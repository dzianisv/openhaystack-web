#!/usr/bin/env python3
import eel
import backend.app
import logging
import os
from lib.icloud import get_icloud_key_cached

def ask_password() -> str:
    # 'Input a keychain password to retreive an iCloud key'
    password = eel.askPassword()()
    logging.debug("keychain password %r", password)
    return password

@eel.expose
def get_locations(trackers: dict):
    logging.debug("get_locations: %r", trackers)
    locations =  backend.app.get_locations(trackers, get_icloud_key_cached(ask_password))
    return locations

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')
    eel.init('web')
    eel.start('index.html')
