#!/usr/bin/env python3
"""Scan for nearby OpenHaystack tags over Bluetooth, without any Apple account.

This is the offline counterpart to tools/locations.py. It cannot tell you where
a tag is in the world -- only whether one is currently broadcasting within radio
range of this machine (roughly 10-50 m). It needs no Apple ID, no iCloud and no
network, so it is also the way to check that a tag is powered and advertising
before blaming the Find My lookup.

A tag separated from its owner broadcasts its full advertisement key, so those
can be matched against trackers.json by name. A tag that still considers itself
"nearby" its owner broadcasts only a truncated key and cannot be identified; it
is reported as an unidentified Find My device.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from findmy import OfflineFindingScanner  # noqa: E402

from lib.trackers import build_trackers  # noqa: E402

DEFAULT_CONFIG = "trackers.json"
DEFAULT_SECONDS = 30.0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Scan Bluetooth for OpenHaystack tags in radio range. "
            "Needs no Apple account, unlike tools/locations.py."
        )
    )
    parser.add_argument(
        "config_path",
        nargs="?",
        metavar="CONFIG",
        default=None,
        help=f"Path to the trackers JSON file (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--config",
        dest="config_option",
        metavar="CONFIG",
        default=None,
        help="Path to the trackers JSON file (alternative to the positional argument)",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=DEFAULT_SECONDS,
        help=f"How long to scan for (default: {DEFAULT_SECONDS:g})",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Also report Find My devices that are not in the config",
    )
    args = parser.parse_args(argv)
    if args.config_option is not None and args.config_path is not None:
        parser.error(
            "config file given twice: positional "
            f"'{args.config_path}' and --config '{args.config_option}'. Use only one."
        )
    if args.seconds <= 0:
        parser.error("--seconds must be greater than 0")
    args.config = args.config_option or args.config_path or DEFAULT_CONFIG
    return args


def load_known(config_path):
    """Return {hashed_adv_key_b64: name}, or {} if the config is absent."""
    path = Path(config_path)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read '{config_path}': {error}") from None
    if isinstance(raw, dict):
        raw = [raw]
    return {t.key_id: t.name for t in build_trackers(raw)}


async def scan(known, seconds, show_all):
    scanner = await OfflineFindingScanner.create()
    seen_known = {}
    unknown_separated = 0
    nearby = 0

    async for device in scanner.scan_for(seconds):
        key_id = getattr(device, "hashed_adv_key_b64", None)
        if key_id is None:
            # A "nearby" tag truncates its key, so it cannot be identified.
            nearby += 1
            if show_all:
                print(f"  unidentified Find My device  rssi={device.rssi:>4}  {device.mac_address}")
            continue
        name = known.get(key_id)
        if name is None:
            unknown_separated += 1
            if show_all:
                print(f"  other OpenHaystack tag       rssi={device.rssi:>4}  {device.mac_address}")
            continue
        best = seen_known.get(name)
        if best is None or device.rssi > best["rssi"]:
            seen_known[name] = {"rssi": device.rssi, "mac": device.mac_address}
        print(f"  FOUND {name!r}  rssi={device.rssi:>4} dBm  {device.mac_address}")

    return seen_known, unknown_separated, nearby


def describe_distance(rssi):
    if rssi >= -55:
        return "very close (same room)"
    if rssi >= -70:
        return "close (same floor)"
    if rssi >= -85:
        return "far (edge of range)"
    return "very far / barely audible"


def main(argv=None):
    args = parse_args(argv)

    try:
        known = load_known(args.config)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    if known:
        print(f"Scanning {args.seconds:g}s for {len(known)} configured tag(s): "
              + ", ".join(sorted(known.values())))
    else:
        print(f"Scanning {args.seconds:g}s (no config found at '{args.config}', "
              "reporting every Find My device)")
        args.all = True

    try:
        found, unknown, nearby = asyncio.run(scan(known, args.seconds, args.all))
    except Exception as error:  # noqa: BLE001 - surface Bluetooth errors readably
        print(
            f"Error: Bluetooth scan failed ({type(error).__name__}: {error}). "
            "Check that Bluetooth is on and that this terminal is allowed to use it "
            "(System Settings -> Privacy & Security -> Bluetooth).",
            file=sys.stderr,
        )
        return 1

    print()
    if found:
        for name in sorted(found):
            hit = found[name]
            print(f"{name}: in range, {describe_distance(hit['rssi'])} "
                  f"({hit['rssi']} dBm, {hit['mac']})")
    for name in sorted(set(known.values()) - set(found)):
        print(f"{name}: not in range")

    print(f"\nAlso saw {unknown} other OpenHaystack tag(s) and "
          f"{nearby} unidentifiable Find My device(s) in range.")
    if not found and known:
        print(
            "\nNone of your tags answered. Either they are out of range, or the "
            "battery is dead, or they are not advertising. This scan is local "
            "radio only -- use tools/locations.py for network-wide lookup."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
