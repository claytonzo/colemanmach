# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

Reverse-engineering the BLE interface of a Coleman Mach / Airxcel Bluetooth Wall
Thermostat (controlled by the *RV Climate* app) in a 2020 Winnebago Travato 59GL.
Goal: read/set mode, setpoint, and room temperature directly over Bluetooth for a
Home Assistant integration, without depending on the phone app.

See [`../CLAUDE.md`](../CLAUDE.md) for hardware context and the third-party protocol
reference this project starts from (bigthrilla/camper-ble-bridge). Everything below is
this project's own confirmed findings — keep the two files in sync as facts get
verified: promote a row from "hypothesis" to "confirmed" here once it's tested against
the real unit.

## Dependencies

```bash
pip3 install bleak paho-mqtt
```

Python 3.9 (macOS system Python via Xcode) for local dev; the Pi runs Python 3.12
(Alpine) for the eventual add-on. **Do not use `X | Y` union type syntax** — it
requires 3.10+. Use `Optional[X]` or skip annotations instead. (Same constraint as
`HA-VoltaApp/myvolta` — copy that project's pattern.)

## Device

*(Fill in once confirmed via `scan.py` / `enumerate.py` against the actual thermostat.)*

- **Hardware**: Coleman Mach / Airxcel Bluetooth Wall Thermostat, model TBD
- **BLE address (macOS UUID)**: TBD
- **BLE address (Linux MAC)**: TBD
- **Service UUID**: `c9282723-4680-491b-a904-c066fa81061f` *(unverified — from
  third-party reference, see top-level CLAUDE.md)*

## Running the scripts

```bash
# Scan for BLE devices (find the thermostat)
python3 scan.py

# Dump all GATT services and characteristics
python3 enumerate.py "<ADDRESS>"

# Poll/log the known characteristics over time (watch for changes while you
# manually operate the thermostat and the RV Climate app)
python3 capture.py "<ADDRESS>"

# Decode a capture log offline
python3 analyze.py capture.jsonl

# Live monitor — mode/setpoint/room temp, updates periodically
python3 monitor.py "<ADDRESS>"
```

## Protocol (hypothesis, pending confirmation)

**Service:** `c9282723-4680-491b-a904-c066fa81061f`

| Purpose | Characteristic UUID | Encoding | Access |
|---|---|---|---|
| Zone name | `beb89473-05fe-41a0-9896-2c082660f19a` | ASCII string | read |
| Setpoint | `09996813-fe7d-48ce-9b47-11634c80263c` | 1 byte, raw °F | read/write |
| Mode | `9230a9ef-347c-4645-8fd9-cbb830d714bf` | ASCII string | read/write |
| Room temperature | `382b4008-084a-4158-b378-66674091b1e2` | 1 byte, raw °F | read |

Candidate mode strings (unverified): `OFF`, `FAN LOW`, `FAN HIGH`, `COOL LOW`,
`COOL HIGH`, `COOL AUTO LOW`, `COOL AUTO HIGH`, `HEAT`.

None of this has been checked against real notifications yet — `enumerate.py`'s
`properties` output for each characteristic will show whether they're actually
read-only/poll, or support `notify` (push on change), which changes how `capture.py`
and the eventual add-on should be built (persistent notify subscription vs. a poll
loop, mirroring the difference in `HA-VoltaApp/myvolta` between its notify-driven
BMS and a hypothetical poll-only device).

## Pairing

The thermostat may require BLE pairing/bonding with a passkey before characteristics
are readable. Open questions to resolve empirically:

- Does a passkey prompt actually appear on first connect?
- Where does the passkey come from — printed on the unit, a factory default, or set
  during RV Climate app pairing?
- **macOS**: CoreBluetooth (which `bleak` sits on top of) handles pairing at the OS
  level via a system dialog — a script can't fully drive this. If pairing is required,
  local dev/testing may need to happen on the Pi (BlueZ) instead, where `bluetoothctl`
  can pair non-interactively and bleak can use an already-bonded connection.
- **Linux/Pi**: `bluetoothctl pair <MAC>` then `bluetoothctl trust <MAC>` before
  running the scripts, if pairing turns out to be required.

Update this section with the real answer once tested — don't guess further here.

## Home Assistant add-on (`ha_addon/`)

Not started. Once the protocol above is confirmed, model this on
`HA-VoltaApp/myvolta/ha_addon/`: persistent BLE connection (or poll loop, depending on
notify support) → MQTT publish → HA auto-discovery sensors for mode/setpoint/room
temp/zone name, plus climate-entity style mode/setpoint control back to the thermostat.

## Deploying changes to the Pi

Not yet applicable — no add-on exists yet. Once one does, mirror
`HA-VoltaApp/myvolta`'s deploy flow (git pull on the Pi, copy into the add-on's live
directory, rebuild — **not just restart**, since the Dockerfile bakes the script in at
build time).
