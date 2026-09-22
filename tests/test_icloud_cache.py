#!/usr/bin/env python3
"""Regression tests for the iCloud key cache (permissions, TTL, round-trip).

These tests never call the real `get_icloud_key()` (which would prompt for the
macOS keychain password) and never touch the real ~/.config/icloud.
"""

import os
import stat
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import icloud  # noqa: E402


FAKE_KEY = "AAAABBBBCCCCDDDDEEEEFFFF"


class ICloudCacheTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

        self.real_path = icloud.ICLOUD_CACHE_FILE
        self.real_get_key = icloud.get_icloud_key

        self.cache_dir = os.path.join(self._tmp.name, ".config")
        self.cache_file = os.path.join(self.cache_dir, "icloud")
        icloud.ICLOUD_CACHE_FILE = self.cache_file
        icloud.get_icloud_key = lambda password_fn=None: FAKE_KEY.encode("ascii")

        self.addCleanup(self._restore)

    def _restore(self):
        icloud.ICLOUD_CACHE_FILE = self.real_path
        icloud.get_icloud_key = self.real_get_key

    def _mode(self, path):
        return stat.S_IMODE(os.stat(path).st_mode)

    def test_fresh_cache_file_is_0600_and_dir_created(self):
        self.assertFalse(os.path.exists(self.cache_dir))
        key = icloud.get_icloud_key_cached(password_fn=lambda: "unused")
        self.assertEqual(key, FAKE_KEY)
        self.assertTrue(os.path.isdir(self.cache_dir))
        self.assertEqual(oct(self._mode(self.cache_file)), oct(0o600))

    def test_parent_dir_created_with_0700(self):
        icloud.get_icloud_key_cached(password_fn=lambda: "unused")
        self.assertEqual(oct(self._mode(self.cache_dir)), oct(0o700))

    def test_preexisting_0644_file_is_repaired(self):
        os.makedirs(self.cache_dir, exist_ok=True)
        with open(self.cache_file, "w", encoding="utf8") as f:
            f.write(FAKE_KEY)
        os.chmod(self.cache_file, 0o644)
        self.assertEqual(oct(self._mode(self.cache_file)), oct(0o644))

        key = icloud.get_icloud_key_cached(password_fn=lambda: "unused")
        self.assertEqual(key, FAKE_KEY)
        self.assertEqual(oct(self._mode(self.cache_file)), oct(0o600))

    def test_empty_cache_is_invalid(self):
        os.makedirs(self.cache_dir, exist_ok=True)
        open(self.cache_file, "w", encoding="utf8").close()
        self.assertFalse(icloud.is_cache_valid(self.cache_file))

        with open(self.cache_file, "w", encoding="utf8") as f:
            f.write("   \n")
        self.assertFalse(icloud.is_cache_valid(self.cache_file))

    def test_missing_cache_is_invalid(self):
        self.assertFalse(icloud.is_cache_valid(self.cache_file))

    def test_ttl_boundaries(self):
        icloud.get_icloud_key_cached(password_fn=lambda: "unused")
        self.assertTrue(icloud.is_cache_valid(self.cache_file))

        ttl_seconds = icloud.CACHE_TTL_HOURS * 3600
        now = time.time()

        stale = now - (ttl_seconds + 60)
        os.utime(self.cache_file, (stale, stale))
        self.assertFalse(icloud.is_cache_valid(self.cache_file))

        fresh = now - (ttl_seconds - 60)
        os.utime(self.cache_file, (fresh, fresh))
        self.assertTrue(icloud.is_cache_valid(self.cache_file))

    def test_round_trip_is_exact(self):
        icloud._write_cache(self.cache_file, FAKE_KEY)
        self.assertEqual(icloud._read_cache(self.cache_file), FAKE_KEY)
        self.assertEqual(
            icloud.get_icloud_key_cached(password_fn=lambda: "unused"), FAKE_KEY
        )

    def test_stale_cache_is_rederived_and_secured(self):
        os.makedirs(self.cache_dir, exist_ok=True)
        with open(self.cache_file, "w", encoding="utf8") as f:
            f.write("OLDKEY")
        os.chmod(self.cache_file, 0o644)
        stale = time.time() - (icloud.CACHE_TTL_HOURS * 3600 + 60)
        os.utime(self.cache_file, (stale, stale))

        key = icloud.get_icloud_key_cached(password_fn=lambda: "unused")
        self.assertEqual(key, FAKE_KEY)
        self.assertEqual(oct(self._mode(self.cache_file)), oct(0o600))

    def test_real_user_cache_path_untouched(self):
        self.assertNotIn(os.path.expanduser("~/.config/icloud"), self.cache_file)


if __name__ == "__main__":
    unittest.main(verbosity=2)
