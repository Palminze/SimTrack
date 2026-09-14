#!/usr/bin/env python3
"""
A low-poly racing helmet that turns with the tracked head, drawn on a plain
tkinter canvas -- no GL, no image library, so it packages into the exe as is.

Mesh: a unit sphere (y up, +z toward the viewer), slightly taller than wide,
open at the neck, with a papaya visor across the front. Faces are flat-shaded
from a fixed light, back faces culled, and painted far-to-near.

The helmet is a MIRROR of the driver, like a screen in front of you: turn
your head right and the visor swings to screen-right. The three sign
constants below are the only thing to touch if a real-world test shows an
axis moving the wrong way.
"""

from __future__ import annotations

import math
import tkinter as tk

YAW_SIGN, PITCH_SIGN, ROLL_SIGN = 1.0, -1.0, -1.0

NLAT, NLON = 10, 18
SHELL_DARK, SHELL_LIGHT = (0x23, 0x28, 0x2e), (0x6b, 0x74, 0x80)
VISOR_DARK, VISOR_LIGHT = (0x7a, 0x36, 0x08), (0xff, 0x8a, 0x2a)
OUTLINE = "#0b0d0f"
_LIGHT = (-0.4, 0.6, 0.7)


def _norm(v):
    l = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
    return (v[0] / l, v[1] / l, v[2] / l)


_LIGHT = _norm(_LIGHT)


def _build():
    """Vertices, faces (outward winding) and a kind per face: shell / visor."""
    verts = []
    for i in range(NLAT + 1):
        phi = math.pi * i / NLAT
        for j in range(NLON):
            th = 2 * math.pi * j / NLON
            verts.append((math.sin(phi) * math.sin(th),
                          1.08 * math.cos(phi),                  # a touch taller than wide
                          math.sin(phi) * math.cos(th)))
    faces, kinds = [], []
    for i in range(NLAT):
        for j in range(NLON):
            a = i * NLON + j
            b = i * NLON + (j + 1) % NLON
            c = (i + 1) * NLON + (j + 1) % NLON
            d = (i + 1) * NLON + j
            cy = sum(verts[k][1] for k in (a, b, c, d)) / 4
            cz = sum(verts[k][2] for k in (a, b, c, d)) / 4
            if cy < -0.78:
                continue                                          # neck opening
            faces.append((a, d, c, b))                            # reversed → outward normals
            kinds.append("visor" if (-0.5 < cy < 0.2 and cz > 0.35) else "shell")
    return verts, faces, kinds


VERTS, FACES, KINDS = _build()


def _rotation(yaw, pitch, roll):
    """R = Ry(yaw) · Rx(pitch) · Rz(roll), signs applied for the mirror view."""
    y, p, r = (math.radians(YAW_SIGN * yaw), math.radians(PITCH_SIGN * pitch),
               math.radians(ROLL_SIGN * roll))
    cy, sy, cp, sp, cr, sr = math.cos(y), math.sin(y), math.cos(p), math.sin(p), math.cos(r), math.sin(r)
    ry = ((cy, 0, sy), (0, 1, 0), (-sy, 0, cy))
    rx = ((1, 0, 0), (0, cp, -sp), (0, sp, cp))
    rz = ((cr, -sr, 0), (sr, cr, 0), (0, 0, 1))

    def mul(A, B):
        return tuple(tuple(sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)) for i in range(3))
    return mul(ry, mul(rx, rz))


def _shade(kind, intensity):
    lo, hi = (VISOR_DARK, VISOR_LIGHT) if kind == "visor" else (SHELL_DARK, SHELL_LIGHT)
    t = 0.25 + 0.75 * max(0.0, min(1.0, intensity))
    return "#%02x%02x%02x" % tuple(int(lo[i] + (hi[i] - lo[i]) * t) for i in range(3))


def render(yaw, pitch, roll, width, height):
    """Polygons to paint, far-to-near: list of (flat point list, fill colour, kind)."""
    R = _rotation(yaw, pitch, roll)
    rv = [(R[0][0] * x + R[0][1] * y + R[0][2] * z,
           R[1][0] * x + R[1][1] * y + R[1][2] * z,
           R[2][0] * x + R[2][1] * y + R[2][2] * z) for x, y, z in VERTS]
    cx, cy, s = width / 2, height / 2, min(width, height) * 0.42
    out = []
    for face, kind in zip(FACES, KINDS):
        a, b, c = rv[face[0]], rv[face[1]], rv[face[2]]
        u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        n = _norm((u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]))
        if n[2] <= 0:
            continue                                              # facing away
        depth = sum(rv[k][2] for k in face) / 4
        pts = []
        for k in face:
            pts.extend((cx + rv[k][0] * s, cy - rv[k][1] * s))
        light = n[0] * _LIGHT[0] + n[1] * _LIGHT[1] + n[2] * _LIGHT[2]
        out.append((depth, pts, _shade(kind, light), kind))
    out.sort(key=lambda f: f[0])
    return [(pts, fill, kind) for _d, pts, fill, kind in out]


class HelmetView(tk.Canvas):
    """Canvas that redraws at ~30fps whenever the pose it was given changes."""

    def __init__(self, master, width=220, height=180, bg="#0b0d0f", **kw):
        super().__init__(master, width=width, height=height, bg=bg,
                         highlightthickness=0, **kw)
        self._w, self._h = width, height
        self._pose = (0.0, 0.0, 0.0)
        self._shown = None
        self._draw()
        self.after(33, self._tick)

    def set_pose(self, yaw, pitch, roll):
        self._pose = (yaw, pitch, roll)

    def _tick(self):
        if self._pose != self._shown:
            self._draw()
        self.after(33, self._tick)

    def _draw(self):
        self.delete("all")
        for pts, fill, _kind in render(*self._pose, self._w, self._h):
            self.create_polygon(pts, fill=fill, outline=OUTLINE, width=1)
        self._shown = self._pose
