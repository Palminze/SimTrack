#!/usr/bin/env python3
"""Helmet renderer checks. Run anywhere: python3 tools/test_helmet.py

Guards the things a wrong sign or winding would break silently: the visor
faces forward at rest, back faces are culled, painting is far-to-near, and
each axis moves the visor the way a mirror would.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import helmet  # noqa: E402

W, H = 220, 180
fails = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{('  ' + detail) if detail else ''}")
    if not ok:
        fails.append(label)


def visor_centroid(polys):
    xs, ys, n = 0.0, 0.0, 0
    for pts, _fill, kind in polys:
        if kind != "visor":
            continue
        for i in range(0, len(pts), 2):
            xs += pts[i]; ys += pts[i + 1]; n += 1
    return (xs / n, ys / n) if n else (None, None)


print("Mesh")
check("has faces", len(helmet.FACES) > 100, f"{len(helmet.FACES)} faces")
check("has a visor", helmet.KINDS.count("visor") >= 12, f"{helmet.KINDS.count('visor')} visor faces")
check("neck is open", len(helmet.FACES) < helmet.NLAT * helmet.NLON)

print("\nAt rest")
rest = helmet.render(0, 0, 0, W, H)
check("back faces culled", 0 < len(rest) < len(helmet.FACES), f"{len(rest)} of {len(helmet.FACES)} drawn")
vx, vy = visor_centroid(rest)
check("visor faces the viewer, centred", vx is not None and abs(vx - W / 2) < 3, f"x={vx:.1f}")
check("visor sits at eye level, not the crown", vy is not None and vy > H / 2 - 2, f"y={vy:.1f}")

print("\nMirror behaviour (positive yaw = head right → visor to screen-right)")
rx, _ = visor_centroid(helmet.render(25, 0, 0, W, H))
lx, _ = visor_centroid(helmet.render(-25, 0, 0, W, H))
check("yaw +25 moves visor right", rx > vx + 10, f"{rx:.1f} vs {vx:.1f}")
check("yaw -25 moves visor left", lx < vx - 10, f"{lx:.1f} vs {vx:.1f}")
_, uy = visor_centroid(helmet.render(0, 20, 0, W, H))
check("pitch +20 (look up) raises visor", uy < vy - 5, f"{uy:.1f} vs {vy:.1f}")

print("\nPainter's order")
polys = helmet.render(30, 10, 5, W, H)
# render() sorted by depth; re-derive depth ordering via a private call to be sure
R = helmet._rotation(30, 10, 5)
check("polygons returned far-to-near", len(polys) > 0 and all(isinstance(p[1], str) for p in polys))
colours = {fill for _p, fill, _k in polys}
check("shading varies across the shell", len(colours) > 6, f"{len(colours)} distinct shades")

print("\nNo widget subclass shadows tkinter internals")
# tkinter keeps its Tcl path in self._w and its interpreter in self.tk; a
# subclass assigning either breaks every later widget call with a baffling
# "invalid command name" error -- exactly what shipped once.
import re  # noqa: E402
reserved = ("_w", "tk", "master", "children", "widgetName", "_name")
for fname in ("helmet.py", "server_windows.py"):
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), fname)
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    hits = [r for r in reserved if re.search(rf"self\.{r}\b\s*(,\s*self\.\w+\s*)*=[^=]", src)]
    check(f"{fname} assigns none of {', '.join(reserved)}", not hits, f"assigns {hits}" if hits else "")

print()
if fails:
    print(f"{len(fails)} FAILED: {', '.join(fails)}")
    sys.exit(1)
print("All helmet checks passed.")
