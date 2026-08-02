#!/usr/bin/env python3
"""Capture thermostat state over time to a JSONL log for offline analysis.

Unlike the Volta BMS gateway (one characteristic streaming packed CAN frames), this
device is expected to expose several independent characteristics (zone name, setpoint,
mode, room temperature) that may be read-only/poll, or may support NOTIFY. This script
auto-detects: it subscribes to NOTIFY where the characteristic supports it, and falls
back to polling on an interval otherwise.

Run this while manually changing the mode/setpoint on the physical thermostat AND via
the RV Climate app, to see which characteristics actually change and confirm/deny the
encodings documented in ../CLAUDE.md.

Usage:
    python3 capture.py <ADDRESS> [duration_seconds]
"""

import asyncio
import datetime
import json
import sys

from bleak import BleakClient

# From bigthrilla/camper-ble-bridge's observed protocol notes (unverified reference)
KNOWN_CHARS = {
    "beb89473-05fe-41a0-9896-2c082660f19a": "zone_name",
    "09996813-fe7d-48ce-9b47-11634c80263c": "setpoint",
    "9230a9ef-347c-4645-8fd9-cbb830d714bf": "mode",
    "382b4008-084a-4158-b378-66674091b1e2": "room_temp",
}

POLL_INTERVAL_S = 2.0

log_entries = []


def log(source: str, label: str, uuid: str, raw: bytes):
    ts = datetime.datetime.now()
    entry = {
        "ts": ts.isoformat(),
        "source": source,   # "notify" or "poll"
        "label": label,
        "uuid": uuid,
        "hex": raw.hex(),
        "bytes": list(raw),
    }
    try:
        entry["ascii"] = raw.decode("utf-8")
    except Exception:
        pass
    log_entries.append(entry)
    print(f"  [{ts.strftime('%H:%M:%S.%f')[:-3]}] ({source}) {label:<12} {raw.hex():<20} {entry.get('ascii', '')}")


def make_notify_handler(label: str, uuid: str):
    def handler(_, raw: bytearray):
        log("notify", label, uuid, bytes(raw))
    return handler


async def poll_loop(client: BleakClient, poll_targets: list, duration: float):
    end = asyncio.get_event_loop().time() + duration
    while asyncio.get_event_loop().time() < end:
        for label, uuid in poll_targets:
            try:
                val = await client.read_gatt_char(uuid)
                log("poll", label, uuid, bytes(val))
            except Exception as e:
                print(f"  poll error on {label} ({uuid}): {e}")
        await asyncio.sleep(POLL_INTERVAL_S)


async def main(address: str, duration: float):
    print(f"Connecting to {address} ...")
    async with BleakClient(address) as client:
        print(f"Connected: {client.is_connected}\n")

        # Find which known characteristics exist and whether they support notify
        found = {}
        for service in client.services:
            for char in service.characteristics:
                uuid = char.uuid.lower()
                if uuid in KNOWN_CHARS:
                    found[uuid] = (KNOWN_CHARS[uuid], char.properties)

        if not found:
            print("None of the reference characteristic UUIDs were found on this device.")
            print("Run enumerate.py first and update KNOWN_CHARS in this script.")

        notify_targets = []
        poll_targets = []
        for uuid, (label, props) in found.items():
            if "notify" in props:
                notify_targets.append((label, uuid))
            elif "read" in props:
                poll_targets.append((label, uuid))
            print(f"  {label}: {uuid}  props={props}  -> {'notify' if 'notify' in props else ('poll' if 'read' in props else 'skip (no read/notify)')}")

        for label, uuid in notify_targets:
            await client.start_notify(uuid, make_notify_handler(label, uuid))

        print(f"\nCapturing for {duration:.0f}s — go change mode/setpoint on the thermostat and in the RV Climate app now.\n")

        if poll_targets:
            await poll_loop(client, poll_targets, duration)
        else:
            await asyncio.sleep(duration)

        for label, uuid in notify_targets:
            try:
                await client.stop_notify(uuid)
            except Exception:
                pass  # some devices reject CCCD writes on disconnect path

    with open("capture.jsonl", "w") as f:
        for entry in log_entries:
            f.write(json.dumps(entry) + "\n")
    print(f"\nSaved {len(log_entries)} entries -> capture.jsonl")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 capture.py <ADDRESS> [duration_seconds]")
        sys.exit(1)
    addr = sys.argv[1]
    dur = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0
    asyncio.run(main(addr, dur))
