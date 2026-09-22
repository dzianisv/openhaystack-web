#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

# Allow running the script from any working directory, not just the repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.icloud import get_icloud_key_cached
from openhaybike.types import BikeTracker
from openhaybike.locations import get_locations_of_trackers

DEFAULT_CONFIG = "trackers.json"
DEFAULT_HOURS = 24.0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Fetch the latest reported locations of OpenHaystack trackers."
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
        type=str,
        help="Path to the trackers JSON file (alternative to the positional argument)",
    )
    parser.add_argument(
        "--hours",
        default=DEFAULT_HOURS,
        type=float,
        help=f"How many hours back to search for reports (default: {DEFAULT_HOURS:g})",
    )
    parser.add_argument(
        "--format",
        choices=("json", "raw"),
        default="json",
        help="Output format: 'json' (default) or 'raw' python repr (legacy)",
    )
    args = parser.parse_args(argv)

    if args.config_option is not None and args.config_path is not None:
        parser.error(
            "config file given twice: positional "
            f"'{args.config_path}' and --config '{args.config_option}'. Use only one."
        )
    if args.hours <= 0:
        parser.error("--hours must be greater than 0")

    args.config = args.config_option or args.config_path or DEFAULT_CONFIG
    return args


def load_trackers(config_path):
    """Read and validate the trackers config, raising ValueError on bad input."""
    try:
        with open(config_path, "r", encoding="utf8") as f:
            keys = json.load(f)
    except FileNotFoundError:
        raise ValueError(
            f"Config file '{config_path}' not found. "
            "Create it (see README) or pass a path, e.g. ./tools/locations.py mytrackers.json"
        ) from None
    except OSError as error:
        raise ValueError(f"Cannot read config file '{config_path}': {error}") from None
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Config file '{config_path}' is not valid JSON: {error}"
        ) from None

    if isinstance(keys, dict):
        keys = [keys]
    if not isinstance(keys, list):
        raise ValueError(
            f"Config file '{config_path}' must contain a JSON object or a list of objects, "
            f"got {type(keys).__name__}"
        )
    if not keys:
        raise ValueError(f"Config file '{config_path}' contains no trackers")

    trackers = []
    for index, tracker in enumerate(keys):
        if not isinstance(tracker, dict):
            raise ValueError(
                f"Config file '{config_path}': entry #{index} must be a JSON object, "
                f"got {type(tracker).__name__}"
            )
        for field in ("key_id", "private_key"):
            value = tracker.get(field)
            if not isinstance(value, str) or not value.strip():
                label = tracker.get("name") or tracker.get("key_id") or f"#{index}"
                raise ValueError(
                    f"Config file '{config_path}': entry {label} (index {index}) "
                    f"is missing a non-empty '{field}'"
                )
        trackers.append(
            BikeTracker(
                name=tracker.get("name", tracker.get("key_id")),
                key_id=tracker.get("key_id"),
                advertisement_key=tracker.get("advertisement_key"),
                private_key=tracker.get("private_key"),
            )
        )
    return trackers


def main(argv=None):
    args = parse_args(argv)

    try:
        trackers = load_trackers(args.config)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    try:
        icloud_key = get_icloud_key_cached()
    except (ValueError, TypeError, OSError, IndexError, KeyError) as error:
        print(
            "Error: failed to retrieve the iCloud key (incorrect keychain password?): "
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1

    reports = get_locations_of_trackers(trackers, icloud_key, args.hours)

    if args.format == "raw":
        print(reports)
    else:
        print(json.dumps(
            {name: [location.serialize() for location in locations]
             for name, locations in reports.items()},
            indent=4,
        ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
