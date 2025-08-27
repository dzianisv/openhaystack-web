#!/usr/bin/env python3
import sys
from intelhex import IntelHex

if len(sys.argv) != 3:
    print("Usage: hex2bin.py <input.hex> <output.bin>")
    sys.exit(1)

IntelHex(sys.argv[1]).tofile(sys.argv[2], format='bin')
