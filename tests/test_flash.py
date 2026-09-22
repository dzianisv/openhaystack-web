#!/usr/bin/env python3
"""Regression tests for the firmware advertisement-key patching in tools/flash.py."""

import base64
import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

import flash  # noqa: E402

PLACEHOLDER = flash.PLACEHOLDER
PREFIX = b"\x00\x01\x02\x03" * 8
SUFFIX = b"\xfe\xff" * 16


def build_image(placeholder_count=1):
    return PREFIX + (PLACEHOLDER + SUFFIX) * placeholder_count


class PatchFirmwareTest(unittest.TestCase):

    def assert_patch_ok(self, key):
        self.assertEqual(len(key), len(PLACEHOLDER))
        data = build_image()
        patched = flash.patch_firmware(data, key)
        self.assertEqual(len(patched), len(data))
        self.assertNotIn(PLACEHOLDER, patched)
        self.assertIn(key, patched)
        self.assertEqual(patched, PREFIX + key + SUFFIX)

    def test_plain_key(self):
        self.assert_patch_ok(bytes(range(28)))

    def test_key_with_literal_backslash(self):
        # 0x5C would be read as a regex escape by re.sub()
        self.assert_patch_ok(b"\\" + bytes(range(1, 28)))

    def test_key_with_backslash_digit_group_reference(self):
        self.assert_patch_ok(b"AB\\1CD\\9EF" + bytes(range(1, 19)))

    def test_key_with_group_zero_backreference(self):
        # b"\g<0>" would re-insert the placeholder itself under re.sub()
        key = b"\\g<0>" + bytes(range(1, 24))
        self.assert_patch_ok(key)

    def test_key_with_backslash_letter_bad_escape(self):
        self.assert_patch_ok(b"\\d\\w\\Q" + bytes(range(1, 23)))

    def test_generated_keys_round_trip(self):
        try:
            import keygen
        except ImportError as error:  # pragma: no cover - env without crypto deps
            self.skipTest(f"keygen unavailable: {error}")
        for _ in range(200):
            key = base64.b64decode(keygen.generate_keys().advertisement_key)
            self.assert_patch_ok(key)

    def test_missing_placeholder_raises(self):
        with self.assertRaises(ValueError):
            flash.patch_firmware(PREFIX + SUFFIX, bytes(range(28)))

    def test_multiple_placeholders_raise(self):
        with self.assertRaises(ValueError):
            flash.patch_firmware(build_image(placeholder_count=2), bytes(range(28)))

    def test_wrong_key_length_raises(self):
        with self.assertRaises(ValueError):
            flash.patch_firmware(build_image(), bytes(range(27)))


class DecodeAdvertisementKeyTest(unittest.TestCase):

    def test_valid_key(self):
        raw = bytes(range(28))
        self.assertEqual(flash.decode_advertisement_key(base64.b64encode(raw).decode()), raw)

    def test_invalid_base64(self):
        with self.assertRaises(ValueError):
            flash.decode_advertisement_key("not base64!!!")

    def test_wrong_decoded_length(self):
        with self.assertRaises(ValueError):
            flash.decode_advertisement_key(base64.b64encode(b"short").decode())


if __name__ == "__main__":
    unittest.main()
