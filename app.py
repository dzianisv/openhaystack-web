#!/usr/bin/env python3
import eel
import backend.app
import threading
import random

@eel.expose
def get_locations(trackers: dict):
    locations =  eel.spawn(backend.app.get_locations(trackers))
    print(locations)
    return locations

threading.Thread(target=backend.app.serve).start()

eel.init('web')
# mode='electron'
eel.start('index.html', port=random.randint(1025, 9999))
