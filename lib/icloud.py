#!/usr/bin/env python3

"""Script to get the icloud key from your keychain password."""

from getpass import getpass
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.modes import CBC
from cryptography.hazmat.primitives.ciphers.algorithms import TripleDES
from cryptography.hazmat.backends import default_backend
from openhaybike.utils import unpad, decrypt
from openhaybike.keychain import read_keychain


import os
import stat
import tempfile
import time
from pathlib import Path

# The cached iCloud key is a live credential stored in plaintext, so the cache is
# deliberately short-lived. Expiry only costs an interactive keychain re-prompt.
CACHE_TTL_HOURS = 12

# Permissions for the cache file and its parent directory: owner-only.
CACHE_FILE_MODE = 0o600
CACHE_DIR_MODE = 0o700


def _config_dir() -> str:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return xdg
    return os.path.join(str(Path.home()), ".config")


ICLOUD_CACHE_FILE = os.path.join(_config_dir(), "icloud")

def is_cache_valid(file_path):
    """
    Check if the file at `file_path` holds a usable, non-expired cached key.

    The cache is valid only when the file exists, is not empty (an interrupted
    write can leave a zero-byte file) and was modified less than
    `CACHE_TTL_HOURS` hours ago.

    Args:
    file_path (str): The path to the file.

    Returns:
    bool: True if the cached value is usable and fresh, False otherwise.
    """
    if not os.path.exists(file_path):
        return False

    try:
        with open(file_path, "r", encoding='utf8') as f:
            if not f.read().strip():
                return False
    except OSError:
        return False

    # Get the last modification time of the file
    last_modified_time = os.path.getmtime(file_path)

    # Get the current time
    current_time = time.time()

    # Calculate the difference in hours
    hours_difference = (current_time - last_modified_time) / 3600

    return hours_difference < CACHE_TTL_HOURS


def get_icloud_key(password_fn = None) -> str:
    keychain = read_keychain()

    if password_fn is None:
        password = getpass("Keychain password: ")
    else:
        password = password_fn()

    master_key = PBKDF2HMAC(
        algorithm=hashes.SHA1(),
        length=24,
        salt=keychain.db_key_salt,
        iterations=1000,
        backend=default_backend(),
    ).derive(bytes(password, encoding="ascii"))
    db_key = unpad(
        decrypt(keychain.db_key_enc, TripleDES(master_key), CBC(keychain.db_key_IV)),
        TripleDES.block_size,
    )[:24]
    p1 = unpad(
        decrypt(
            keychain.symmetric_key_enc, TripleDES(db_key), CBC(b"J\xdd\xa2,y\xe8!\x05")
        ),
        TripleDES.block_size,
    )
    symmetric_key = unpad(
        decrypt(p1[:32][::-1], TripleDES(db_key), CBC(keychain.symmetric_key_IV)),
        TripleDES.block_size,
    )[4:]
    icloud_key = unpad(
        decrypt(
            keychain.icloud_key_enc,
            TripleDES(symmetric_key),
            CBC(keychain.icloud_key_IV),
        ),
        TripleDES.block_size,
    )
    return icloud_key

def _repair_permissions(file_path):
    """Tighten a pre-existing cache file to owner-only if it is more permissive."""
    try:
        current_mode = stat.S_IMODE(os.stat(file_path).st_mode)
    except OSError:
        return
    if current_mode != CACHE_FILE_MODE:
        os.chmod(file_path, CACHE_FILE_MODE)


def _write_cache(file_path, key):
    """Atomically write `key` to `file_path` with owner-only permissions."""
    directory = os.path.dirname(file_path) or "."
    os.makedirs(directory, mode=CACHE_DIR_MODE, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=directory)
    try:
        os.chmod(tmp_path, CACHE_FILE_MODE)
        with os.fdopen(fd, "w", encoding='utf8') as f:
            f.write(key)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, file_path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _read_cache(file_path):
    with open(file_path, "r", encoding='utf8') as f:
        return f.read().strip()


def get_icloud_key_cached(password_fn = None) -> str:
    if is_cache_valid(ICLOUD_CACHE_FILE):
        _repair_permissions(ICLOUD_CACHE_FILE)
        return _read_cache(ICLOUD_CACHE_FILE)

    key = get_icloud_key(password_fn).decode('ascii').strip()
    _write_cache(ICLOUD_CACHE_FILE, key)
    return key

if __name__ == "__main__":
    print(get_icloud_key_cached())

