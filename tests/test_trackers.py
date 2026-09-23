"""Unit tests for lib.trackers and lib.findmy_backend.

No network and no Apple authentication: AppleAccount is replaced by a fake.
The only real crypto used is KeyPair, which is purely local.
"""

import json
import os
import stat
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from findmy import KeyPair  # noqa: E402

from lib import findmy_backend  # noqa: E402
from lib import trackers as trackers_mod  # noqa: E402

# The user's real, already-flashed tag. Regression guard: these exact values
# were burned into the firmware, so KeyPair must keep reproducing them.
REAL_PRIVATE_KEY = "ITZhulzcTqgnsVSfsbqBJ5Xj0l44CDie1Foh3g=="
REAL_ADV_KEY = "LSloFAaecds6QifRdqPBmT4WpqI1ulKPtONH7A=="
REAL_KEY_ID = "AxYe7WPcm5hY9tRw3BvNIfaSxxoefDba1+AVlq0CR8k="

SECOND_PRIVATE_KEY = KeyPair.new().private_key_b64
SECOND_KEY_ID = KeyPair.from_b64(SECOND_PRIVATE_KEY).hashed_adv_key_b64

VALID = [
    {"name": "bike", "key_id": REAL_KEY_ID, "private_key": REAL_PRIVATE_KEY},
    {"name": "car", "key_id": SECOND_KEY_ID, "private_key": SECOND_PRIVATE_KEY},
]


class FakeReport:
    """Stand-in for findmy.LocationReport (only the fields we serialize)."""

    def __init__(self, lat, lng, accuracy, timestamp):
        self.latitude = lat
        self.longitude = lng
        self.horizontal_accuracy = accuracy
        self.timestamp = timestamp


class FakeAccount:
    """Stand-in for AppleAccount: records the keys it was asked about."""

    def __init__(self, reports_by_key_id=None):
        self._reports = reports_by_key_id or {}
        self.requested = None
        self.closed = False

    def fetch_location_history(self, keys):
        self.requested = list(keys)
        return {key: list(self._reports.get(key.hashed_adv_key_b64, [])) for key in keys}

    def close(self):
        self.closed = True


class KeyCompatibilityTest(unittest.TestCase):
    """Existing flashed tags must keep working with FindMy.py."""

    def test_adv_key_matches_flashed_value(self):
        self.assertEqual(KeyPair.from_b64(REAL_PRIVATE_KEY).adv_key_b64, REAL_ADV_KEY)

    def test_hashed_adv_key_matches_flashed_key_id(self):
        self.assertEqual(KeyPair.from_b64(REAL_PRIVATE_KEY).hashed_adv_key_b64, REAL_KEY_ID)


class ValidationTest(unittest.TestCase):
    def test_accepts_empty_list(self):
        self.assertEqual(trackers_mod.validate_tracker_list([]), [])

    def test_rejects_non_list(self):
        with self.assertRaises(ValueError):
            trackers_mod.validate_tracker_list({"key_id": "a"})

    def test_rejects_non_dict_entry(self):
        with self.assertRaises(ValueError):
            trackers_mod.validate_tracker_list(["nope"])

    def test_rejects_missing_private_key(self):
        with self.assertRaises(ValueError) as ctx:
            trackers_mod.validate_tracker_list([{"key_id": REAL_KEY_ID}])
        self.assertIn("private_key", str(ctx.exception))

    def test_rejects_unparsable_private_key(self):
        with self.assertRaises(ValueError) as ctx:
            trackers_mod.validate_tracker_list([{"private_key": "not-a-key"}])
        self.assertIn("private_key", str(ctx.exception))

    def test_key_id_optional(self):
        self.assertEqual(
            trackers_mod.validate_tracker_list([{"private_key": REAL_PRIVATE_KEY}]),
            [{"private_key": REAL_PRIVATE_KEY}],
        )

    def test_rejects_key_id_inconsistent_with_private_key(self):
        with self.assertRaises(ValueError) as ctx:
            trackers_mod.validate_tracker_list(
                [{"key_id": SECOND_KEY_ID, "private_key": REAL_PRIVATE_KEY}]
            )
        self.assertIn("key_id", str(ctx.exception))

    def test_rejects_advertisement_key_inconsistent_with_private_key(self):
        with self.assertRaises(ValueError) as ctx:
            trackers_mod.validate_tracker_list(
                [{"private_key": REAL_PRIVATE_KEY, "advertisement_key": "bogus"}]
            )
        self.assertIn("advertisement_key", str(ctx.exception))


