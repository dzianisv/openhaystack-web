#!/usr/bin/env python3
import eel
import logging
import time
from lib.icloud import get_icloud_key_cached

from openhaybike.types import BikeTracker
from openhaybike.locations import get_locations_of_trackers

# The keychain password lives in the browser's memory only, so the first call
# after start-up merely opens the dialog and returns nothing. Wait for the user.
PASSWORD_WAIT_TIMEOUT_SECONDS = 180
PASSWORD_POLL_INTERVAL_SECONDS = 0.5

def ask_password() -> str:
    # 'Input a keychain password to retreive an iCloud key'
    # Re-calling askPassword() is idempotent: it only re-shows the modal, which
    # is a no-op when it is already visible.
    # eel.sleep() (gevent.sleep) is required here: eel never monkeypatches the
    # stdlib, so a time.sleep() would block the whole OS thread - including the
    # websocket greenlet that delivers the answer we are waiting for.
    deadline = time.monotonic() + PASSWORD_WAIT_TIMEOUT_SECONDS
    while True:
        password = eel.askPassword()()
        if password:
            logging.debug("keychain password obtained from the frontend")
            return password
        if time.monotonic() >= deadline:
            raise TimeoutError(
                "Timed out after %d seconds waiting for the keychain password. "
                "Enter it in the password dialog and try again."
                % PASSWORD_WAIT_TIMEOUT_SECONDS
            )
        eel.sleep(PASSWORD_POLL_INTERVAL_SECONDS)

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
    # Never log tracker private keys.
    logging.debug(
        "get_locations: %d tracker(s): %s",
        len(trackers),
        [tracker.get("name") for tracker in trackers],
    )
    try:
        return _get_locations(trackers, get_icloud_key_cached(ask_password))
    except Exception:
        logging.exception("get_locations failed")
        raise

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')
    eel.init('web')
    eel.start('index.html')
