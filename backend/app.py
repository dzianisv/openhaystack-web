#!/usr/bin/env python3

from sanic import Sanic
from sanic.response import json
from sanic_cors import CORS, cross_origin

from openhaybike.types import BikeTracker
from openhaybike.locations import get_locations_of_trackers
import json as jsonlib
import logging
import sys
import os

app = Sanic("tracker_app")
CORS(app)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler(sys.stderr))

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

@app.route("/api/v1/locations", methods=["POST"])
@cross_origin(app)
async def post_locations(request):
    icloud_key = os.environ.get("ICLOUD_KEY")
    r = get_locations(request.json.get("trackers", []), icloud_key)
    return json(r)


def serve():
    app.run(host="0.0.0.0", port=8000)

if __name__ == "__main__":
    serve()

