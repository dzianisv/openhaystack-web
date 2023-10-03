#!/usr/bin/env python3

from sanic import Sanic
from sanic.response import json
from openhaybike.types import BikeTracker
from openhaybike.locations import get_locations_of_trackers
import json as jsonlib
import logging
import sys
import os

icloud_key = os.environ.get("ICLOUD_KEY")
if not icloud_key:
    raise ValueError("ICLOUD_KEY environment variable is not set!")

app = Sanic("tracker_app")

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler(sys.stderr))

@app.route("/api/v1/locations", methods=["POST"])
async def get_locations(request):
    trackers = [BikeTracker(
        name=tracker.get("name"),
        key_id=tracker.get("key_id"),
        advertisement_key="",
        private_key=tracker.get("private_key"),
    ) for tracker in request.json.get("trackers", [])]

    reports = get_locations_of_trackers(trackers, icloud_key, 24)
    r = {}
    for name, locations in reports.items():
        r[name] = [location.serialize() for location in locations]

    logger.debug(r)
    return json(r)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
