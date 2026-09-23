#!/usr/bin/env python3

"""Sign in to Apple once and cache the Find My session on disk.

Run this a single time (and after the session expires). Every fresh login
registers another trusted device on your Apple ID, and an Apple ID that has
accumulated too many of them eventually starts refusing sign-ins - so this
script refuses to log in again when a valid session already exists, unless
``--force`` is given.

The Apple ID password is read with getpass: it is never echoed, never logged,
and never written anywhere by this script. Only the session state produced by
FindMy.py is persisted, with mode 0600.
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
            continue
        if state == LoginState.LOGGED_IN:
            return state
        print(f"Login state after code: {state}. Retrying...")
        if attempt == 2:
            break
    raise SystemExit("Two-factor authentication failed; nothing was saved.")


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
        help="Log in again even if a valid session exists. Use sparingly: each "
        "login adds a trusted device to your Apple ID.",
    )
    parser.add_argument(
        "--apple-id",
        default=None,
        help="Apple ID (email). Prompted for when omitted. The password is "
        "always prompted for and is never stored or logged.",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    account_path = Path(args.account_file) if args.account_file else findmy_backend.account_file_path()

    if not args.force:
        existing = _existing_session(account_path)
        if existing is not None:
            print(
                f"Already signed in as {existing.account_name} "
                f"(session at {account_path}). Nothing to do.\n"
                "Use --force only if you really need a new login: each login "
                "adds a trusted device to your Apple ID."
            )
            findmy_backend.close_account(existing)
            return 0

    apple_id = args.apple_id or input("Apple ID (email): ").strip()
    if not apple_id:
        print("An Apple ID is required.", file=sys.stderr)
        return 2
    password = getpass("Apple ID password (not echoed, not stored): ")
    if not password:
        print("A password is required.", file=sys.stderr)
        return 2

    account = findmy_backend.new_account(account_path)
    try:
        try:
            state = account.login(apple_id, password)
        except InvalidCredentialsError:
            print("Apple rejected those credentials.", file=sys.stderr)
            return 1
        finally:
            del password

        if state == LoginState.REQUIRE_2FA:
            state = _complete_2fa(account)

        if state != LoginState.LOGGED_IN:
            print(f"Login did not complete (state: {state}).", file=sys.stderr)
            return 1

        saved_to = findmy_backend.save_account(account, account_path)
        print(
            f"\nSigned in as {account.account_name}.\n"
            f"Session saved to {saved_to} (mode 0600)."
        )
        return 0
    finally:
        findmy_backend.close_account(account)


if __name__ == "__main__":
    raise SystemExit(main())
