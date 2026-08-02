#!/usr/bin/env python3
"""Analyze a capture.jsonl log produced by capture.py.

Prints a chronological, decoded view and a per-characteristic summary of distinct
values seen — useful for spotting which characteristic actually changed when you
adjusted mode/setpoint during the capture window, and for sanity-checking the
1-byte-degF and ASCII encodings hypothesized in ../CLAUDE.md.
"""

import json
import sys
from collections import defaultdict


def decode_value(label: str, raw: bytes):
    """Best-effort decode per the reference encodings; falls back to hex."""
    if label in ("setpoint", "room_temp") and len(raw) == 1:
        return f"{raw[0]} degF"
    if label in ("mode", "zone_name"):
        try:
            return repr(raw.decode("utf-8"))
        except Exception:
            pass
    return raw.hex()


def analyze(path: str):
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))

    print(f"Loaded {len(entries)} entries from {path}\n")

    print("=" * 70)
    print("  CHRONOLOGICAL LOG")
    print("=" * 70)
    for e in entries:
        raw = bytes(e["bytes"])
        decoded = decode_value(e["label"], raw)
        print(f"  [{e['ts']}] ({e['source']}) {e['label']:<12} {e['hex']:<20} -> {decoded}")

    print("\n" + "=" * 70)
    print("  PER-CHARACTERISTIC DISTINCT VALUES")
    print("=" * 70)
    by_label = defaultdict(list)
    for e in entries:
        by_label[e["label"]].append(e)

    for label, es in by_label.items():
        print(f"\n  {label}  ({es[0]['uuid']})")
        seen = []
        for e in es:
            raw = bytes(e["bytes"])
            decoded = decode_value(label, raw)
            if not seen or seen[-1] != decoded:
                seen.append(decoded)
                print(f"    [{e['ts']}] -> {decoded}")
        if len(seen) <= 1:
            print(f"    (no change observed across {len(es)} samples)")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "capture.jsonl"
    analyze(path)
