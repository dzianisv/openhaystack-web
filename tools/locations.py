#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

# Allow running the script from any working directory, not just the repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib import findmy_backend
from lib.trackers import get_tracker_locations, validate_tracker_list

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
        trackers.append(tracker)

    try:
        return validate_tracker_list(trackers)
    except ValueError as error:
        raise ValueError(f"Config file '{config_path}': {error}") from None


def main(argv=None):
    args = parse_args(argv)

    try:
        trackers = load_trackers(args.config)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    try:
        reports = get_tracker_locations(trackers, args.hours)
    except findmy_backend.AccountNotConfiguredError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except findmy_backend.AccountStateError as error:
        print(
            f"Error: the saved Apple session is unusable ({error}). "
            "Run `python tools/findmy_login.py --force` to sign in again.",
            file=sys.stderr,
        )
        return 1
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    if args.format == "raw":
        print(reports)
    else:
        print(json.dumps(reports, indent=4))
    return 0


if __name__ == "__main__":
    sys.exit(main())
