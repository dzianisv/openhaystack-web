# requirements

```shell
brew install python3
python3 -m pip install pipenv
```


[Generate](https://dzianisv.github.io/notes/Embedded/Openhaybike.html) and export ICLOUD key
```shell
export ICLOUD_KEY=
```

```shell
pipenv install
pipenv run python3 app.py
```

# Usage

Click on the Trackers button and put the trackers configuration, for example
```json
[
    {
        "name": "microbit",
        "key_id": "",
        "private_key": ""
    }
]
```

Then tracker positions has to be displayed on the map.
