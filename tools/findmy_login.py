#!/usr/bin/env python3

"""Sign in to Apple once and cache the Find My session on disk.

Run this a single time (and after the session expires). Every login that
presents a *new* device identity registers another device on your Apple ID, and
an Apple ID that has accumulated too many of them starts refusing sign-ins with
"Account limit reached" - so this script refuses to log in again when a valid
session already exists, unless ``--force`` is given.

Crucially, the device identity (``uid``/``devid``) is persisted even when a
login *fails*, and every later attempt reuses it. Retrying therefore costs zero
extra device slots. ``--force`` reuses it too; only ``--new-device-identity``
mints a new one, and that is the expensive action.

The Apple ID password is read with getpass: it is never echoed, never logged,
and never printed by this script. On success the session state produced by
FindMy.py is persisted with mode 0600 - note that this state contains the Apple
ID password in plaintext (see the README). After a failed login only the device
identity is stored: no username, no password.
"""

import argparse
import sys
from getpass import getpass
from pathlib import Path

# Allow running the script from any working directory, not just the repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from findmy import (  # noqa: E402
    AppleAccount,
    InvalidCredentialsError,
    LoginState,
    SmsSecondFactorMethod,
    TrustedDeviceSecondFactorMethod,
    UnhandledProtocolError,
)

from lib import findmy_backend  # noqa: E402

DEVICES_URL = "https://account.apple.com/account/manage/section/devices"


def _is_account_limit_error(exc: BaseException) -> bool:
    """True for Apple's mobileme "Account limit reached" rejection only."""
    text = str(exc).lower()
    return "account limit reached" in text


def _print_account_limit_help() -> None:
    """Explain the one failure that is fixed on Apple's website, not here."""
    print(
        "\nApple refused the final step because your Apple ID has too many\n"
        "registered devices. Remove the ones this tool created before retrying:\n"
        f"  {DEVICES_URL}\n"
        'They show up as "MacBook Pro" devices running macOS 13.4.1 (build\n'
        "22F8) with a blank/zero serial number - that is the identity FindMy.py\n"
        'sends ("<MacBookPro18,3> <Mac OS X;13.4.1;22F8>", X-Apple-I-SRL-NO: "0").\n'
        "Leave your real Macs, iPhones and iPads alone.\n"
        "This attempt's device identity has been saved, so retrying after the\n"
        "cleanup will reuse it and will not register yet another device.",
        file=sys.stderr,
    )


def _describe_method(method) -> str:
    if isinstance(method, SmsSecondFactorMethod):
        return f"SMS to {method.phone_number}"
    if isinstance(method, TrustedDeviceSecondFactorMethod):
        return "Trusted device (code shown on your Apple devices)"
    return type(method).__name__


def _choose_method(methods):
    print("\nTwo-factor authentication required. Available methods:")
    for index, method in enumerate(methods, start=1):
        print(f"  [{index}] {_describe_method(method)}")

    if len(methods) == 1:
        print("Using the only available method.")
        return methods[0]

    while True:
        raw = input(f"Choose a method [1-{len(methods)}]: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(methods):
            return methods[int(raw) - 1]
        print("Please enter one of the listed numbers.")


def _complete_2fa(account: AppleAccount) -> LoginState:
    methods = account.get_2fa_methods()
    if not methods:
        raise SystemExit(
            "Apple requires two-factor authentication but offered no method. "
            "Try again later, or check your Apple ID security settings."
        )

    method = _choose_method(methods)
    method.request()
    print("A verification code has been sent/displayed.")

    for attempt in range(3):
        code = input("Enter the 6-digit code: ").strip()
        try:
            state = method.submit(code)
        except (InvalidCredentialsError, UnhandledProtocolError) as exc:
            print(f"Code rejected: {exc}")
            if _is_account_limit_error(exc):
                # Retrying cannot help: the code was accepted, the Apple ID is full.
                _print_account_limit_help()
                raise SystemExit(1) from None
            continue
        if state == LoginState.LOGGED_IN:
            return state
        print(f"Login state after code: {state}. Retrying...")
        if attempt == 2:
            break
    raise SystemExit("Two-factor authentication failed.")


def _existing_session(account_path: Path):
    """Return a usable cached account, or None."""
    if not findmy_backend.has_account(account_path):
        return None
    try:
        account = findmy_backend.load_account(account_path)
    except (findmy_backend.AccountStateError, findmy_backend.AccountNotConfiguredError) as exc:
        print(f"Existing session unusable ({exc}); a new login is needed.")
        return None
    if findmy_backend.is_logged_in(account):
        return account
    findmy_backend.close_account(account)
    return None


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="tools/findmy_login.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--account-file",
        default=None,
        help="Where to store the session (default: %s, or $%s)."
        % (findmy_backend.account_file_path(), findmy_backend.ACCOUNT_FILE_ENV),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Log in again even if a valid session exists. The stored device "
        "identity is reused, so this does not register another device.",
    )
    parser.add_argument(
        "--new-device-identity",
        action="store_true",
        help="DANGEROUS: discard the stored device identity and mint a new one. "
        "Apple then registers ANOTHER device on your Apple ID, which is exactly "
        "what causes 'Account limit reached'. Only use this if Apple has "
        "blacklisted the current identity and you have already removed the stale "
        "devices at " + DEVICES_URL + ".",
    )
    parser.add_argument(
        "--apple-id",
        default=None,
        help="Apple ID (email). Prompted for when omitted. The password is "
        "always prompted for and is never printed or logged.",
    )
    return parser.parse_args(argv)


