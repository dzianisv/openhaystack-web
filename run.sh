#!/bin/sh
export PIPENV_VENV_IN_PROJECT=1

cd "$(dirname $0)"

if ! command -v pipenv 2>&1 >/dev/null; then
    pip3 install pipenv
fi

if [[ ! -d openhaystack-toolkit ]]; then
    git submodule update --init --recursive
fi

if [[ ! -d .venv ]]; then
    pipenv install
fi

exec pipenv run python3 ./app.py