class BuildTrackersTest(unittest.TestCase):
    def test_fields_mapped(self):
        built = trackers_mod.build_trackers(VALID)
        self.assertEqual([t.name for t in built], ["bike", "car"])
        self.assertEqual([t.key_id for t in built], [REAL_KEY_ID, SECOND_KEY_ID])
        self.assertEqual(built[0].key.private_key_b64, REAL_PRIVATE_KEY)

    def test_name_defaults_to_key_id_not_none(self):
        built = trackers_mod.build_trackers(
            [{"key_id": REAL_KEY_ID, "private_key": REAL_PRIVATE_KEY}]
        )
        self.assertEqual(built[0].name, REAL_KEY_ID)
        self.assertIsNotNone(built[0].name)

    def test_key_id_derived_when_absent(self):
        built = trackers_mod.build_trackers([{"private_key": REAL_PRIVATE_KEY}])
        self.assertEqual(built[0].key_id, REAL_KEY_ID)
        self.assertEqual(built[0].name, REAL_KEY_ID)


class GetTrackerLocationsTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)

    def test_return_shape(self):
        ts = self.now - timedelta(minutes=5)
        account = FakeAccount({REAL_KEY_ID: [FakeReport(1.5, 2.5, 10, ts)]})
        result = trackers_mod.get_tracker_locations(VALID, account=account)
        self.assertEqual(
            result,
            {
                "bike": [
                    {
                        "lat": 1.5,
                        "lng": 2.5,
                        "accuracy": 10,
                        "reported_at": int(ts.timestamp()),
                    }
                ],
                "car": [],
            },
        )
        self.assertIsInstance(result["bike"][0]["reported_at"], int)

    def test_hours_filter_drops_old_reports(self):
        recent = FakeReport(1.0, 1.0, 5, self.now - timedelta(hours=1))
        old = FakeReport(2.0, 2.0, 5, self.now - timedelta(hours=48))
        account = FakeAccount({REAL_KEY_ID: [old, recent]})

        result = trackers_mod.get_tracker_locations(VALID, account=account)
        self.assertEqual([p["lat"] for p in result["bike"]], [1.0])

        result = trackers_mod.get_tracker_locations(VALID, hours=72, account=account)
        self.assertEqual([p["lat"] for p in result["bike"]], [2.0, 1.0])

    def test_hours_boundary_with_non_utc_aware_timestamps(self):
        other_tz = timezone(timedelta(hours=-7))
        inside = FakeReport(1.0, 1.0, 5, (self.now - timedelta(hours=23)).astimezone(other_tz))
        outside = FakeReport(2.0, 2.0, 5, (self.now - timedelta(hours=25)).astimezone(other_tz))
        account = FakeAccount({REAL_KEY_ID: [inside, outside]})
        result = trackers_mod.get_tracker_locations(VALID, hours=24, account=account)
        self.assertEqual([p["lat"] for p in result["bike"]], [1.0])

    def test_naive_timestamp_is_not_compared_against_aware(self):
        naive = FakeReport(3.0, 3.0, 5, datetime.now().replace(tzinfo=None))
        account = FakeAccount({REAL_KEY_ID: [naive]})
        result = trackers_mod.get_tracker_locations(VALID, hours=24, account=account)
        self.assertEqual([p["lat"] for p in result["bike"]], [3.0])

    def test_hours_none_disables_filtering(self):
        old = FakeReport(2.0, 2.0, 5, self.now - timedelta(days=30))
        account = FakeAccount({REAL_KEY_ID: [old]})
        result = trackers_mod.get_tracker_locations(VALID, hours=None, account=account)
        self.assertEqual(len(result["bike"]), 1)

    def test_unnamed_trackers_key_on_key_id(self):
        account = FakeAccount({})
        result = trackers_mod.get_tracker_locations(
            [
                {"private_key": REAL_PRIVATE_KEY},
                {"private_key": SECOND_PRIVATE_KEY},
            ],
            account=account,
        )
        self.assertEqual(sorted(result), sorted([REAL_KEY_ID, SECOND_KEY_ID]))
        self.assertNotIn(None, result)

    def test_inconsistent_key_id_rejected(self):
        account = FakeAccount({})
        with self.assertRaises(ValueError):
            trackers_mod.get_tracker_locations(
                [{"key_id": SECOND_KEY_ID, "private_key": REAL_PRIVATE_KEY}],
                account=account,
            )

    def test_keypairs_are_passed_to_the_account(self):
        account = FakeAccount({})
        trackers_mod.get_tracker_locations(VALID, account=account)
        self.assertTrue(all(isinstance(k, KeyPair) for k in account.requested))
        self.assertEqual(
            [k.hashed_adv_key_b64 for k in account.requested],
            [REAL_KEY_ID, SECOND_KEY_ID],
        )

    def test_empty_tracker_list_does_not_touch_the_account(self):
        with mock.patch.object(findmy_backend, "account_session") as session:
            self.assertEqual(trackers_mod.get_tracker_locations([]), {})
        session.assert_not_called()

    def test_loads_cached_session_when_no_account_given(self):
        account = FakeAccount({REAL_KEY_ID: [FakeReport(9.0, 9.0, 1, self.now)]})
        with mock.patch.object(findmy_backend, "load_account", return_value=account), \
                mock.patch.object(findmy_backend, "close_account") as close:
            result = trackers_mod.get_tracker_locations(VALID)
        self.assertEqual(result["bike"][0]["lat"], 9.0)
        close.assert_called_once_with(account)


