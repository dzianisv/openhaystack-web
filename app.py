#!/usr/bin/env python3
import eel
import backend.app
import logging
import os

icloud_key = os.environ.get("ICLOUD_KEY")

@eel.expose
def get_locations(trackers: dict):
    logging.debug("get_locations: %r", trackers)
    locations =  backend.app.get_locations(trackers, icloud_key)
    return locations


if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')
    eel.init('web')
    eel.start('index.html')
