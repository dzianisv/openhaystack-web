#!/usr/bin/env python3
import eel
import backend

@eel.expose
def get_locations(trackers: dict):
    return backend.get_locations(trackers)

# Initialize eel with web folder
eel.init('web')
# Start eel with the main.html
# mode='electron'
eel.start('index.html')
