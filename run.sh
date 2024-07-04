#!/bin/sh
export PIPENV_VENV_IN_PROJECT=1

cd "$(dirname $0)"

if ! command -v pipenv 2>&1 >/dev/null; then
    pip3 install pipenv
fi

if [[ ! -d .venv ]]; then
    pipenv install --skip-lock
fi

# https://stackoverflow.com/questions/77232001/python-eel-module-unable-to-use-import-bottle-ext-websocket-as-wbs-modulenotfoun
# pipenv run pip install auto-py-to-exe --upgrade --force-reinstall

sed -i '' 's/import bottle\.ext\.websocket as wbs/import bottle_websocket as wbs/' .venv/lib/python3.12/site-packages/eel/__init__.py
exec pipenv run python3 ./app.py
