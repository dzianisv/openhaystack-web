#!/usr/bin/env python3
import eel
import backend.app
import logging
import os
from openhaystacktoolkit.lib.icloud import get_icloud_key_cached

def ask_password() -> str:
    return eel.ask_password()('Input a keychain password to retreive an iCloud key')

@eel.expose
def get_locations(trackers: dict):
    logging.debug("get_locations: %r", trackers)
    locations =  backend.app.get_locations(trackers, get_icloud_key_cached(password_fn))
    return locations

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')
    eel.init('web')
    eel.start('index.html')
