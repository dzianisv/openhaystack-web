# HeyStack-NRF5X - OpenHaystack Compatible Low Power Firmware

This repository contains an alternative OpenHaystack firmware. It is based on the SoftDevice from Nordic Semiconductor. This approach could potentially extend battery life, with some estimates suggesting up to three years on a CR2032 battery! (See [this comment](https://github.com/seemoo-lab/openhaystack/issues/57#issuecomment-841642356)).

It's based on [acalatrava's](https://raw.githubusercontent.com/acalatrava/openhaystack-firmware/main/README.md) firmware with fixes
and support for newer nRF5x devices and SDKs.

## Supported Devices

- **nRF52810**: Tested on an original Tile Tag.
- **nRF51822**: Tested on an aliexpress tag.
- **nRF52832**: Tested with the YJ-17024 board (see link below).

Other nRF devices might be supported, but untested.

These aliexpress tags should work with the nRF52810 firmware:

- [Holyiot NRF52810](https://s.click.aliexpress.com/e/_DdDyDp9)

These aliexpress tags works with the nRF51822 firmware:

- [1: NRF51822](https://s.click.aliexpress.com/e/_De2JHyL)
- [2: NRF51822](https://s.click.aliexpress.com/e/_DdkWkyJ)
- [3: NRF51822](https://s.click.aliexpress.com/e/_DBp4icn)

This AliExpress tag works with the nRF52832 firmware:

- [HolyIOT YJ-17024-NRF52832 Amplified Module](https://s.click.aliexpress.com/e/_DlpmE0n): [Manufacturer's documentation](http://www.holyiot.com/eacp_view.asp?id=299).
- [HolyIOT YJ-17095-NRF52832](https://s.click.aliexpress.com/e/_DCkw8LV)

These are affiliate links, so if you buy something using them, I get a small commission, and you help me to keep working on this project.

### Available make targets

- `nrf51822/armgcc`: `nrf51822_xxac` `nrf51822_xxac-dcdc`
- `nrf52810/armgcc`: `nrf52810_xxaa` `nrf52810_xxaa-dcdc`
- `nrf52832/armgcc`: `nrf52832_xxaa` `nrf52832_xxaa-dcdc` `nrf52832_yj17024`

## Setup Instructions

Unzip the relevant Nordic SDK and a compiler and place it in the `nrf-sdk` folder:

```bash
gcc-arm-none-eabi-6-2017-q2-update/ # Migth work with newer versions
nRF5_SDK_12.3.0_d7731ad/
nRF5_SDK_15.3.0_59ac345/
```

### Compile the Firmware

```
make all # Compile all the supported devices and place them in the release folder
```

### Flash the Firmware

The device can be flashed using a STLink V2 programmer. The programmer should be connected to the SWD pins on the device. The following command can be used to flash the firmware:

```bash
cd nrf51822/armgcc
make clean
make stflash-nrf51822_xxac-patched ADV_KEYS_FILE=./50_NRF_keyfile
```

```bash
```

To compile the firmware for the nRF52832 with the YJ-17024 board configuration, use the following command:

```bash
cd nrf52832/armgcc
make clean
make stflash-nrf52832_yj17024-patched ADV_KEYS_FILE=./50_NRF_keyfile
```

### Flashing with Raspberry Pi

If you're using a Raspberry Pi for flashing instead of a STLink V2 programmer, you can change the OpenOCD configuration file. Toggle between the configuration for the STLink V2 and Raspberry Pi by modifying the OpenOCD script.

Locate the configuration line in your `openocd.cfg` file:

```bash
source [find interface/stlink.cfg]
```

To use a Raspberry Pi for flashing, comment out the STLink line and uncomment the Raspberry Pi configuration line:

```bash
# source [find interface/stlink.cfg]
source [find interface/raspberrypi2-native.cfg]
```

This change allows you to use the Raspberry Pi GPIO pins for flashing your device instead of the STLink programmer.

### Makefile Variables Summary

This section describes key Makefile variables you can adjust to customize the firmware:


- **HAS_DEBUG**: Controls debug logging; set to `1` to enable or `0` to disable (default).
- **MAX_KEYS**: Defines the maximum number of keys supported;
- **HAS_BATTERY**: Enables battery level reporting; set to `1` to enable or `0` to disable (default);
- **HAS_DCDC**: Enables DCDC mode; set to `1` to enable or `0` to for automatic selection (default);
- **KEY_ROTATION_INTERVAL**: Sets the key rotation interval in seconds (default is 3600 * 3 seconds);
- **ADVERTISING_INTERVAL**: Adjusts Bluetooth advertising interval; `0` (default) uses the standard interval (1000ms, down to 20ms);
- **BOARD**: Specifies the custom board configuration; defaults to `custom_board` (see `custom_board.h`), but can be overridden with your board's configuration. For example, set `BOARD=yj17024` for the nRF52832 device.
- **ADV_KEYS_FILE**: Specifies the file containing the keys to be flashed to the device.
- **GNU_INSTALL_ROOT**: Path to the GNU toolchain; eg: ../../nrf-sdk/gcc-arm-none-eabi-6-2017-q2-update/bin/
- **FIND_NETWORK**: `APPLE` (default), `GOOGLE_FMDN`, or `DUAL`. Default keeps the Apple manufacturer-data advert. See below.

Google Find Hub (FMDN) example. `FIND_NETWORK=GOOGLE_FMDN` forces `KEY_ROTATION_INTERVAL=1024` (`K = 10`). Any other interval is a build error:

```bash
cd nrf52832/armgcc
make clean
make nrf52832_xxaa FIND_NETWORK=GOOGLE_FMDN
```

Regenerate the EID table before that build if the placeholder key is not the one you registered. Run this from the repo root:

```bash
python3 tools/fmdn_keys.py --eik <64 hex chars> --count 8 --start 0 \
  --out firmware/src/fmdn_eid_table.h
```

## Find Hub Network (FMDN) mode

`FIND_NETWORK=GOOGLE_FMDN` advertises a legacy Find Hub frame instead of the Apple offline-finding frame:

- Flags AD `02 01 06`, then service data for UUID `0xFEAA` (bytes `AA FE`).
- Frame type `0x40` (normal mode), then the 20-byte EID, then one hashed-flags byte. 29 bytes total, so it fits a legacy advert. Frame type `0x41` is unwanted-tracking-protection mode. This build does not set the UTP flag and it changes the address with the EID, so it does not advertise `0x41`.
- The EID table is `firmware/src/fmdn_eid_table.h`, produced by `tools/fmdn_keys.py`. The firmware does not compute the EID. Slot selection is `(beacon_counter - FMDN_TABLE_START_TS) / 1024`. The counter is stored in the last flash page and restored after reset, so a power cycle does not restart at slot 0. It is not a circular list: when the counter leaves the table, FMDN advertising stops.
- Hashed flags = clear flags XOR the low byte of `SHA256(r)`, with `r` aligned to 160 bits. Clear flags start at 0 (battery indication unsupported). `HAS_BATTERY=1` maps the measured level into spec bits 5-6, numbered from the MSB, and XORs again. The SoftDevice copies the advert when advertising is restarted, so the new flags go on air at the next rotation.
- The address is a non-resolvable private address taken from the EID, so it changes with the slot.

`FIND_NETWORK=DUAL` keeps the Apple advert and also the FMDN advert. One legacy packet cannot hold both, so a 2-second timer swaps which one is on air. Apple keys still rotate on their own index. The FMDN slot follows the persisted beacon counter, not that index. The rotation interval is forced to 1024 seconds. When the FMDN table is exhausted the swap stays on the Apple advert.

`FIND_NETWORK=APPLE` does not include the FMDN advertiser. Behavior matches the previous firmware.

### Provisioning limits

This is a broadcast-only tag. It is not a Find Hub accessory until someone registers it, and this firmware cannot do that registration itself.

- The phone, not the tag, chooses the 32-byte ephemeral identity key during provisioning and writes it to the Beacon Actions characteristic (data ID `0x02`), encrypted with the Fast Pair account key. There is no Fast Pair service and no GATT here, so the tag cannot receive an EIK, an account key, or a clock.
- Find Hub only returns locations to the owner who registered that EIK. A scanner can see the `FEAA` frame without the tag ever appearing in the owner's Find Hub. The workable path is the GoogleFindMyTools-style one: generate the EIK on the owner side, register the accessory with the Google account out of band, precompute the table with `tools/fmdn_keys.py`, and flash a build that contains that table.
- The backend stores derived keys, not the EIK. Recovery is the first 8 bytes of `SHA256(EIK || 0x01)`, ring is `SHA256(EIK || 0x02)`, unwanted-tracking protection is `SHA256(EIK || 0x03)`. This firmware does not store or serve those, so ring, EIK recovery, and unwanted-tracking activation from the network do not work.
- One account key is the owner account key and must not be dropped until factory reset. This build has no account-key slots.
- The EID is a function of the beacon time counter. Slot `i` is the window starting at `--start` (masked to a 1024-second boundary) plus `i * 1024`. The tag keeps that counter in the last flash page and advances it by 1024 seconds of powered-on time. A reboot resumes the last saved counter. A chip erase, or a new table with a different start, starts again at that table's start. It does not wrap, and it does not add time spent with the battery removed (the chip has no clock while unpowered). Generate the table with `--start` equal to the counter you want at first boot. The spec also wants the rotation instant jittered by 1 to 204 seconds. This firmware does not jitter.
- Locator-tag rules this build does not implement: Fast Pair pairing, reverting to factory settings if FHN is not provisioned within 5 minutes, non-discoverable Fast Pair frames after power loss so the phone can sync the clock, and a button chord to stop advertising without wiping the EIK. DULT unwanted-tracking prevention is not implemented either.
- Only SECP160R1 (20-byte EID) is implemented. SECP256R1 needs a 32-byte EID and BLE 5 extended advertising, which this advertiser does not send. The 20-byte frame is the one older phones can report.
- The committed `fmdn_eid_table.h` is a placeholder from EIK `0x11` repeated 32 times, start timestamp 0, 8 slots. That key is not registered to any account. Replace the header before expecting a lookup.
- Frame type is `0x40` (normal mode). Unwanted-tracking-protection mode (`0x41`, UTP flag set, address held for up to 24 hours) is not implemented, so the firmware does not advertise `0x41`.

### Debugging with strtt

The firmware supports using strtt for displaying debug logs. To enable this feature, compile the firmware with `HAS_DEBUG=1`:

```bash
cd nrf51822/armgcc
make clean
make stflash-nrf51822_xxac-patched MAX_KEYS=500 HAS_DEBUG=1 ADV_KEYS_FILE=./50_NRF_keyfile
```

This will activate debug logging, which can be viewed using `strtt`.

### Using Black Magic Probe

The firmware can also be flashed using a Black Magic Probe. The programmer should be connected to the SWD pins on the device. The following command can be used to flash the firmware:

```bash
cd nrf52832/armgcc
make clean
make bmpflash-nrf52832_yj17024-patched ADV_KEYS_FILE=./50_NRF_keyfileZ
```

### Using RTT monitor

You can use the RTT monitor to see the debug logs. The following command can be used to monitor the logs:

```bash
make bmpflash-monitor
  BMP /dev/serial/by-id/usb-Black_Magic_Debug_Black_Magic_Probe__ST-Link_v2__v1.10.0-1151-g3fe0bc5a-XXXXXXXX-if00 (monitor)
  minicom -c on -D /dev/serial/by-id/usb-Black_Magic_Debug_Black_Magic_Probe__ST-Link_v2__v1.10.0-1151-g3fe0bc5a-XXXXXXXX-if02
Target voltage: 3.35V
....
```

In another terminal, you can monitor the logs:

```bash
minicom -c on -D /dev/serial/by-id/usb-Black_Magic_Debug_Black_Magic_Probe__ST-Link_v2__v1.10.0-1151-g3fe0bc5a-XXXXXXXX-if02
<info> app: last_filled_index: 249
<info> app: Starting advertising
<info> app: ble_set_mac_address: D3:7F:6F:DA:64:78
<info> app: ble_set_max_tx_power: 8 dB failed
<info> app: ble_set_max_tx_power: 7 dBm failed
<info> app: ble_set_max_tx_power: 6 dBm failed
<info> app: ble_set_max_tx_power: 5 dBm failed
<info> app: ble_set_max_tx_power: 4 dBm
<info> app: Rotating key: 59
<info> app: last_filled_index: 249
[0.000] <info> app: Starting advertising
[0.000] <info> app: ble_set_mac_address: XX:XX:XX:XX:XX:XX
```
