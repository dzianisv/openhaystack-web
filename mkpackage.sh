#!/bin/sh

pipenv run pyinstaller  --onefile --windowed --hidden-import=eel app.py