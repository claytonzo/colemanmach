#!/usr/bin/env python3
"""Scan for BLE devices — finds the Coleman Mach / Airxcel thermostat's advertised name/address."""

import asyncio
from bleak import BleakScanner

# From bigthrilla/camper-ble-bridge's observed protocol notes (third-party reference,
# unverified against this specific thermostat) — see ../CLAUDE.md
KNOWN_SERVICE_UUID = "c9282723-4680-491b-a904-c066fa81061f"


async def scan(duration: float = 10.0):
    print(f"Scanning for BLE devices for {duration}s... (make sure the thermostat is powered)\n")

    devices = await BleakScanner.discover(timeout=duration, return_adv=True)

    print(f"{'Name':<40} {'Address':<40} {'RSSI':>5}  Services/UUIDs")
    print("-" * 110)
    for addr, (device, adv) in devices.items():
        name = device.name or "(no name)"
        uuids = ", ".join(adv.service_uuids) if adv.service_uuids else ""
        print(f"{name:<40} {addr:<40} {adv.rssi:>5}  {uuids}")

    print("\n--- Possible Coleman Mach / RV Climate devices ---")
    found = False
    for addr, (device, adv) in devices.items():
        name = (device.name or "").lower()
        uuids = [u.lower() for u in (adv.service_uuids or [])]
        name_match = any(k in name for k in ("coleman", "mach", "airxcel", "thermostat", "rv climate", "climate"))
        uuid_match = KNOWN_SERVICE_UUID in uuids
        if name_match or uuid_match:
            tag = " [service UUID matches reference doc]" if uuid_match else ""
            print(f"  >> {device.name}  {addr}  RSSI={adv.rssi}{tag}")
            found = True
    if not found:
        print("  None matched keywords or the known service UUID — check the full list above")
        print("  and look for unfamiliar names (the thermostat may advertise a generic/blank name).")


if __name__ == "__main__":
    asyncio.run(scan())
