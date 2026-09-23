#!/usr/bin/env python3
"""Convert ``trackers.json`` into an OpenTagViewer import bundle.

OpenTagViewer (https://github.com/parawanderer/OpenTagViewer, MIT) is an
Android app that talks to Apple's Find My network entirely on the phone: it
downloads Apple's ADI libraries from Apple's own CDN at runtime and generates
anisette locally, so it needs no server, no Mac and no companion process. It
imports self-generated (non-Apple) tags as ``custom_rolling_key_accessory``
records, which is exactly what an OpenHaystack tag is.

This tool is the bridge: it turns the tracker list this repository already
uses into a bundle that app can import.

**The bundle layout is not reimplemented here.** It is built by OpenTagViewer's
own exporter (``opentagviewer_export.bundle``), because the format has several
details that are correct-looking when wrong -- ``KeyAlignmentRecords`` is plural
where its siblings are singular, every file is ``.plist`` even where macOS names
it ``.record``, and the plists must be XML because the importer reads them with
XPath. A hand-rolled copy would import cleanly and silently lose tags. Using the
upstream writer means the format is whatever upstream says it is.

Install the exporter first. It is **not on PyPI**, and its ``pyproject.toml``
sets ``package = false``, so ``pip install`` from git does not work either --
clone the repository and point this tool at its ``python/`` directory::

    git clone --depth 1 https://github.com/parawanderer/OpenTagViewer.git
    pip install pyyaml
    python tools/export_opentagviewer.py trackers.json \
        --exporter-path OpenTagViewer/python \
        -o ~/openhaystack-tags.zip

``OPENHAYSTACK_OTV_EXPORTER`` sets the same path if you would rather not pass
the flag every time.

The upstream module is used rather than vendored on purpose: vendoring would
pin us to a snapshot of a format that upstream still changes, and the copy
would keep passing its own tests on the day the real format moved.

The output contains tracker **private keys**. It is written 0600, and anyone
holding it can locate your tags -- transfer it to the phone the way you would
transfer an SSH key, and delete it afterwards.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import sys
import zipfile
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.trackers import validate_tracker_list  # noqa: E402

# Apple's Find My private keys are P-224 scalars: 28 bytes. FindMy.py's KeyPair
# takes exactly that, and a wrong length here produces a bundle that imports and
# then never matches a report, which is indistinguishable from a tag that is out
# of range. Fail loudly instead.
PRIVATE_KEY_BYTES = 28

EXPORT_VIA = "openhaystack-web:1"
SOURCE_USER = "local@openhaystack-web.invalid"

# Fixed rather than read from the clock so that re-exporting an unchanged
# tracker list produces an identical bundle; a file that changes every run is
# one nobody can diff to see whether anything really changed.
EXPORTED_AT_MS = 1_760_000_000_000

INSTALL_HINT = (
    "OpenTagViewer's exporter was not found.\n"
    "It is not on PyPI and its pyproject sets package = false, so pip cannot\n"
    "install it. Clone the repository and point this tool at its python/ dir:\n"
    "  git clone --depth 1 https://github.com/parawanderer/OpenTagViewer.git\n"
    "  pip install pyyaml\n"
    "  python tools/export_opentagviewer.py --exporter-path OpenTagViewer/python\n"
    "(or set OPENHAYSTACK_OTV_EXPORTER to that path)"
)


def add_exporter_to_path(exporter_path=None) -> None:
    """Put OpenTagViewer's ``python/`` directory on ``sys.path``.

    Prepended, not appended: if both a stale installed copy and a fresh clone
    are present, the explicitly chosen one has to win, otherwise the tool would
    silently write the older format.
    """
    candidate = exporter_path or os.environ.get("OPENHAYSTACK_OTV_EXPORTER")
    if not candidate:
        return
    resolved = Path(candidate).expanduser().resolve()
    if not (resolved / "opentagviewer_export" / "bundle.py").is_file():
        raise SystemExit(
            f"Error: {resolved} does not look like OpenTagViewer's python/ "
            "directory (no opentagviewer_export/bundle.py inside).\n\n"
            + INSTALL_HINT
        )
    sys.path.insert(0, str(resolved))


def _identifier_for(name: str, key_id: str) -> str:
    """Build a stable, filesystem-safe identifier for one tracker.

    Derived from ``key_id`` rather than the name so that renaming a tag does not
    create a second entry, and so two tags sharing a name stay distinct. The
    name is unusable directly: these are emoji strings, and the identifier ends
    up as a zip entry name.
    """
    stem = re.sub(r"[^A-Za-z0-9]", "", key_id)[:16]
    if not stem:
        raise ValueError(f"tracker {name!r} has a key_id with no usable characters")
    return f"openhaystack-{stem}"


def _private_key_bytes(tracker: dict, index: int) -> bytes:
    try:
        raw = base64.b64decode(tracker["private_key"], validate=True)
    except (binascii.Error, ValueError) as exc:
        # Never echo the key itself.
        raise ValueError(
            f"trackers[{index}] has a 'private_key' that is not valid base64: "
            f"{type(exc).__name__}"
        ) from None
    if len(raw) != PRIVATE_KEY_BYTES:
        raise ValueError(
            f"trackers[{index}] has a {len(raw)}-byte 'private_key'; "
            f"expected {PRIVATE_KEY_BYTES}"
        )
    return raw


def build_bundle_entries(trackers: List[dict], exporter_path=None) -> dict:
    """Return the zip entries for ``trackers`` as ``{name: bytes|str}``.

    Split out from file writing so it can be tested without touching the disk.
    """
    add_exporter_to_path(exporter_path)
    try:
        from findmy.accessory import FixedRollingKeyPairAccessory
        from opentagviewer_export.bundle import CustomAccessoryExport, build_export
    except ImportError as exc:
        raise SystemExit(f"{INSTALL_HINT}\n\n(import failed: {exc})") from None

    validate_tracker_list(trackers)
    if not trackers:
        raise ValueError("the tracker list is empty; there is nothing to export")

    exports = []
    for index, tracker in enumerate(trackers):
        key_id = tracker.get("key_id")
        if not key_id:
            # validate_tracker_list() allows key_id to be absent because it is
            # derivable, but the identifier has to be stable across exports, so
            # derive it the same way rather than falling back to the name.
            from findmy import KeyPair

            key_id = KeyPair.from_b64(tracker["private_key"]).hashed_adv_key_b64
        name = tracker.get("name") or key_id
        accessory = FixedRollingKeyPairAccessory(
            private_keys=[_private_key_bytes(tracker, index)],
            name=name,
            identifier=_identifier_for(name, key_id),
        )
        exports.append(CustomAccessoryExport(mapping=accessory.to_json()))

    bundle = build_export(
        exports,
        via=EXPORT_VIA,
        source_user=SOURCE_USER,
        exported_at_ms=EXPORTED_AT_MS,
    )
    return bundle.entries


def write_bundle(entries: dict, destination: Path) -> None:
    """Write ``entries`` to ``destination`` as a 0600 zip.

    Created via ``os.open`` with the mode applied at creation time: writing the
    file first and chmod-ing after leaves a window in which a file full of
    tracker private keys is world-readable.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as raw:
        with zipfile.ZipFile(raw, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in sorted(entries.items()):
                archive.writestr(name, content)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Convert trackers.json into an OpenTagViewer import bundle.",
        epilog=(
            "The output contains tracker private keys. Treat it like an SSH "
            "private key: transfer it to the phone over a channel you trust, "
            "import it, then delete it from both machines."
        ),
    )
    parser.add_argument(
        "trackers",
        nargs="?",
        default="trackers.json",
        help="Path to the tracker list (default: trackers.json)",
    )
    parser.add_argument(
        "--exporter-path",
        default=None,
        metavar="PATH",
        help="Path to OpenTagViewer's python/ directory (a clone of "
        "github.com/parawanderer/OpenTagViewer). Defaults to "
        "$OPENHAYSTACK_OTV_EXPORTER.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="opentagviewer-import.zip",
        help="Where to write the bundle (default: opentagviewer-import.zip)",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    source = Path(args.trackers)
    try:
        trackers = json.loads(source.read_text(encoding="utf8"))
    except OSError as exc:
        print(f"Error: cannot read {source}: {exc.strerror}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Error: {source} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    try:
        entries = build_bundle_entries(trackers, args.exporter_path)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    destination = Path(args.output).expanduser()
    write_bundle(entries, destination)

    print(f"Wrote {destination} (mode 0600) with {len(trackers)} tracker(s):")
    for tracker in trackers:
        print(f"  - {tracker.get('name') or tracker.get('key_id')}")
    print(
        "\nNext: install OpenTagViewer on the Android phone "
        "(https://github.com/parawanderer/OpenTagViewer/releases), sign in with "
        "your Apple ID, then import this file.\n"
        "It holds private keys - delete it from both machines once imported."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
