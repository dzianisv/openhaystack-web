#!/usr/bin/env python3

import asyncio
import ipaddress
import logging
import os
import sys

from sanic import Sanic
from sanic.response import json

from sanic_cors import CORS

from openhaybike.types import BikeTracker
from openhaybike.locations import get_locations_of_trackers

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler(sys.stderr))

app = Sanic("tracker_app")


def get_bind_host() -> str:
    return os.environ.get("BIND_HOST") or os.environ.get("HOST") or DEFAULT_HOST


def get_bind_port() -> int:
    raw = os.environ.get("PORT")
    if not raw:
        return DEFAULT_PORT
    try:
        return int(raw)
    except ValueError:
        raise SystemExit(f"Invalid PORT value: {raw!r}")


def is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def get_allowed_origins(port: int) -> list:
    configured = os.environ.get("ALLOWED_ORIGINS")
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    origins = []
    for eel_port in {port, 8000}:
        origins.append(f"http://localhost:{eel_port}")
        origins.append(f"http://127.0.0.1:{eel_port}")
    return origins


# CORS is configured once, globally. The per-route @cross_origin decorator that
# used to be here was redundant with this and only re-applied the same defaults.
CORS(
    app,
    resources={r"/api/v1/*": {"origins": get_allowed_origins(get_bind_port())}},
    automatic_options=True,
)


def get_locations(trackers: dict, icloud_key: str) -> dict:
    trackers = [BikeTracker(
        name=tracker.get("name"),
        key_id=tracker.get("key_id"),
        advertisement_key="",
        private_key=tracker.get("private_key"),
    ) for tracker in trackers]

    reports = get_locations_of_trackers(trackers, icloud_key, 24)
    r = {}
    for name, locations in reports.items():
        r[name] = [location.serialize() for location in locations]
    return r


def validate_trackers(payload) -> list:
    """Return the tracker list, or raise ValueError with a user-facing message."""
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object")
    trackers = payload.get("trackers", [])
    if not isinstance(trackers, list):
        raise ValueError("'trackers' must be a list")
    for index, tracker in enumerate(trackers):
        if not isinstance(tracker, dict):
            raise ValueError(f"trackers[{index}] must be an object")
        for field in ("key_id", "private_key"):
            if not tracker.get(field):
                raise ValueError(f"trackers[{index}] is missing '{field}'")
    return trackers


@app.route("/api/v1/locations", methods=["POST"])
async def post_locations(request):
    icloud_key = os.environ.get("ICLOUD_KEY")
    if not icloud_key:
        logger.error("ICLOUD_KEY is not set; cannot query Apple's location service")
        return json({"error": "Server misconfigured: ICLOUD_KEY is not set"}, status=500)

    try:
        payload = request.json
    except Exception:
        payload = None
    if payload is None:
        return json({"error": "Request body must be valid JSON"}, status=400)

    try:
        trackers = validate_trackers(payload)
    except ValueError as e:
        return json({"error": str(e)}, status=400)

    try:
        # get_locations performs blocking network I/O; keep it off the event loop.
        r = await asyncio.to_thread(get_locations, trackers, icloud_key)
    except Exception as e:
        logger.exception("Failed to fetch locations from upstream")
        return json(
            {"error": f"Failed to fetch locations from Apple: {type(e).__name__}: {e}"},
            status=502,
        )
    return json(r)


def serve():
    host = get_bind_host()
    port = get_bind_port()
    if not is_loopback(host):
        logger.warning(
            "Binding to %s exposes an UNAUTHENTICATED endpoint that accepts tracker "
            "private keys and returns physical location history to anyone who can "
            "reach this host. Only do this on a trusted network.",
            host,
        )
    app.run(host=host, port=port)


if __name__ == "__main__":
    serve()
