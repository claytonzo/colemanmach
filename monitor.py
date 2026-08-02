#!/usr/bin/env python3
"""Live monitor for the Coleman Mach / Airxcel thermostat, and optional write test.

Usage:
    python3 monitor.py <ADDRESS>                         # read-only, loops until Ctrl+C
    python3 monitor.py <ADDRESS> --set-setpoint 72        # write setpoint once, then monitor
    python3 monitor.py <ADDRESS> --set-mode "COOL LOW"    # write mode once, then monitor

Writes are a real command to the physical AC — only pass --set-* once you've confirmed
via capture.py/analyze.py that the encoding actually matches what changed on the unit.
"""

import argparse
import asyncio

from bleak import BleakClient

# From bigthrilla/camper-ble-bridge's observed protocol notes (unverified reference)
CHAR_ZONE_NAME = "beb89473-05fe-41a0-9896-2c082660f19a"
CHAR_SETPOINT = "09996813-fe7d-48ce-9b47-11634c80263c"
CHAR_MODE = "9230a9ef-347c-4645-8fd9-cbb830d714bf"
CHAR_ROOM_TEMP = "382b4008-084a-4158-b378-66674091b1e2"

POLL_INTERVAL_S = 5.0


async def read_state(client: BleakClient) -> dict:
    state = {}
    for label, uuid in (
        ("zone_name", CHAR_ZONE_NAME),
        ("mode", CHAR_MODE),
        ("setpoint", CHAR_SETPOINT),
        ("room_temp", CHAR_ROOM_TEMP),
    ):
        try:
            raw = await client.read_gatt_char(uuid)
            if label in ("setpoint", "room_temp") and len(raw) == 1:
                state[label] = f"{raw[0]}°F"
            else:
                try:
                    state[label] = raw.decode("utf-8")
                except Exception:
                    state[label] = raw.hex()
        except Exception as e:
            state[label] = f"<read error: {e}>"
    return state


async def main(address: str, set_mode: str, set_setpoint: int):
    print(f"Connecting to {address} ...")
    async with BleakClient(address) as client:
        print(f"Connected: {client.is_connected}\n")

        if set_setpoint is not None:
            print(f"Writing setpoint = {set_setpoint} (raw byte {bytes([set_setpoint]).hex()}) ...")
            await client.write_gatt_char(CHAR_SETPOINT, bytes([set_setpoint]))

        if set_mode is not None:
            print(f"Writing mode = {set_mode!r} ...")
            await client.write_gatt_char(CHAR_MODE, set_mode.encode("utf-8"))

        print("Monitoring (Ctrl+C to stop)...\n")
        try:
            while True:
                state = await read_state(client)
                print(f"  zone={state['zone_name']:<12} mode={state['mode']:<16} "
                      f"setpoint={state['setpoint']:<6} room_temp={state['room_temp']}")
                await asyncio.sleep(POLL_INTERVAL_S)
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("address")
    parser.add_argument("--set-mode", default=None, help='e.g. "COOL LOW", "OFF", "HEAT"')
    parser.add_argument("--set-setpoint", type=int, default=None, help="degrees F")
    args = parser.parse_args()
    asyncio.run(main(args.address, args.set_mode, args.set_setpoint))
