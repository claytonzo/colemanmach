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

- **Hardware**: Coleman Mach / Airxcel Bluetooth Wall Thermostat, exact model still TBD
- **BLE address (Linux MAC)**: `00:A0:50:4E:E5:07` — confirmed via HA Core's own
  passive Bluetooth scanner (`bluetooth/subscribe_advertisements` websocket command)
  and independently reconfirmed with `bluetoothctl`/`scan.py` from the Pi
- **BLE address (macOS UUID)**: not yet captured (haven't scanned from a Mac near the
  actual thermostat)
- **Service UUID**: `c9282723-4680-491b-a904-c066fa81061f` — **confirmed**, both by
  advertisement (`bluetoothctl info`) and by live `enumerate.py` GATT dump
- **ManufacturerData.Key `0xffff`, 1-byte value**: `00` at rest, `AA` while the
  thermostat is in Bluetooth pairing mode (UP+DOWN held 5s) — a live, readable
  "is this thermostat in pairing mode right now" flag. Not documented anywhere else;
  found empirically 2026-08-02.

## Existing community integration

[mallorybowes/ha-coleman-mach-ble](https://github.com/mallorybowes/ha-coleman-mach-ble)
is a public HACS custom_component that already implements a `climate` entity for this
exact device (mode, setpoint, room temp, zone), using the same characteristic UUIDs as
the bigthrilla reference in `../CLAUDE.md`. Author calls it "vibeware," tested on one
unit only (`9430-720`). It's installed on this RV's HA instance
(`/homeassistant/custom_components/coleman_mach_ble/`) and is the more promising path
to a working integration than building our own from scratch — this `colemanmach/`
project's role going forward is protocol reference + independent diagnostic tooling
(scan/enumerate/capture, run from outside the HA container to avoid adapter
contention), not a competing implementation.

Two merged PRs on that repo are worth knowing about:
- `e21b2b2c-379e-4166-b835-c71ef7eadfdf` = `CHAR_UNIT_ID`, an opaque 3-byte binary ID
  (not ASCII — display it as hex).
- `3016e3fc-1dbb-455e-b268-80750e36c950` = `CHAR_AVAILABLE_MODE`, a 10-byte positional
  bitmap (`byte[i] == 0x01` ⇒ that index in `ALL_MODES` is supported), inferred from a
  single cool-only unit and confirmed **not fully authoritative** — the thermostat's
  own display can hide a mode (e.g. `HEAT` with no furnace installed) that the
  characteristic still reports as available.

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

## Protocol — confirmed via live GATT dump (2026-08-02, `enumerate.py` from the Pi)

**Service:** `c9282723-4680-491b-a904-c066fa81061f` — confirmed present.

| Purpose | Characteristic UUID | Properties | Status |
|---|---|---|---|
| — (unknown) | `0575cdb7-d448-4bff-bc53-3b900d2a829f` | read | **New** — not in the reference doc. First-in-service-order; reading it (or, empirically, reading *any* characteristic first) always fails, see below. |
| Mode | `9230a9ef-347c-4645-8fd9-cbb830d714bf` | read, write | Confirmed exists, matches reference |
| — (unknown) | `8ca95e2d-daed-4b81-a91a-6eb46cb4ffac` | read | **New** — not in the reference doc, not in mallorybowes' `const.py` either as far as we've seen |
| Zone name | `beb89473-05fe-41a0-9896-2c082660f19a` | read, write | Confirmed exists (reference doc said read-only; this unit's properties include write too) |
| Unit ID | `e21b2b2c-379e-4166-b835-c71ef7eadfdf` | read | Matches `CHAR_UNIT_ID` from mallorybowes PR #1 — opaque binary, display as hex |
| Room temperature | `382b4008-084a-4158-b378-66674091b1e2` | read | Confirmed exists, matches reference |
| Setpoint | `09996813-fe7d-48ce-9b47-11634c80263c` | read, write | Confirmed exists, matches reference. Has a `0x2906` "Valid Range" descriptor — not yet read. |
| Available modes | `3016e3fc-1dbb-455e-b268-80750e36c950` | read | Matches `CHAR_AVAILABLE_MODE` from mallorybowes PR #2 |

Also present: standard GATT (`00001801`, Service Changed/indicate) and GAP
(`00001800`: Device Name, Appearance, Peripheral Preferred Connection Parameters,
Central Address Resolution, Resolvable Private Address Only) services — nothing
thermostat-specific there.

Candidate mode strings (still unverified against this unit): `OFF`, `FAN LOW`,
`FAN HIGH`, `COOL LOW`, `COOL HIGH`, `COOL AUTO LOW`, `COOL AUTO HIGH`, `HEAT`.

**Read behavior on an unbonded connection:** every characteristic in the
`c9282723-...` service is currently unreadable. The *first* read attempted in a fresh
connection — whichever characteristic that happens to be, not specifically
`0575cdb7-...` — fails with `GATT Protocol Error: Unlikely Error` (ATT code `0x0E`),
and every subsequent read in that same connection then fails with "Service Discovery
has not been performed yet" (BlueZ invalidates its service cache after the first
error). `0x0E` is BlueZ's generic/undefined ATT error; well-behaved peripherals are
supposed to return `0x05` (Insufficient Authentication) or `0x0F` (Insufficient
Encryption) instead when the real problem is "you're not paired," so this looks like a
firmware quirk on the thermostat's side rather than a bleak/BlueZ bug — but see
"Pairing" below, since standard pairing doesn't get us there either.

Notify support: not yet determined for any characteristic — couldn't get far enough to
check, since every characteristic is unreadable pre-pairing and pairing itself is the
open problem (`capture.py` will report `properties` for each once a connection can
actually read something).

## Pairing — reproducibly fails, root cause still open

Confirmed facts, from live testing against `00:A0:50:4E:E5:07` on 2026-08-02:

- The thermostat does have a real Bluetooth pairing mode: hold **UP + DOWN together
  for 5 seconds**; LCD then shows a 6-digit code. Confirmed independently via the
  `ManufacturerData.Value` flag flipping `00` → `AA` (see "Device" above).
- With pairing mode confirmed active (flag = `AA`) and a real 6-digit code in hand
  (`443649` on this occasion), `bluetoothctl pair 00:A0:50:4E:E5:07` **fails
  immediately and consistently**: the LE link connects fine (`Connected: yes`), but
  BlueZ reports `Failed to pair: org.bluez.Error.ConnectionAttemptFailed` within
  about a second — before the registered agent is ever asked for a passkey. Reproduced
  twice, with a `KeyboardOnly` agent, `pairable on` set explicitly first.
- This exactly reproduces what a separate, independent debugging session (a sandboxed
  Claude Code instance running inside the HA Core container, working through the
  mallorybowes integration's own coordinator) had already hit repeatedly, across two
  different agent capabilities (`NoInputNoOutput`, `KeyboardOnly`) and multiple
  physical pairing attempts. Two independent environments, same immediate failure —
  this is very unlikely to be bad luck/timing on our part.
- Running a live `bluetoothctl` agent process **at the same time** as a separate
  `bleak` connection attempt (hoping BlueZ would auto-escalate to pairing when a read
  failed) made things actively worse — the device started rapidly connecting and
  disconnecting instead of holding a connection at all. **Don't run two concurrent BLE
  clients against this device** — even for diagnosis, it seems to make the peripheral's
  radio/firmware unhappy, not just BlueZ.
- mallorybowes' own README describes this device requiring standard BLE
  pairing/bonding via `bluetoothctl`, and presumably that's worked on their own unit —
  so either firmware/hardware differs by unit or model, or there's something specific
  to this Pi's BlueZ version (5.86) or Bluetooth chip that's incompatible with how this
  thermostat expects pairing to be initiated.

**Resolved: it is standard BLE SMP pairing, not an app-layer scheme.** Confirmed by
capturing the Android Bluetooth stack's own debug log (`adb bugreport`, since this
OnePlus/Qualcomm build doesn't produce a standard `btsnoop_hci.log` — its logs live at
`/data/misc/bluetooth/logs/bluetooth_*.log` inside the bug report, human-readable text
not binary) while the RV Climate app reconnected to the thermostat:

- The **AC itself sends an SMP `Security Request`** (`SMP_OPCODE_SEC_REQ`, `0x0b`)
  immediately after ACL connection — pairing is peripheral-initiated by design, not
  something the central is supposed to demand up front.
- The phone had a real stored bond from previous use and re-encrypted using the stored
  LTK (`LE_START_ENCRYPTION`, `use_stk:false`, `key_size:16`) — no fresh passkey
  exchange needed, which is why "it didn't ask for the code" (see below, the 6-digit
  code turned out to be **static per-unit, not rotating**, confirmed by the user).
  This is a real link-layer bond, not application-layer trust.
- GATT service discovery succeeds *before* encryption completes — matches our own
  `enumerate.py` results (full service/characteristic table readable unbonded).

This directly explains why `bluetoothctl pair` fails: it makes the **central** send an
unsolicited `Pairing Request` the instant the link comes up, which is the wrong order
for a peripheral that expects to initiate its own `Security Request` first. Tested the
fix — plain `bluetoothctl connect` (not `pair`), with an agent already registered and
`pairable on` set, so BlueZ could react to the AC's own request instead of us jumping
ahead:

- **Still fails**, but differently: not `ConnectionAttemptFailed` anymore — now
  `Failed to connect: org.bluez.Error.Failed le-connection-abort-by-local`. Notice
  "by-**local**" — this is *our own* Pi's BlueZ aborting the connection, not the AC
  rejecting anything. Reproduced twice, including after a full adapter power-cycle
  (`bluetoothctl power off`/`power on`) in between, so it isn't simply a wedged
  adapter from repeated test attempts.
- `dmesg` on the Pi shows kernel-level Bluetooth HCI errors correlating with these
  attempts: `Bluetooth: hci0: Opcode 0x200e failed: -16` (`0x200e` =
  `LE Create Connection Cancel`, `-16` = `EBUSY`) recurring across the session, and a
  new `Bluetooth: hci0: ACL packet for unknown connection handle 64` right after the
  post-reset retry — evidence of a connection-teardown race at the kernel/HCI level,
  not a deliberate protocol rejection.
- The Pi's adapter is a **Broadcom BCM4345C0** (onboard Pi 4 chip, confirmed via
  `dmesg`: `hci0: BCM4345C0`). This exact error signature matches a known,
  still-unresolved class of BlueZ↔Broadcom-Pi-firmware race conditions in LE
  connection establishment — see
  [bluez/bluez#2115](https://github.com/bluez/bluez/issues/2115) (same symptom: link
  connects, dies in ~1s, no passkey ever requested, tried every standard
  workaround, closed unresolved) and
  [hbldh/bleak#1500](https://github.com/hbldh/bleak/issues/1500) (same opcode/error,
  labeled a BlueZ-not-bleak issue).

**Conclusion: this is very likely a hardware/firmware-level bug in the Pi's onboard
Broadcom Bluetooth chip's interaction with BlueZ's LE connection state machine,
specifically triggered by the timing of the AC's peripheral-initiated Security
Request — not something fixable via `bluetoothctl` flags, agent capability choice, or
protocol-level guessing from our side.** The mallorybowes README's standard pairing
instructions likely do work on hardware that doesn't share this specific chip/BlueZ
combination.

**Next step (not yet tried): swap the Bluetooth adapter.** A USB BLE dongle with a
different chipset (many cheap CSR/Intel-based ones are much better behaved with BlueZ
on Linux than Broadcom's Pi firmware) is the most likely real fix — plug it in, repeat
the exact `connect` sequence above, see if it pairs cleanly. If it does, that confirms
the onboard chip as the culprit and the fix is permanent-hardware, not a workaround.
An ESPHome Bluetooth proxy (already noted elsewhere as a fix for adapter *contention*)
would be a second, independent way to sidestep this same chip.

**macOS note:** CoreBluetooth (which `bleak` sits on top of) handles pairing at the OS
level via a system dialog a script can't drive — do pairing work on the Pi (BlueZ),
not from a Mac.

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
