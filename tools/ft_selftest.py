#!/usr/bin/env python3
"""Validate FreeTrack packing without a game or Windows. Run: python3 tools/ft_selftest.py"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from freetrack import FT_DATA, FT_HEAP, FreeTrack, decode  # noqa: E402

fails = []


def check(label, got, want, tol=1e-4):
    ok = abs(got - want) <= tol if isinstance(want, float) else got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}: got {got!r}, want {want!r}")
    if not ok:
        fails.append(label)


print("Struct sizes")
check("FTData size", FT_DATA.size, 92)
check("FTHeap size", FT_HEAP.size, 108)

print("\nField offsets (Yaw must sit at byte 12, right after the three ints)")
check("Yaw offset", struct.calcsize("<3i"), 12)
check("marker X1 offset", struct.calcsize("<3i15f"), 72)

print("\nRound trip: 30 deg yaw, -15 deg pitch, 5 deg roll")
ft = FreeTrack(invert_yaw=False, invert_pitch=False, invert_roll=False)
d = decode(ft.pack(30.0, -15.0, 5.0, 1.0, 2.0, 3.0))
check("Yaw", d["Yaw"], 30.0)
check("Pitch", d["Pitch"], -15.0)
check("Roll", d["Roll"], 5.0)
check("X", d["X"], 1.0)
check("CamWidth", d["CamWidth"], 640)

print("\nAngles stored as radians, not degrees")
raw = struct.unpack_from("<3i20f", ft.pack(90.0, 0.0, 0.0))
check("raw yaw field", round(raw[3], 4), 1.5708)

print("\nDataID increments each frame")
a = decode(ft.pack(0, 0, 0))["DataID"]
b = decode(ft.pack(0, 0, 0))["DataID"]
check("DataID advances", b - a, 1)

print("\nInversion flags")
inv = FreeTrack(invert_yaw=True, invert_pitch=True, invert_roll=False)
d = decode(inv.pack(30.0, -15.0, 5.0))
check("inverted yaw", d["Yaw"], -30.0)
check("inverted pitch", d["Pitch"], 15.0)
check("roll untouched", d["Roll"], 5.0)

print("\nOld layout comparison")
old = struct.Struct("<3i 14f i")
print(f"  old struct was {old.size} bytes vs {FT_HEAP.size} required "
      f"({FT_HEAP.size - old.size} bytes short)")
old_bytes = old.pack(1, 640, 480, *([0.0] * 8), 0.0, 0.0, 0.0, 30.0, -15.0, 5.0, 0)
stale = struct.unpack_from("<f", old_bytes, 12)[0]
print(f"  a game reading Yaw at offset 12 from the old layout saw {stale} "
      f"(marker X1), not 30.0")

print()
if fails:
    print(f"{len(fails)} FAILED: {', '.join(fails)}")
    sys.exit(1)
print("All checks passed.")
