# intro

this app allows to see locations of the openhaystack trackers

![](img/b4add158-6f94-4d46-90cd-4ab8b51f82df.webp)

# how to build a openhaystack tracker

- [Nordic NRF51822 Airtag tutorial](https://dzianisv.github.io/notes/Embedded/Nordic-NRF51822-Airtag.html)
- [openhaystack-toolkit](https://github.com/dzianisv/openhaystack-toolkit)

# requirements

```shell
git submodule update --init
```

```shell
brew install python3
python3 -m pip install pipenv
git submodule update --init --recursive
pipenv install
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
