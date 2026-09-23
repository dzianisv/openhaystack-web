"""Shared tracker-location lookup, backed by FindMy.py.

This module is the single implementation used by both entry points
(``app.py``, the Eel desktop app, and ``backend/app.py``, the Sanic HTTP
service). It must stay free of any web-framework import (eel/sanic) so both
can use it and so it is unit-testable without a browser or an event loop.

Authentication is no longer a macOS-keychain iCloud token: it is an Apple ID
session managed by :mod:`lib.findmy_backend` and created once by
``tools/findmy_login.py``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from findmy import KeyPair

from lib import findmy_backend

DEFAULT_WITHIN_LAST_HOURS = 24

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Tracker:
    """A tracker from the frontend config, resolved to a FindMy keypair.

    ``key_id`` is always the value derived from ``key`` (the base64 SHA-256 of
    the advertisement key), so it can never disagree with the key actually
    queried. ``name`` is never ``None``.
    """

    name: str
    key_id: str
    key: KeyPair


def _keypair_from_private_key(private_key: str, index: int) -> KeyPair:
    try:
        return KeyPair.from_b64(private_key)
    except Exception as exc:  # noqa: BLE001 - surface as a config error
        # Never include the key material itself in the message.
        raise ValueError(
            f"trackers[{index}] has an invalid 'private_key': {type(exc).__name__}"
        ) from exc


def validate_tracker_list(trackers: Any) -> List[dict]:
    """Return ``trackers`` unchanged, or raise ValueError with a user-facing message.

    ``private_key`` is required: it is the only field that cannot be derived,
    and FindMy.py needs it both to address Apple's endpoint (via the hashed
    advertisement key) and to decrypt the reports.

    ``key_id`` is now *optional* because it is derivable from ``private_key``
    (``KeyPair.hashed_adv_key_b64``). It is still validated when present: a
    ``key_id`` that does not match the one derived from its ``private_key``
    means the config is corrupt (mismatched pair), and querying it would
    silently return another tag's reports - so it is rejected instead.

    ``name`` is optional and ``advertisement_key`` is advisory only; when
    present it is checked against the derived advertisement key for the same
    reason.
    """
    if not isinstance(trackers, list):
        raise ValueError("'trackers' must be a list")
    for index, tracker in enumerate(trackers):
        if not isinstance(tracker, dict):
            raise ValueError(f"trackers[{index}] must be an object")
        if not tracker.get("private_key"):
            raise ValueError(f"trackers[{index}] is missing 'private_key'")

        key = _keypair_from_private_key(tracker["private_key"], index)

        key_id = tracker.get("key_id")
        if key_id and key_id != key.hashed_adv_key_b64:
            raise ValueError(
                f"trackers[{index}] has a 'key_id' that does not match its "
                f"'private_key' (expected {key.hashed_adv_key_b64!r}); "
                "the tracker configuration is inconsistent"
            )

        advertisement_key = tracker.get("advertisement_key")
        if advertisement_key and advertisement_key != key.adv_key_b64:
            raise ValueError(
                f"trackers[{index}] has an 'advertisement_key' that does not match "
                f"its 'private_key' (expected {key.adv_key_b64!r}); "
                "the tracker configuration is inconsistent"
            )
    return trackers


def build_trackers(trackers: List[dict]) -> List[Tracker]:
    """Map plain dicts from the frontend/HTTP body onto :class:`Tracker` objects.

    Validates first, so a bad/inconsistent entry raises ValueError here too.

    ``name`` falls back to the tracker's ``key_id`` because the name is the key
    of the results dict: a missing name would key every unnamed tracker under
    the same ``None`` bucket and serialize as ``"null"`` to the frontend.
    """
    validate_tracker_list(trackers)

    built: List[Tracker] = []
    for index, tracker in enumerate(trackers):
        key = _keypair_from_private_key(tracker["private_key"], index)
        key_id = key.hashed_adv_key_b64
        name = tracker.get("name") or key_id
        key.name = name
        built.append(Tracker(name=name, key_id=key_id, key=key))
    return built


def _as_aware(value: datetime) -> datetime:
    """Return ``value`` as a timezone-aware datetime.

    ``LocationReport.timestamp`` is already aware (UTC converted to local), but
    a naive value is interpreted as local time rather than crashing the whole
    fetch on a naive/aware comparison.
    """
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.astimezone()
    return value


def serialize_location(report: Any) -> Dict[str, Any]:
    """Serialize a ``LocationReport`` into the dict shape the frontend expects.

    ``web/app.js`` reads ``lat``/``lng``/``accuracy``/``reported_at`` and sorts
    on ``reported_at``, which must stay unix seconds as an int.
    """
    return {
        "lat": report.latitude,
        "lng": report.longitude,
        "accuracy": report.horizontal_accuracy,
        "reported_at": int(_as_aware(report.timestamp).timestamp()),
    }


def get_tracker_locations(
    trackers: List[dict],
    hours: float = DEFAULT_WITHIN_LAST_HOURS,
    account: Optional[Any] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Fetch location reports and return ``{tracker_name: [serialized, ...]}``.

    Args:
        trackers: list of dicts with ``private_key`` (required) and optional
            ``name``/``key_id``/``advertisement_key``.
        hours: only reports newer than this many hours are returned. FindMy.py
            0.10.2 has no server-side time window, so this is applied
            client-side on ``LocationReport.timestamp``. ``None`` or a
            non-positive value disables filtering.
        account: an already-restored ``AppleAccount``; when omitted, the cached
            session is loaded (and closed again) for the duration of the call.

    Raises:
        ValueError: the tracker list is invalid or internally inconsistent.
        lib.findmy_backend.AccountNotConfiguredError: no login has been done.
        lib.findmy_backend.AccountStateError: the saved session is unusable.

    Blocking network I/O; callers on an event loop must run it in a thread.
    """
    built = build_trackers(trackers)

    # Never log private keys.
    logger.debug(
        "fetching locations for %d tracker(s) over the last %s hours: %s",
        len(built),
        hours,
        [tracker.name for tracker in built],
    )

    if not built:
        return {}

    if account is not None:
        reports_by_key = _fetch_history(account, built)
    else:
        with findmy_backend.account_session() as session:
            reports_by_key = _fetch_history(session, built)

    cutoff = None
    if hours is not None and hours > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    results: Dict[str, List[Dict[str, Any]]] = {}
    for tracker in built:
        reports = reports_by_key.get(tracker.key_id, [])
        if cutoff is not None:
            reports = [r for r in reports if _as_aware(r.timestamp) >= cutoff]
        reports = sorted(reports, key=lambda r: _as_aware(r.timestamp))
        results[tracker.name] = [serialize_location(report) for report in reports]
    return results


def _fetch_history(account: Any, built: List[Tracker]) -> Dict[str, List[Any]]:
    """Query Apple once for all keys and index the result by ``key_id``.

    ``fetch_location_history`` returns a dict keyed by the ``KeyPair`` objects
    that were passed in; re-keying on ``hashed_adv_key_b64`` keeps the mapping
    explicit and lets several config entries share one physical tag.
    """
    # Deduplicate: the same tag may appear under several names.
    unique: Dict[str, KeyPair] = {}
    for tracker in built:
        unique.setdefault(tracker.key_id, tracker.key)

    history = account.fetch_location_history(list(unique.values()))
    if not isinstance(history, dict):  # single-key shape; defensive
        history = {list(unique.values())[0]: history}

    return {key.hashed_adv_key_b64: list(reports or []) for key, reports in history.items()}
