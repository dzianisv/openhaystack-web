#!/usr/bin/env python3
"""Precompute Google Find Hub (FMDN) ephemeral identifiers.

Algorithm, verbatim from the Find Hub Network accessory specification
(https://developers.google.com/nearby/fast-pair/specifications/extensions/fmdn),
"Ephemeral identifier (EID) computation" and "Hashed flags":

  * Build the 32-byte timestamp block (Table 17): 11 bytes of 0xFF, rotation
    exponent K, the 32-bit big-endian beacon time counter with the K lowest
    bits cleared, 11 bytes of 0x00, K again, and the same masked counter.
  * r' = AES-ECB-256(ephemeral identity key, timestamp block). The EIK is
    32 bytes. K is fixed at 10 by the spec (1024-second windows).
  * r = r' mod n, n the order of SECP160R1 (SEC 2). The spec's formula is
    "r = r' mod n" even though the surrounding sentence says "projected to Fp".
  * EID = x-coordinate of R = r * G, 20 bytes, big-endian.
  * Hashed flags = clear_flags XOR the least significant byte of
    SHA256(r). r is aligned to 160 bits: zero-pad on the left, or drop
    the most significant bits if r does not fit in 160 bits.

cryptography has AES but not SECP160R1, so AES comes from cryptography and
the curve math is pure Python. This does not register an accessory with
Google. See firmware/src/README.md for the provisioning limits.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# SECP160R1, SEC 2 v2.0. a = p - 3.
SECP160R1_P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF7FFFFFFF
SECP160R1_A = -3
SECP160R1_B = 0x1C97BEFC54BD7A8B65ACF89F81D4D4ADC565FA45
SECP160R1_GX = 0x4A96B5688EF573284664698968C38BB913CBFC82
SECP160R1_GY = 0x23A628553168947D59DCC912042351377AC5FB32
SECP160R1_N = 0x0100000000000000000001F4C8F927AED3CA752257
SECP160R1_BITS = 160

ROTATION_EXPONENT = 10
EID_LEN = 20
EIK_LEN = 32

# Public sample only. Not registered with a Google account. The committed
# firmware table is built from this so a GOOGLE_FMDN image has something to
# advertise; replace it before expecting Find Hub to resolve the tag.
PLACEHOLDER_EIK = bytes([0x11]) * EIK_LEN
PLACEHOLDER_COUNT = 8
PLACEHOLDER_START = 0


@dataclass(frozen=True)
class Point:
    x: int
    y: int


def _mod_p(value: int) -> int:
    return value % SECP160R1_P


def _inv(value: int) -> int:
    return pow(value % SECP160R1_P, -1, SECP160R1_P)


def point_add(p: Point | None, q: Point | None) -> Point | None:
    """Affine addition on SECP160R1. None is the point at infinity."""
    if p is None:
        return q
    if q is None:
        return p
    if p.x == q.x and _mod_p(p.y + q.y) == 0:
        return None
    if p.x == q.x and p.y == q.y:
        lam = _mod_p((3 * p.x * p.x + SECP160R1_A) * _inv(2 * p.y))
    else:
        lam = _mod_p((q.y - p.y) * _inv(q.x - p.x))
    x = _mod_p(lam * lam - p.x - q.x)
    y = _mod_p(lam * (p.x - x) - p.y)
    return Point(x, y)


def scalar_mul(k: int, point: Point | None) -> Point | None:
    """Double-and-add. k is taken mod n; 0 yields infinity."""
    if point is None:
        return None
    k %= SECP160R1_N
    result: Point | None = None
    addend: Point | None = point
    while k:
        if k & 1:
            result = point_add(result, addend)
        addend = point_add(addend, addend)
        k >>= 1
    return result


def scalar_mul_ladder(k: int, point: Point | None) -> Point | None:
    """Montgomery ladder. Independent of scalar_mul; used by the tests."""
    if point is None:
        return None
    k %= SECP160R1_N
    r0: Point | None = None
    r1: Point | None = point
    for shift in range(k.bit_length() - 1, -1, -1):
        if (k >> shift) & 1:
            r0 = point_add(r0, r1)
            r1 = point_add(r1, r1)
        else:
            r1 = point_add(r0, r1)
            r0 = point_add(r0, r0)
    return r0


def generator() -> Point:
    return Point(SECP160R1_GX, SECP160R1_GY)


def on_curve(point: Point | None) -> bool:
    if point is None:
        return False
    left = _mod_p(point.y * point.y)
    right = _mod_p(point.x * point.x * point.x + SECP160R1_A * point.x + SECP160R1_B)
    return left == right


def aes_ecb_256(key: bytes, block: bytes) -> bytes:
    if len(key) != EIK_LEN:
        raise ValueError(f"EIK must be {EIK_LEN} bytes, got {len(key)}")
    if len(block) != EIK_LEN or len(block) % 16 != 0:
        raise ValueError("AES-ECB-256 input must be one 32-byte block")
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return encryptor.update(block) + encryptor.finalize()


def masked_counter(timestamp: int, k: int = ROTATION_EXPONENT) -> int:
    if timestamp < 0 or timestamp > 0xFFFFFFFF:
        raise ValueError("beacon time counter must fit in a uint32")
    if not 0 <= k <= 31:
        raise ValueError("rotation exponent K must be 0..31")
    return timestamp & ~((1 << k) - 1) & 0xFFFFFFFF


def timestamp_block(timestamp: int, k: int = ROTATION_EXPONENT) -> bytes:
    """Table 17 of the Find Hub Network accessory specification."""
    ts = masked_counter(timestamp, k).to_bytes(4, "big")
    return b"\xff" * 11 + bytes([k]) + ts + b"\x00" * 11 + bytes([k]) + ts


def align_scalar(r: int, bits: int = SECP160R1_BITS) -> bytes:
    """Left-pad or truncate MSBs so r is exactly `bits` wide, as the spec requires."""
    if r < 0:
        raise ValueError("r must be non-negative")
    nbytes = bits // 8
    if r == 0:
        return b"\x00" * nbytes
    raw = r.to_bytes((r.bit_length() + 7) // 8, "big")
    if len(raw) < nbytes:
        return raw.rjust(nbytes, b"\x00")
    if len(raw) > nbytes:
        return raw[-nbytes:]
    return raw


def hashed_flags(r: int, clear_flags: int = 0) -> int:
    """clear_flags XOR LSB of SHA256(r aligned to the curve size)."""
    if not 0 <= clear_flags <= 0xFF:
        raise ValueError("clear flags must be one byte")
    digest = hashlib.sha256(align_scalar(r)).digest()
    return clear_flags ^ digest[-1]


@dataclass(frozen=True)
class EidSlot:
    timestamp: int
    masked_timestamp: int
    r: int
    eid: bytes
    flag_xor: int

    @property
    def hashed_flags(self) -> int:
        """Hashed flags for clear flags 0x00 (battery unsupported, not UTP)."""
        return self.flag_xor


def compute_slot(eik: bytes, timestamp: int, k: int = ROTATION_EXPONENT) -> EidSlot:
    block = timestamp_block(timestamp, k)
    r_prime = int.from_bytes(aes_ecb_256(eik, block), "big")
    r = r_prime % SECP160R1_N
    if r == 0:
        raise ValueError("r mod n is 0; R is the point at infinity and has no EID")
    point = scalar_mul(r, generator())
    if point is None:
        raise ValueError("r * G is the point at infinity")
    eid = point.x.to_bytes(EID_LEN, "big")
    return EidSlot(
        timestamp=timestamp,
        masked_timestamp=masked_counter(timestamp, k),
        r=r,
        eid=eid,
        flag_xor=hashed_flags(r, 0),
    )


def compute_table(
    eik: bytes,
    count: int,
    start: int = 0,
    k: int = ROTATION_EXPONENT,
) -> list[EidSlot]:
    if count < 1:
        raise ValueError("count must be >= 1")
    window = 1 << k
    base = masked_counter(start, k)
    return [compute_slot(eik, base + i * window, k) for i in range(count)]


def service_data_advert(eid: bytes, hashed_flags_byte: int, frame_type: int = 0x40) -> bytes:
    """Legacy ADV payload: flags AD + FEAA service data, matching spec Table 15.

    Frame type 0x40 is normal mode, which is what the firmware advertises.
    0x41 is unwanted tracking protection mode and is not the default: that
    mode also requires the UTP flag and a fixed address, which this tag
    does not implement.
    """
    if len(eid) != EID_LEN:
        raise ValueError("EID must be 20 bytes")
    if not 0 <= hashed_flags_byte <= 0xFF or not 0 <= frame_type <= 0xFF:
        raise ValueError("frame type and hashed flags must be bytes")
    service = bytes([frame_type]) + eid + bytes([hashed_flags_byte])
    # length covers type + uuid + service payload
    service_ad = bytes([1 + 2 + len(service), 0x16, 0xAA, 0xFE]) + service
    return bytes([0x02, 0x01, 0x06]) + service_ad


def _c_bytes(data: bytes, indent: str = "    ") -> str:
    lines = []
    for offset in range(0, len(data), 8):
        chunk = data[offset : offset + 8]
        lines.append(indent + ", ".join(f"0x{b:02x}" for b in chunk) + ",")
    return "\n".join(lines)


def render_c_header(slots: list[EidSlot], k: int = ROTATION_EXPONENT) -> str:
    if not slots:
        raise ValueError("refusing to emit an empty EID table")
    rows = []
    for slot in slots:
        rows.append("    {\n" + _c_bytes(slot.eid, "        ") + "\n    },")
    xor_rows = []
    for offset in range(0, len(slots), 8):
        chunk = slots[offset : offset + 8]
        xor_rows.append("    " + ", ".join(f"0x{s.flag_xor:02x}" for s in chunk) + ",")
    return f"""\