class AccountFileTest(unittest.TestCase):
    def test_paths_respect_xdg_and_env_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}, clear=False):
                os.environ.pop(findmy_backend.ACCOUNT_FILE_ENV, None)
                os.environ.pop(findmy_backend.ANISETTE_LIBS_ENV, None)
                self.assertEqual(
                    findmy_backend.account_file_path(),
                    findmy_backend.Path(tmp) / "openhaystack-web" / "account.json",
                )
            override = os.path.join(tmp, "custom.json")
            with mock.patch.dict(os.environ, {findmy_backend.ACCOUNT_FILE_ENV: override}):
                self.assertEqual(str(findmy_backend.account_file_path()), override)
                self.assertEqual(
                    str(findmy_backend.anisette_libs_path()),
                    os.path.join(tmp, "anisette-libs.bin"),
                )

    def test_state_file_written_0600_in_0700_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = findmy_backend.Path(tmp) / "cfg" / "account.json"
            state = {"type": "account", "account": {"name": "someone@example.com"}}
            account = mock.Mock()
            account.to_json.return_value = state

            written = findmy_backend.save_account(account, path)

            self.assertEqual(written, path)
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(os.stat(path.parent).st_mode), 0o700)
            self.assertEqual(json.loads(path.read_text()), state)
            account.to_json.assert_called_once_with()

    def test_atomic_write_overwrites_and_leaves_no_temp_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = findmy_backend.Path(tmp) / "account.json"
            findmy_backend.atomic_write_secret(path, "one")
            findmy_backend.atomic_write_secret(path, "two")
            self.assertEqual(path.read_text(), "two")
            self.assertEqual(os.listdir(tmp), ["account.json"])

    def test_load_account_without_file_names_the_login_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = findmy_backend.Path(tmp) / "account.json"
            self.assertFalse(findmy_backend.has_account(path))
            with self.assertRaises(findmy_backend.AccountNotConfiguredError) as ctx:
                findmy_backend.load_account(path)
            self.assertIn("tools/findmy_login.py", str(ctx.exception))

    def test_load_account_with_corrupt_file_raises_state_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = findmy_backend.Path(tmp) / "account.json"
            findmy_backend.atomic_write_secret(path, "{not json")
            with self.assertRaises(findmy_backend.AccountStateError):
                findmy_backend.load_account(path)

    def test_close_account_tolerates_sync_close(self):
        account = FakeAccount({})
        findmy_backend.close_account(account)
        self.assertTrue(account.closed)


if __name__ == "__main__":
    unittest.main()
