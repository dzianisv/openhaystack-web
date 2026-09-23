"""Apple account/session management on top of FindMy.py (``findmy`` 0.10.2).

This module owns everything related to *authenticating* against Apple's
Find My network. It replaces the old macOS-keychain iCloud-token flow, which
only worked on macOS 12 and required the Mac to be signed into iCloud.

It deliberately contains no web-framework import (eel/sanic) and never prompts
for credentials: interactive login lives in ``tools/findmy_login.py``.

Account state (a live Apple credential, including the anisette provisioning
blob) is written atomically with owner-only permissions, following the same
mkstemp -> chmod 0600 -> fsync -> os.replace pattern previously used for the
iCloud key cache.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

from findmy import AppleAccount, LocalAnisetteProvider, LoginState

logger = logging.getLogger(__name__)

APP_DIR_NAME = "openhaystack-web"
ACCOUNT_FILE_NAME = "account.json"
ANISETTE_LIBS_FILE_NAME = "anisette-libs.bin"

# The account state file is a live Apple credential: owner-only, like ~/.ssh.
ACCOUNT_FILE_MODE = 0o600
CONFIG_DIR_MODE = 0o700

# Env overrides (both optional).
ACCOUNT_FILE_ENV = "FINDMY_ACCOUNT_FILE"
ANISETTE_LIBS_ENV = "FINDMY_ANISETTE_LIBS"

LOGIN_COMMAND = "tools/findmy_login.py"


class AccountNotConfiguredError(RuntimeError):
    """Raised when no usable Apple account state file exists yet."""


class AccountStateError(RuntimeError):
    """Raised when an account state file exists but cannot be restored."""


def config_dir() -> Path:
    """Return the directory holding this app's config, honouring XDG_CONFIG_HOME."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / APP_DIR_NAME


def account_file_path() -> Path:
    """Path of the Apple account state file (``$FINDMY_ACCOUNT_FILE`` wins)."""
    override = os.environ.get(ACCOUNT_FILE_ENV)
    if override:
        return Path(override).expanduser()
    return config_dir() / ACCOUNT_FILE_NAME


def anisette_libs_path(account_path: Optional[Path] = None) -> Path:
    """Path of the cached anisette libraries archive.

    ``LocalAnisetteProvider`` downloads a set of Apple libraries on first use
    and calls ``save_libs(libs_path)`` afterwards, so keeping a stable path
    next to the account file turns every later start into a local load instead
    of a network download. The anisette *provisioning* state is not stored
    here; it is embedded in the account JSON by ``AppleAccount.to_json()``.
    """
    override = os.environ.get(ANISETTE_LIBS_ENV)
    if override:
        return Path(override).expanduser()
    parent = (account_path or account_file_path()).parent
    return parent / ANISETTE_LIBS_FILE_NAME


def _ensure_config_dir(directory: Path) -> None:
    directory.mkdir(mode=CONFIG_DIR_MODE, parents=True, exist_ok=True)
    try:
        if stat.S_IMODE(directory.stat().st_mode) != CONFIG_DIR_MODE:
            directory.chmod(CONFIG_DIR_MODE)
    except OSError as exc:  # pragma: no cover - best effort hardening
        logger.warning("could not tighten permissions on %s: %s", directory, exc)


def atomic_write_secret(path: Path, text: str) -> Path:
    """Write ``text`` to ``path`` atomically with mode 0600 in a 0700 parent.

    Same proven pattern as the old iCloud key cache: write a temp file in the
    *target* directory (so ``os.replace`` stays on one filesystem), tighten its
    mode before any content is written, fsync, then rename over the target.
    """
    path = Path(path)
    directory = path.parent if str(path.parent) else Path(".")
    _ensure_config_dir(directory)

    fd, tmp_path = tempfile.mkstemp(dir=str(directory))
    try:
        os.chmod(tmp_path, ACCOUNT_FILE_MODE)
        with os.fdopen(fd, "w", encoding="utf8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return path


def new_anisette_provider(account_path: Optional[Path] = None) -> LocalAnisetteProvider:
    """A fresh local anisette provider (no Docker, no public anisette server)."""
    libs = anisette_libs_path(account_path)
    _ensure_config_dir(libs.parent)
    return LocalAnisetteProvider(libs_path=libs)


def new_account(account_path: Optional[Path] = None) -> AppleAccount:
    """A brand-new, logged-out account object, for the interactive login tool."""
    return AppleAccount(new_anisette_provider(account_path))


def has_account(account_path: Optional[Path] = None) -> bool:
    """True when a non-empty account state file exists."""
    path = Path(account_path) if account_path else account_file_path()
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def save_account(account: AppleAccount, account_path: Optional[Path] = None) -> Path:
    """Persist ``account`` state atomically at 0600 and return the path used."""
    path = Path(account_path) if account_path else account_file_path()
    state = account.to_json()  # no dst: findmy's own writer is not atomic/0600
    atomic_write_secret(path, json.dumps(state, indent=4))
    logger.debug("wrote Apple account state to %s", path)
    return path


def load_account(account_path: Optional[Path] = None) -> AppleAccount:
    """Restore the cached Apple account.

    Raises:
        AccountNotConfiguredError: no state file yet - run the login tool.
        AccountStateError: the file exists but is corrupt/unreadable.
    """
    path = Path(account_path) if account_path else account_file_path()
    if not has_account(path):
        raise AccountNotConfiguredError(
            f"No Apple account session found at {path}. "
            f"Run `{LOGIN_COMMAND}` once to sign in with your Apple ID."
        )
    try:
        return AppleAccount.from_json(path, anisette_libs_path=anisette_libs_path(path))
    except AccountNotConfiguredError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise AccountStateError(
            f"Could not restore the Apple account session from {path}: {exc}. "
            f"Delete the file and re-run `{LOGIN_COMMAND}`."
        ) from exc


def is_logged_in(account: AppleAccount) -> bool:
    """True when ``account`` holds a usable (fully logged-in) session."""
    return account.login_state == LoginState.LOGGED_IN


def close_account(account: Any) -> None:
    """Release the account's HTTP/anisette resources.

    ``AppleAccount.close()`` is a coroutine even on the sync class, so it has
    to be driven by the account's own event loop. Failures here are logged, not
    raised: closing must never mask the caller's result.
    """
    if account is None:
        return
    try:
        result = account.close()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("error closing Apple account session: %s", exc)
        return
    if not asyncio.iscoroutine(result):
        return
    loop = getattr(account, "_evt_loop", None)
    try:
        if loop is not None and not loop.is_closed() and not loop.is_running():
            loop.run_until_complete(result)
        else:
            asyncio.run(result)
    except Exception as exc:  # pragma: no cover - defensive
        result.close()
        logger.warning("error closing Apple account session: %s", exc)


@contextmanager
def account_session(account_path: Optional[Path] = None) -> Iterator[AppleAccount]:
    """Context manager yielding a restored account and closing it afterwards."""
    account = load_account(account_path)
    try:
        yield account
    finally:
        close_account(account)