/* Generated by tools/fmdn_keys.py. Do not edit by hand.
 * Find Hub Network accessory spec, EID computation (SECP160R1, K={k}).
 * The ephemeral identity key is not stored here. flag_xor is the least
 * significant byte of SHA256(r aligned to 160 bits). Advertised hashed
 * flags = clear_flags XOR flag_xor. clear_flags 0 means battery indication
 * unsupported and unwanted-tracking-protection clear.
 * Slot i is the window starting at {slots[0].masked_timestamp}
 * (uint32 beacon time counter, low {k} bits already clear), step {1 << k}s.
 */
#ifndef FMDN_EID_TABLE_H
#define FMDN_EID_TABLE_H

#include <stdint.h>

#define FMDN_ROTATION_EXPONENT {k}
#define FMDN_EID_LEN {EID_LEN}
#define FMDN_EID_COUNT {len(slots)}
#define FMDN_TABLE_START_TS {slots[0].masked_timestamp}u
#define FMDN_TABLE_STEP_SEC {(1 << k)}u

static const uint8_t fmdn_eid[FMDN_EID_COUNT][FMDN_EID_LEN] = {{
{chr(10).join(rows)}
}};

static const uint8_t fmdn_flag_xor[FMDN_EID_COUNT] = {{
{chr(10).join(xor_rows)}
}};

