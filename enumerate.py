#!/usr/bin/env python3
"""Connect to a BLE device and dump all GATT services and characteristics.

Usage:
    python3 enumerate.py <ADDRESS>

Example:
    python3 enumerate.py "AA:BB:CC:DD:EE:FF"

On macOS the address may be a UUID like "12345678-ABCD-...".

Flags any characteristic UUID matching the third-party reference doc
(bigthrilla/camper-ble-bridge, see ../CLAUDE.md) so it's easy to confirm/deny the
hypothesis against this specific thermostat.
"""

import asyncio
import sys
from bleak import BleakClient

# From bigthrilla/camper-ble-bridge's observed protocol notes (unverified reference)
KNOWN_CHARS = {
    "beb89473-05fe-41a0-9896-2c082660f19a": "zone name (ASCII, read)",
    "09996813-fe7d-48ce-9b47-11634c80263c": "setpoint (1 byte degF, read/write)",
    "9230a9ef-347c-4645-8fd9-cbb830d714bf": "mode (ASCII, read/write)",
    "382b4008-084a-4158-b378-66674091b1e2": "room temperature (1 byte degF, read)",
}


async def enumerate(address: str):
    print(f"Connecting to {address} ...")
    async with BleakClient(address) as client:
        print(f"Connected: {client.is_connected}\n")
        for service in client.services:
            print(f"Service: {service.uuid}  ({service.description})")
            for char in service.characteristics:
                props = ", ".join(char.properties)
                known = KNOWN_CHARS.get(char.uuid.lower())
                tag = f"  <<< reference: {known}" if known else ""
                print(f"  Char: {char.uuid}  [{props}]  ({char.description}){tag}")
                if "read" in char.properties:
                    try:
                        val = await client.read_gatt_char(char.uuid)
                        print(f"         Value (hex): {val.hex()}  ({list(val)})")
                        try:
                            print(f"         Value (str): {val.decode('utf-8')}")
                        except Exception:
                            pass
                    except Exception as e:
                        print(f"         Read error: {e}")
                for desc in char.descriptors:
                    print(f"    Desc: {desc.uuid}  ({desc.description})")
            print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 enumerate.py <BLE_ADDRESS_OR_UUID>")
        sys.exit(1)
    asyncio.run(enumerate(sys.argv[1]))
