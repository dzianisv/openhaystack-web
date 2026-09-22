# Copyright (c) Bezmenov Denys
#
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for lib/AirTagCrypto.py key derivation."""

import base64
import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.AirTagCrypto import AirTagCrypto  # noqa: E402
from tools import keygen  # noqa: E402


ITERATIONS = 50


class AdvertisementKeyTest(unittest.TestCase):
    def test_advertisement_key_is_28_bytes(self):
        for _ in range(ITERATIONS):
            raw = base64.b64decode(AirTagCrypto().get_advertisement_key())
            self.assertEqual(len(raw), 28)

    def test_advertisement_key_is_deterministic_for_a_private_key(self):
        for _ in range(ITERATIONS):
            crypto = AirTagCrypto()
            private_key = base64.b64encode(crypto._private_key).decode()
            self.assertEqual(
                AirTagCrypto(private_key=private_key).get_advertisement_key(),
                crypto.get_advertisement_key(),
            )

    def test_invalid_private_key_raises_value_error(self):
        # Private value 0 is not a valid SECP224R1 scalar.
        with self.assertRaises(ValueError):
            AirTagCrypto(private_key=base64.b64encode(b"\x00" * 28).decode()).get_advertisement_key()


class PublicKeyTest(unittest.TestCase):
    def test_get_public_key_matches_sha256_of_raw_advertisement_key(self):
        for _ in range(ITERATIONS):
            crypto = AirTagCrypto()
            expected = base64.b64encode(
                hashlib.sha256(base64.b64decode(crypto.get_advertisement_key())).digest()
            ).decode("utf-8")
            self.assertEqual(crypto.get_public_key(), expected)

    def test_get_public_key_returns_str_of_44_chars(self):
        value = AirTagCrypto().get_public_key()
        self.assertIsInstance(value, str)
        self.assertEqual(len(value), 44)
        self.assertEqual(len(base64.b64decode(value)), 32)

    def test_get_public_key_is_deterministic(self):
        crypto = AirTagCrypto()
        private_key = base64.b64encode(crypto._private_key).decode()
        self.assertEqual(
            AirTagCrypto(private_key=private_key).get_public_key(),
            crypto.get_public_key(),
        )


class KeygenParityTest(unittest.TestCase):
    """tools/keygen.py computes key_id inline; prove get_public_key() is the same value."""

    def test_key_id_equals_get_public_key(self):
        for _ in range(ITERATIONS):
            keys = keygen.generate_keys()
            crypto = AirTagCrypto(private_key=keys.private_key)
            self.assertEqual(crypto.get_advertisement_key(), keys.advertisement_key)
            self.assertEqual(crypto.get_public_key(), keys.key_id)
            self.assertEqual(
                base64.b64encode(
                    hashlib.sha256(base64.b64decode(keys.advertisement_key)).digest()
                ).decode("utf-8"),
                keys.key_id,
            )


if __name__ == "__main__":
    unittest.main()
