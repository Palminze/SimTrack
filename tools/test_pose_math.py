#!/usr/bin/env python3
"""Why CENTER must subtract a rotation, not three angles.

Mirrors the maths in index.html. A phone propped below the monitor looks up
at the head, so the camera frame is pitched relative to the head frame. A
pure head yaw then decomposes, in camera Euler angles, into yaw plus spurious
roll and pitch. Expressing each frame relative to the rest orientation
(R0^T R) removes it exactly.
"""

import math
import sys

d2r = math.pi / 180


def rx(a): c, s = math.cos(a * d2r), math.sin(a * d2r); return [[1, 0, 0], [0, c, -s], [0, s, c]]
def ry(a): c, s = math.cos(a * d2r), math.sin(a * d2r); return [[c, 0, s], [0, 1, 0], [-s, 0, c]]
def mul(A, B): return [[sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
def T(A): return [[A[j][i] for j in range(3)] for i in range(3)]


def euler(R):
    """Same ZYX extraction the page uses (signs as in index.html)."""
    yaw = math.asin(-max(-1.0, min(1.0, R[2][0]))) / d2r
    pitch = math.atan2(R[2][1], R[2][2]) / d2r
    roll = math.atan2(R[1][0], R[0][0]) / d2r
    return -yaw, -pitch, roll


fails = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{('  ' + detail) if detail else ''}")
    if not ok:
        fails.append(label)


cam_tilt = 25.0                       # phone looks up at the face by 25°
R0 = rx(cam_tilt)                     # head at rest, as the camera sees it
R = mul(R0, ry(30.0))                 # head turns 30° about its own vertical axis

print(f"Camera tilted {cam_tilt:.0f}°, head turns 30° left, nothing else\n")

print("Old method: Euler angles of the raw frame, minus Euler angles at rest")
y0, p0, r0 = euler(R0)
y, p, r = euler(R)
old = (y - y0, p - p0, r - r0)
print(f"  yaw {old[0]:+6.1f}  pitch {old[1]:+6.1f}  roll {old[2]:+6.1f}")
check("old method leaks into roll", abs(old[2]) > 2.0, f"{old[2]:+.1f}° of phantom roll")

print("\nNew method: Euler angles of R0^T · R")
rel = euler(mul(T(R0), R))
print(f"  yaw {rel[0]:+6.1f}  pitch {rel[1]:+6.1f}  roll {rel[2]:+6.1f}")
check("yaw exact", abs(abs(rel[0]) - 30.0) < 1e-6, f"{rel[0]:+.3f}")
check("pitch zero", abs(rel[1]) < 1e-6, f"{rel[1]:+.3f}")
check("roll zero", abs(rel[2]) < 1e-6, f"{rel[2]:+.3f}")

print("\nSame for a pure nod and a pure tilt")
for name, Rm, axis in (("nod 15°", mul(R0, rx(15.0)), 1), ("tilt 10°", mul(R0, mul(ry(0), [[math.cos(10*d2r), -math.sin(10*d2r), 0], [math.sin(10*d2r), math.cos(10*d2r), 0], [0, 0, 1]])), 2)):
    e = euler(mul(T(R0), Rm))
    others = [abs(v) for i, v in enumerate(e) if i != axis]
    check(f"{name}: other axes stay at zero", max(others) < 1e-6, f"{tuple(round(v, 3) for v in e)}")

print()
if fails:
    print(f"{len(fails)} FAILED: {', '.join(fails)}")
    sys.exit(1)
print("All pose-maths checks passed.")
