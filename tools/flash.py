#!/usr/bin/env python3

import sys
import base64
import binascii
import os
import tempfile
import subprocess
import argparse
import json
from pathlib import Path

import keygen

PLACEHOLDER = b"OFFLINEFINDINGPUBLICKEYHERE!"
FIRMWARE_PATH = Path(__file__).resolve().parent.parent / "firmware" / "nrf51.bin"


def decode_advertisement_key(advertisement_key: str) -> bytes:
    try:
        advertisement_key_bin = base64.b64decode(advertisement_key, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError(f"Invalid advertisement key: not valid base64 ({error})") from None

    if len(advertisement_key_bin) != len(PLACEHOLDER):
        raise ValueError(
            f"Invalid advertisement key length. Expected {len(PLACEHOLDER)}, "
            f"provided key length is {len(advertisement_key_bin)}"
        )
    return advertisement_key_bin


def patch_firmware(data: bytes, advertisement_key_bin: bytes) -> bytes:
    """Replace the advertisement key placeholder with the raw key bytes.

    Uses a literal bytes replacement: re.sub() would interpret backslash bytes
    (0x5C) in the binary key as regex escapes, crashing or silently corrupting
    the flashed key.
    """
    if len(advertisement_key_bin) != len(PLACEHOLDER):
        raise ValueError(
            f"Invalid advertisement key length. Expected {len(PLACEHOLDER)}, "
            f"provided key length is {len(advertisement_key_bin)}"
        )

    occurrences = data.count(PLACEHOLDER)
    if occurrences == 0:
        raise ValueError("Invalid firmware file. Advertisement key placeholder is not found")
    if occurrences > 1:
        raise ValueError(
            f"Invalid firmware file. Advertisement key placeholder found {occurrences} times, expected exactly 1"
        )

    patched_firmware_bin = data.replace(PLACEHOLDER, advertisement_key_bin)

    if len(patched_firmware_bin) != len(data):
        raise ValueError(
            f"Firmware patching changed the image size ({len(data)} -> {len(patched_firmware_bin)})"
        )
    if PLACEHOLDER in patched_firmware_bin:
        raise ValueError("Firmware patching failed: advertisement key placeholder is still present")
    if advertisement_key_bin not in patched_firmware_bin:
        raise ValueError("Firmware patching failed: advertisement key bytes are not present in the patched image")

    return patched_firmware_bin


def flash(advertisement_key: str) -> int:
    advertisement_key_bin = decode_advertisement_key(advertisement_key)

    with open(FIRMWARE_PATH, "rb") as src_firmware, \
        tempfile.NamedTemporaryFile("wb", delete=True) as dst_firmware:
        data = src_firmware.read()
        patched_firmware_bin = patch_firmware(data, advertisement_key_bin)
        dst_firmware.write(patched_firmware_bin)
        # openocd reads this file by name, so the buffer must hit the disk first
        dst_firmware.flush()
        os.fsync(dst_firmware.fileno())

        result = subprocess.run([
            'openocd',
            '-f', 'interface/stlink-v2.cfg',
            '-f', 'target/nrf51.cfg',
            '-c', f'init; halt; nrf51 mass_erase; program {dst_firmware.name} verify; program {dst_firmware.name}; exit;'
        ])

        if result.returncode != 0:
            print(f"openocd failed with exit code {result.returncode}", file=sys.stderr)
        return result.returncode

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Flash the firmware')
    parser.add_argument('--advertisement-key', type=str, help='Key ID to flash')
    args = parser.parse_args()

    advertisement_key = args.advertisement_key 
    if advertisement_key is None:
        keys = keygen.generate_keys()
        print(json.dumps(keys.__dict__, indent=4))
        advertisement_key = keys.advertisement_key

    try:
        sys.exit(flash(advertisement_key))
    except (ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
