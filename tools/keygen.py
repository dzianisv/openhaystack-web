#!/usr/bin/env pipenv run 

import base64
import json
import base64
import hashlib

from lib.AirTagCrypto import AirTagCrypto
from dataclasses import dataclass

@dataclass
class Keys:
    key_id: str
    advertisement_key: str
    private_key: str

def generate_keys() -> Keys:
    crypto = AirTagCrypto()
    return Keys(
        key_id=base64.b64encode(hashlib.sha256(base64.b64decode(crypto.get_advertisement_key())).digest()).decode('utf-8'),
        advertisement_key=crypto.get_advertisement_key(),
        private_key=base64.b64encode(crypto._private_key).decode()
    )

if __name__ == "__main__":
    print(json.dumps(generate_keys().__dict__))