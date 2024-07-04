#!/usr/bin/env python3
import eel
import logging
from lib.icloud import get_icloud_key_cached

from openhaybike.types import BikeTracker
from openhaybike.locations import get_locations_of_trackers

def ask_password() -> str:
    # 'Input a keychain password to retreive an iCloud key'
    password = eel.askPassword()()
    logging.debug("keychain password %r", password)
    return password

def _get_locations(trackers: dict, icloud_key: str) -> dict:
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

@eel.expose
def get_locations(trackers: dict):
    logging.debug("get_locations: %r", trackers)
    locations =  _get_locations(trackers, get_icloud_key_cached(ask_password))
    return locations

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')
    eel.init('web')
    eel.start('index.html')
