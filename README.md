# intro

An app allows one to see the locations of the open haystack trackers

![](img/b4add158-6f94-4d46-90cd-4ab8b51f82df.webp)

# How to use it?

```shell
./run.sh
```

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


# For developers

## How to build a open haystack tracker?

1. [Building Nordic NRF51822 Airtag tutorial](https://dzianisv.github.io/notes/Embedded/Nordic-NRF51822-Airtag.html)
2. 2. [How to generate a key pair and flash a firmware to the MCU]([https://github.com/dzianisv/openhaystack-toolkit](https://github.com/dzianisv/openhaystack-toolkit/blob/main/README.md))

## dev requirements

1. Install system requirements (macOS example):
```shell
brew install python3
python3 -m pip install pipenv
git submodule update --init --recursive
pipenv install
```

2. Install python requirements

```shell
pipenv install
pipenv run python3 app.py
```
