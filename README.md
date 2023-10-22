# intro

this app allows to see locations of the openhaystack trackers

![](img/b4add158-6f94-4d46-90cd-4ab8b51f82df.webp)

# requirements

```shell
brew install python3
python3 -m pip install pipenv
```


[Get] an Icloud key using `pipenv run python3 ./get-icloud-key.py` and export it when start an application.

```shell
pipenv install
ICLOUD_KEY=... pipenv run python3 app.py
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
