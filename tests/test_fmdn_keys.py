# Copyright (c) Bezmenov Denys
#
# SPDX-License-Identifier: Apache-2.0

"""FMDN EID tests.

The Find Hub Network accessory specification describes EID computation but
does not publish a numerical EID test vector. The Fast Pair cryptographic
test-vector appendix (SHA-256, AES, ECDH, HMAC, bloom filter) also has none.
Checked:
  https://developers.google.com/nearby/fast-pair/specifications/extensions/fmdn
  https://developers.google.com/nearby/fast-pair/specifications/appendix/cryptotestcases
The 0x1122334455667788990011223344556677889900 value on the spec page is an
example clock-sync field, not a computed EID.

These tests are therefore self-consistency checks plus the FIPS-197 AES-256
ECB vector for the AES call. They do not claim to match a Google sample EID.
"""

import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.fmdn_keys import (  # noqa: E402
    EID_LEN,
    PLACEHOLDER_COUNT,
    PLACEHOLDER_EIK,
    PLACEHOLDER_START,
    ROTATION_EXPONENT,
    SECP160R1_N,
    SECP160R1_P,
    aes_ecb_256,
    align_scalar,
    compute_slot,
    compute_table,
    generator,
    hashed_flags,
    masked_counter,
    on_curve,
    parse_eik,
    render_c_header,
    scalar_mul,
    scalar_mul_ladder,
    service_data_advert,
    timestamp_block,
)


# FIPS-197 Appendix C.3, AES-256 ECB. Not an FMDN vector.
_FIPS_197_C3_KEY = bytes(range(32))
_FIPS_197_C3_PLAIN = bytes.fromhex("00112233445566778899aabbccddeeff")
_FIPS_197_C3_CIPHER = bytes.fromhex("8ea2b7ca516745bfeafc49904b496089")


class AesCallTest(unittest.TestCase):
    def test_aes_ecb_256_matches_fips_197_c3(self):
        # One block, so a 32-byte EIK encrypts two of these independently.
        one = aes_ecb_256(_FIPS_197_C3_KEY, _FIPS_197_C3_PLAIN + _FIPS_197_C3_PLAIN)
        self.assertEqual(one[:16], _FIPS_197_C3_CIPHER)
        self.assertEqual(one[16:], _FIPS_197_C3_CIPHER)


class TimestampBlockTest(unittest.TestCase):
    def test_block_matches_spec_table_17_layout(self):
        # 0x0084D000 is already aligned to 2^10. Built here, not via the helper,
        # so a drift in timestamp_block fails this test.
        k = 10
        ts = (0x0084D000).to_bytes(4, "big")
        expected = b"\xff" * 11 + bytes([k]) + ts + b"\x00" * 11 + bytes([k]) + ts
        self.assertEqual(len(expected), 32)
        self.assertEqual(timestamp_block(0x0084D000, k), expected)

    def test_low_k_bits_are_cleared(self):
        self.assertEqual(masked_counter(1024 + 1023, 10), 1024)
        self.assertEqual(timestamp_block(1024 + 1023), timestamp_block(1024))
        self.assertNotEqual(timestamp_block(1024), timestamp_block(2048))


class CurveSelfCheckTest(unittest.TestCase):
    def test_generator_is_on_the_curve_and_order_kills_it(self):
        g = generator()
        self.assertTrue(on_curve(g))
        self.assertLess(g.x, SECP160R1_P)
        self.assertIsNone(scalar_mul(SECP160R1_N, g))
        self.assertIsNone(scalar_mul_ladder(SECP160R1_N, g))

    def test_double_and_add_matches_montgomery_ladder(self):
        g = generator()
        for scalar in (1, 2, 3, 0x100, SECP160R1_N - 1, 0x0102030405):
            a = scalar_mul(scalar, g)
            b = scalar_mul_ladder(scalar, g)
            self.assertIsNotNone(a)
            self.assertEqual((a.x, a.y), (b.x, b.y))
            self.assertTrue(on_curve(a))