#endif /* FMDN_EID_TABLE_H */
"""


def parse_eik(text: str) -> bytes:
    cleaned = text.strip().lower().replace("0x", "").replace(" ", "").replace(":", "")
    try:
        raw = bytes.fromhex(cleaned)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"EIK is not hex: {exc}") from exc
    if len(raw) != EIK_LEN:
        raise argparse.ArgumentTypeError(f"EIK must be {EIK_LEN} bytes ({EIK_LEN * 2} hex chars), got {len(raw)}")
    return raw


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit a C header of FMDN EIDs (SECP160R1, K=10).")
    parser.add_argument("--eik", required=True, type=parse_eik, help="32-byte ephemeral identity key, hex")
    parser.add_argument("--count", type=int, default=PLACEHOLDER_COUNT, help="number of rotation windows")
    parser.add_argument("--start", type=int, default=0, help="beacon time counter (seconds) for slot 0")
    parser.add_argument("--k", type=int, default=ROTATION_EXPONENT, help="rotation exponent (spec fixes this at 10)")
    parser.add_argument("--out", help="header path (default: stdout)")
    args = parser.parse_args(argv)
    if args.count < 1 or args.count > 2048:
        parser.error("count must be 1..2048")
    if args.k != ROTATION_EXPONENT:
        parser.error(f"spec fixes K={ROTATION_EXPONENT}; refusing K={args.k}")
    slots = compute_table(args.eik, args.count, args.start, args.k)
    header = render_c_header(slots, args.k)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(header)
        print(f"wrote {args.count} EIDs to {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(header)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
