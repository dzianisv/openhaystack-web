#!/bin/sh
export PIPENV_VENV_IN_PROJECT=1

cd "$(dirname $0)"

if [ ! -d openhaybike/.git ]; then
    git submodule update --init --recursive
fi

if ! command -v pipenv 2>&1 >/dev/null; then
    pip3 install pipenv
fi

if [[ ! -d .venv ]]; then
    pipenv install --skip-lock
fi

# https://stackoverflow.com/questions/77232001/python-eel-module-unable-to-use-import-bottle-ext-websocket-as-wbs-modulenotfoun
pipenv run pip install auto-py-to-exe --upgrade --force-reinstall

exec pipenv run python3 ./app.py
