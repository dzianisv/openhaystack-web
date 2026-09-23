"""Unit tests for tools/export_opentagviewer.py.

No network and no Apple authentication. OpenTagViewer's exporter is not a
dependency of this repository, so the tests that need it are skipped unless a
clone is pointed at by ``OPENHAYSTACK_OTV_EXPORTER`` -- the rest exercise the
parts this repository actually owns: key decoding, identifier derivation, and
the permissions of a file full of private keys.
"""

import base64
import importlib.util
import os
import stat
import sys
import tempfile
import unittest
import unittest.mock
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from findmy import KeyPair  # noqa: E402


def _load_tool():
    spec = importlib.util.spec_from_file_location(
        "export_opentagviewer", REPO / "tools" / "export_opentagviewer.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


export_tool = _load_tool()

# A real 28-byte key, generated locally; never any of the author's tags.
SAMPLE_KEY = base64.b64encode(bytes(range(28))).decode()
SAMPLE_KEY_ID = KeyPair.from_b64(SAMPLE_KEY).hashed_adv_key_b64


class PrivateKeyBytesTest(unittest.TestCase):
    def test_decodes_a_valid_key(self):
        raw = export_tool._private_key_bytes({"private_key": SAMPLE_KEY}, 0)
        self.assertEqual(len(raw), export_tool.PRIVATE_KEY_BYTES)

    def test_rejects_non_base64(self):
        with self.assertRaises(ValueError) as ctx:
            export_tool._private_key_bytes({"private_key": "not base64!!"}, 3)
        self.assertIn("trackers[3]", str(ctx.exception))

    def test_rejects_a_wrong_length_key(self):
        """A short key would import fine and then silently match nothing."""
        short = base64.b64encode(b"\x01" * 16).decode()
        with self.assertRaises(ValueError) as ctx:
            export_tool._private_key_bytes({"private_key": short}, 1)
        self.assertIn("16-byte", str(ctx.exception))

    def test_error_never_contains_the_key(self):
        secret = base64.b64encode(b"\x02" * 16).decode()
        with self.assertRaises(ValueError) as ctx:
            export_tool._private_key_bytes({"private_key": secret}, 0)
        self.assertNotIn(secret, str(ctx.exception))


class IdentifierTest(unittest.TestCase):
    def test_is_derived_from_key_id_not_name(self):
        """Renaming a tag must not create a second entry on the phone."""
        first = export_tool._identifier_for("🐼 Den", SAMPLE_KEY_ID)
        second = export_tool._identifier_for("Something else", SAMPLE_KEY_ID)
        self.assertEqual(first, second)

    def test_is_filesystem_safe(self):
        """The identifier becomes a zip entry name, so emoji and / must go."""
        identifier = export_tool._identifier_for("🚗 minicooper", "a/b+c=dEF")
        self.assertTrue(identifier.startswith("openhaystack-"))
        self.assertRegex(identifier, r"^openhaystack-[A-Za-z0-9]+$")

    def test_distinct_keys_give_distinct_identifiers(self):
        other = KeyPair.from_b64(
            base64.b64encode(bytes(range(28, 56))).decode()
        ).hashed_adv_key_b64
        self.assertNotEqual(
            export_tool._identifier_for("x", SAMPLE_KEY_ID),
            export_tool._identifier_for("x", other),
        )

    def test_rejects_an_unusable_key_id(self):
        with self.assertRaises(ValueError):
            export_tool._identifier_for("x", "///+++")


class WriteBundleTest(unittest.TestCase):
    def test_is_created_0600(self):
        """It holds private keys; it must never exist world-readable, even briefly."""
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "nested" / "out.zip"
            export_tool.write_bundle({"OPENTAGVIEWER.yml": "version: 0.0.3\n"}, destination)
            mode = stat.S_IMODE(destination.stat().st_mode)
            self.assertEqual(mode, 0o600, f"expected 0600, got {mode:o}")

    def test_round_trips_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "out.zip"
            export_tool.write_bundle({"a.json": "{}", "OPENTAGVIEWER.yml": "x: 1\n"}, destination)
            with zipfile.ZipFile(destination) as archive:
                self.assertEqual(sorted(archive.namelist()), ["OPENTAGVIEWER.yml", "a.json"])

    def test_overwrites_an_existing_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "out.zip"
            export_tool.write_bundle({"a.json": "{}"}, destination)
            export_tool.write_bundle({"b.json": "{}"}, destination)
            with zipfile.ZipFile(destination) as archive:
                self.assertEqual(archive.namelist(), ["b.json"])


class ExporterPathTest(unittest.TestCase):
    def test_rejects_a_directory_that_is_not_the_exporter(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as ctx:
                export_tool.add_exporter_to_path(tmp)
            self.assertIn("opentagviewer_export", str(ctx.exception))

    def test_no_path_is_a_no_op(self):
        before = list(sys.path)
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            export_tool.add_exporter_to_path(None)
        self.assertEqual(sys.path, before)


@unittest.skipUnless(
    os.environ.get("OPENHAYSTACK_OTV_EXPORTER"),
    "set OPENHAYSTACK_OTV_EXPORTER to a clone of OpenTagViewer/python to run",
)
class BundleContentTest(unittest.TestCase):
    """End-to-end against the real upstream exporter, when one is available."""

    def test_produces_a_custom_accessory_bundle(self):
        entries = export_tool.build_bundle_entries(
            [{"name": "Test tag", "private_key": SAMPLE_KEY, "key_id": SAMPLE_KEY_ID}]
        )
        self.assertIn("OPENTAGVIEWER.yml", entries)
        metadata = entries["OPENTAGVIEWER.yml"]
        if isinstance(metadata, bytes):
            metadata = metadata.decode("utf8")
        # 0.0.3 is the version that can express a self-generated accessory;
        # an older one would import as "well-formed but carries no tags".
        self.assertIn("0.0.3", metadata)
        custom = [n for n in entries if n.startswith("CustomAccessories/")]
        self.assertEqual(len(custom), 1, entries.keys())

    def test_rejects_an_empty_tracker_list(self):
        with self.assertRaises(ValueError):
            export_tool.build_bundle_entries([])


if __name__ == "__main__":
    unittest.main()
