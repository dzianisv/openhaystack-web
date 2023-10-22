#!/usr/bin/env python3
import eel
import backend.app
import random
import logging
import os

@eel.expose
def get_locations(trackers: dict):
    logging.debug("get_locations: %r", trackers)
    locations =  eel.spawn(backend.app.get_locations(trackers))
    print(locations)
    return locations


if __name__ == "__main__":
    if 'ICLOUD_KEY' not in os.environ:
        print("Please set ICLOUD_KEY environment variable")
        exit(1)

    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')
    eel.init('web')
    eel.start('index.html', port=random.randint(1025, 9999))
