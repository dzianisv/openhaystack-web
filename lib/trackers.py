"""Shared tracker-location lookup.

This module is the single implementation used by both entry points
(``app.py``, the Eel desktop app, and ``backend/app.py``, the Sanic HTTP
service). It must stay free of any web-framework import (eel/sanic) so both
can use it and so it is unit-testable without a browser or an event loop.
"""

import logging
from typing import Any, Dict, List

from openhaybike.types import BikeTracker
from openhaybike.locations import get_locations_of_trackers

DEFAULT_WITHIN_LAST_HOURS = 24

logger = logging.getLogger(__name__)


def validate_tracker_list(trackers: Any) -> List[dict]:
    """Return ``trackers`` unchanged, or raise ValueError with a user-facing message.

    Only the fields openhaybike actually consumes are required: ``key_id``
    (used to address Apple's fetch endpoint) and ``private_key`` (used to
    decrypt the reports). ``name`` is optional and ``advertisement_key`` is
    never read by openhaybike.
    """
    if not isinstance(trackers, list):
        raise ValueError("'trackers' must be a list")
    for index, tracker in enumerate(trackers):
        if not isinstance(tracker, dict):
            raise ValueError(f"trackers[{index}] must be an object")
        for field in ("key_id", "private_key"):
            if not tracker.get(field):
                raise ValueError(f"trackers[{index}] is missing '{field}'")
    return trackers


def build_trackers(trackers: List[dict]) -> List[BikeTracker]:
    """Map plain dicts from the frontend/HTTP body onto BikeTracker objects.

    ``advertisement_key`` is passed through when present and defaults to ""
    because ``openhaybike.locations.get_locations_of_trackers`` never reads it
    - lookups key off ``key_id`` and decrypt off ``private_key``.

    ``name`` falls back to ``key_id`` because openhaybike uses ``tracker.name``
    as the key of the results dict: a missing name would key every unnamed
    tracker under the same ``None`` bucket and serialize as ``"null"`` to the
    frontend.
    """
    return [
        BikeTracker(
            name=tracker.get("name") or tracker.get("key_id"),
            key_id=tracker.get("key_id"),
            advertisement_key=tracker.get("advertisement_key") or "",
            private_key=tracker.get("private_key"),
        )
        for tracker in trackers
    ]


def get_tracker_locations(
    trackers: List[dict],
    icloud_key: str,
    hours: float = DEFAULT_WITHIN_LAST_HOURS,
) -> Dict[str, List[Dict[str, Any]]]:
    """Fetch location reports and return ``{tracker_name: [serialized, ...]}``.

    Blocking network I/O; callers on an event loop must run it in a thread.
    """
    if not icloud_key:
        raise ValueError("An iCloud key is required to query Apple's location service")

    validate_tracker_list(trackers)
    bike_trackers = build_trackers(trackers)

    # Never log private keys.
    logger.debug(
        "fetching locations for %d tracker(s) over the last %s hours: %s",
        len(bike_trackers),
        hours,
        [tracker.name for tracker in bike_trackers],
    )

    reports = get_locations_of_trackers(bike_trackers, icloud_key, hours)
    return {
        name: [location.serialize() for location in locations]
        for name, locations in reports.items()
    }