def _account_for_login(account_path: Path, new_identity: bool) -> AppleAccount:
    if new_identity:
        print(
            "Minting a NEW device identity: Apple will register another device "
            "on your Apple ID."
        )
        return findmy_backend.new_account(account_path)
    account = findmy_backend.account_for_login(account_path)
    if findmy_backend.has_state_file(account_path):
        print(f"Reusing the device identity stored in {account_path}.")
    return account


def _persist_identity(account: AppleAccount, account_path: Path) -> None:
    """Keep the device identity after a failure so the retry is free."""
    try:
        saved = findmy_backend.save_identity(account, account_path)
    except OSError as exc:
        print(f"Warning: could not save the device identity: {exc}", file=sys.stderr)
        return
    if saved is not None:
        print(
            f"Device identity saved to {saved} (mode 0600) so the next attempt "
            "reuses it instead of registering another device.",
            file=sys.stderr,
        )


def main(argv=None) -> int:
    args = parse_args(argv)
    account_path = Path(args.account_file) if args.account_file else findmy_backend.account_file_path()

    if not args.force:
        existing = _existing_session(account_path)
        if existing is not None:
            print(
                f"Already signed in as {existing.account_name} "
                f"(session at {account_path}). Nothing to do.\n"
                "Use --force only if you really need a new login."
            )
            findmy_backend.close_account(existing)
            return 0

    apple_id = args.apple_id or input("Apple ID (email): ").strip()
    if not apple_id:
        print("An Apple ID is required.", file=sys.stderr)
        return 2
    password = getpass("Apple ID password (not echoed): ")
    if not password:
        print("A password is required.", file=sys.stderr)
        return 2

    account = _account_for_login(account_path, args.new_device_identity)
    succeeded = False
    try:
        try:
            state = account.login(apple_id, password)
        except InvalidCredentialsError:
            print("Apple rejected those credentials.", file=sys.stderr)
            return 1
        except UnhandledProtocolError as exc:
            print(f"Login failed: {exc}", file=sys.stderr)
            if _is_account_limit_error(exc):
                _print_account_limit_help()
            return 1
        finally:
            del password

        if state == LoginState.REQUIRE_2FA:
            state = _complete_2fa(account)

        if state != LoginState.LOGGED_IN:
            print(f"Login did not complete (state: {state}).", file=sys.stderr)
            return 1

        saved_to = findmy_backend.save_account(account, account_path)
        succeeded = True
        print(
            f"\nSigned in as {account.account_name}.\n"
            f"Session saved to {saved_to} (mode 0600). It contains your Apple ID "
            "password in plaintext - treat it like ~/.ssh/id_rsa."
        )
        return 0
    finally:
        if not succeeded:
            _persist_identity(account, account_path)
        findmy_backend.close_account(account)


if __name__ == "__main__":
    raise SystemExit(main())
