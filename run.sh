#!/bin/sh
set -e

export PIPENV_VENV_IN_PROJECT=1
# Without this, an already-active virtualenv (e.g. ~/.venv) is reused instead of .venv
export PIPENV_IGNORE_VIRTUALENVS=1

cd "$(dirname "$0")"

if ! command -v pipenv >/dev/null 2>&1; then
    pip3 install pipenv
fi

if [ ! -d .venv ]; then
    # sync installs exactly what Pipfile.lock pins, with hash verification.
    # CI should use `pipenv install --deploy --dev` instead, which additionally
    # fails if Pipfile.lock is stale relative to Pipfile.
    pipenv sync
fi

# https://stackoverflow.com/questions/77232001/python-eel-module-unable-to-use-import-bottle-ext-websocket-as-wbs-modulenotfoun
# pipenv run pip install auto-py-to-exe --upgrade --force-reinstall
# The `import bottle.ext.websocket` breakage was fixed upstream in eel; eel is
# pinned to 0.18.2 in Pipfile, which already imports bottle_websocket directly,
# so the old `sed` patch of site-packages/eel/__init__.py is no longer applied.

exec pipenv run python3 ./app.py