class EidCompositionTest(unittest.TestCase):
    def test_eid_is_x_coordinate_of_r_times_g(self):
        eik = bytes(range(32))
        slot = compute_slot(eik, 1_700_000_000)
        self.assertEqual(len(slot.eid), EID_LEN)
        self.assertEqual(slot.masked_timestamp, 1_700_000_000 & ~1023)
        block = timestamp_block(slot.timestamp)
        r_prime = int.from_bytes(aes_ecb_256(eik, block), "big")
        self.assertEqual(slot.r, r_prime % SECP160R1_N)
        point = scalar_mul_ladder(slot.r, generator())
        self.assertEqual(slot.eid, point.x.to_bytes(EID_LEN, "big"))
        self.assertTrue(on_curve(point))
        self.assertEqual(slot.flag_xor, hashlib.sha256(align_scalar(slot.r)).digest()[-1])
        self.assertEqual(slot.flag_xor, hashed_flags(slot.r, 0))

    def test_same_window_is_stable_and_next_window_changes(self):
        eik = PLACEHOLDER_EIK
        a = compute_slot(eik, 5000)
        b = compute_slot(eik, 5000 + 100)
        c = compute_slot(eik, 5000 + 1024)
        self.assertEqual(a.eid, b.eid)
        self.assertNotEqual(a.eid, c.eid)
        self.assertEqual(a.masked_timestamp + 1024, c.masked_timestamp)

    def test_table_steps_by_2_to_the_k(self):
        slots = compute_table(PLACEHOLDER_EIK, 4, start=100, k=ROTATION_EXPONENT)
        self.assertEqual(len(slots), 4)
        self.assertEqual(slots[0].masked_timestamp, 0)
        for i in range(1, 4):
            self.assertEqual(
                slots[i].masked_timestamp - slots[i - 1].masked_timestamp,
                1 << ROTATION_EXPONENT,
            )
            self.assertNotEqual(slots[i].eid, slots[i - 1].eid)


class HeaderAndAdvertTest(unittest.TestCase):
    def test_header_round_trip_matches_compute_slot(self):
        slots = compute_table(PLACEHOLDER_EIK, PLACEHOLDER_COUNT, PLACEHOLDER_START)
        text = render_c_header(slots)
        self.assertIn(f"#define FMDN_EID_COUNT {PLACEHOLDER_COUNT}", text)
        self.assertIn("#define FMDN_ROTATION_EXPONENT 10", text)
        self.assertNotIn(PLACEHOLDER_EIK.hex(), text)
        for slot in slots:
            for i in range(0, EID_LEN, 8):
                chunk = ", ".join(f"0x{b:02x}" for b in slot.eid[i : i + 8])
                self.assertIn(chunk, text)
            self.assertIn(f"0x{slot.flag_xor:02x}", text)

    def test_committed_placeholder_header_matches_the_tool(self):
        header_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "firmware",
            "src",
            "fmdn_eid_table.h",
        )
        with open(header_path, encoding="utf-8") as fh:
            committed = fh.read()
        expected = render_c_header(
            compute_table(PLACEHOLDER_EIK, PLACEHOLDER_COUNT, PLACEHOLDER_START)
        )
        self.assertEqual(committed, expected)

    def test_service_data_advert_layout(self):
        eid = bytes(range(20))
        adv = service_data_advert(eid, 0xAB, frame_type=0x41)
        self.assertEqual(adv[0:3], b"\x02\x01\x06")
        self.assertEqual(adv[3], 0x19)
        self.assertEqual(adv[4:8], b"\x16\xaa\xfe\x41")
        self.assertEqual(adv[8:28], eid)
        self.assertEqual(adv[28], 0xAB)
        self.assertEqual(len(adv), 29)

    def test_parse_eik_rejects_the_wrong_length(self):
        self.assertEqual(parse_eik("11" * 32), PLACEHOLDER_EIK)
        with self.assertRaises(Exception):
            parse_eik("11" * 16)


if __name__ == "__main__":
    unittest.main()
