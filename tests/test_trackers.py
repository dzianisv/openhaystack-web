"""Unit tests for the shared lib.trackers module.

No network: openhaybike.locations.get_locations_of_trackers is monkeypatched.
"""

import os
import sys
import unittest
from dataclasses import dataclass
from datetime import datetime
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import trackers as trackers_mod  # noqa: E402
from openhaybike.types import BikeTracker  # noqa: E402


@dataclass
class FakeLocation:
    lat: float
    lng: float

    def serialize(self):
        return {
            "lat": self.lat,
            "lng": self.lng,
            "accuracy": 10,
            "reported_at": int(datetime(2024, 1, 1).timestamp()),
        }


VALID = [
    {"name": "bike", "key_id": "kid-1", "private_key": "pk-1"},
    {"name": "car", "key_id": "kid-2", "private_key": "pk-2"},
]


class BuildTrackersTest(unittest.TestCase):
    def test_fields_mapped(self):
        built = trackers_mod.build_trackers(VALID)
        self.assertEqual(
            built,
            [
                BikeTracker(name="bike", key_id="kid-1", advertisement_key="", private_key="pk-1"),
                BikeTracker(name="car", key_id="kid-2", advertisement_key="", private_key="pk-2"),
            ],
        )

    def test_name_defaults_to_key_id(self):
        built = trackers_mod.build_trackers([{"key_id": "kid-9", "private_key": "pk"}])
        self.assertEqual(built[0].name, "kid-9")

    def test_advertisement_key_passed_through_when_present(self):
        built = trackers_mod.build_trackers(
            [{"key_id": "k", "private_key": "p", "advertisement_key": "adv"}]
        )
        self.assertEqual(built[0].advertisement_key, "adv")


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
            trackers_mod.validate_tracker_list([{"key_id": "a"}])
        self.assertIn("private_key", str(ctx.exception))

    def test_missing_icloud_key_raises(self):
        with self.assertRaises(ValueError):
            trackers_mod.get_tracker_locations(VALID, "")


class GetTrackerLocationsTest(unittest.TestCase):
    def _run(self, reports, **kwargs):
        with mock.patch.object(
            trackers_mod, "get_locations_of_trackers", return_value=reports
        ) as stub:
            result = trackers_mod.get_tracker_locations(VALID, "icloud-key", **kwargs)
        return result, stub

    def test_return_shape(self):
        result, _ = self._run({"bike": [FakeLocation(1.5, 2.5)], "car": []})
        self.assertEqual(
            result,
            {
                "bike": [
                    {
                        "lat": 1.5,
                        "lng": 2.5,
                        "accuracy": 10,
                        "reported_at": int(datetime(2024, 1, 1).timestamp()),
                    }
                ],
                "car": [],
            },
        )

    def test_default_hours_is_24(self):
        _, stub = self._run({})
        args = stub.call_args[0]
        self.assertEqual(args[1], "icloud-key")
        self.assertEqual(args[2], 24)

    def test_hours_forwarded(self):
        _, stub = self._run({}, hours=6)
        self.assertEqual(stub.call_args[0][2], 6)

    def test_bike_trackers_passed_to_openhaybike(self):
        _, stub = self._run({})
        passed = stub.call_args[0][0]
        self.assertTrue(all(isinstance(t, BikeTracker) for t in passed))
        self.assertEqual([t.key_id for t in passed], ["kid-1", "kid-2"])
        self.assertEqual([t.private_key for t in passed], ["pk-1", "pk-2"])
        self.assertEqual([t.advertisement_key for t in passed], ["", ""])


if __name__ == "__main__":
    unittest.main()
