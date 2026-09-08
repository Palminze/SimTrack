#!/usr/bin/env python3
"""
SimTrack Windows — standalone head tracking for sim racing
- Receives head pose from phone via WebSocket
- Writes FreeTrack shared memory (AC, ETS2, ATS, BeamNG, ...)
- Sends UDP to port 4242 (OpenTrack fallback for iRacing, ACC, Dirt Rally)
- Serves phone tracker page at http://<your-ip>:8080/index.html
"""

import asyncio
import json
import mmap
import os
import socket
import struct
import subprocess
import sys
import threading
import tkinter as tk
import traceback

# ── Auto-install aiohttp ──────────────────────────────────────────────────────
try:
    import aiohttp
    from aiohttp import web
except ImportError:
    print("Installing aiohttp, please wait...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "aiohttp"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import aiohttp
    from aiohttp import web

# ── Settings ──────────────────────────────────────────────────────────────────
# OpenTrack's UDP port is not always 4242 -- it varies by install, and a
# mismatch is silent: SimTrack keeps sending, OpenTrack keeps not listening,
# and nothing indicates why. Override it in config.json next to this file:
#     {"opentrack_port": 4376}
DEFAULTS = {
    "port": 8080,
    "opentrack_ip": "127.0.0.1",
    "opentrack_port": 4242,
}


def _load_config():
    cfg = dict(DEFAULTS)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    try:
        with open(path, encoding="utf-8") as fh:
            user = json.load(fh)
        cfg.update({k: v for k, v in user.items() if k in DEFAULTS})
        print(f"[config] loaded {path}")
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[config] ignoring {path}: {exc}")
    return cfg


CONFIG         = _load_config()
PORT           = CONFIG["port"]
OPENTRACK_IP   = CONFIG["opentrack_ip"]
OPENTRACK_PORT = CONFIG["opentrack_port"]

udp_sock  = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
clients   = set()
_ui_cb    = None   # set after GUI is created


# ── FreeTrack shared memory ───────────────────────────────────────────────────
# The byte layout lives in freetrack.py -- it must match the FreeTrack 2.0
# public interface exactly. Verify with: python tools/ft_check.py emit
from freetrack import FreeTrack
from tunnel import Tunnel

freetrack = FreeTrack()
if freetrack.active:
    print("[FreeTrack] Shared memory open — AC / ETS2 / BeamNG ready")
else:
    print(f"[FreeTrack] Inactive: {freetrack.error}")


# ── WebSocket handler ─────────────────────────────────────────────────────────
async def ws_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    clients.add(ws)
    print(f"\n[+] {request.remote}  ({len(clients)} connected)")
    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    d     = json.loads(msg.data)
                    yaw   = float(d["yaw"])
                    pitch = float(d["pitch"])
                    roll  = float(d["roll"])
                except (KeyError, ValueError, json.JSONDecodeError):
                    continue

                freetrack.write(yaw, pitch, roll)

                # UDP → OpenTrack (covers iRacing, ACC, Dirt Rally via OpenTrack)
                udp_sock.sendto(
                    struct.pack("<6d", 0.0, 0.0, 0.0, yaw, pitch, roll),
                    (OPENTRACK_IP, OPENTRACK_PORT)
                )

                # Relay to demo.html / other browser tabs
                for c in list(clients - {ws}):
                    try:
                        await c.send_str(msg.data)
                    except Exception:
                        pass

                if _ui_cb:
                    _ui_cb(yaw, pitch, roll, len(clients))

            elif msg.type == aiohttp.WSMsgType.ERROR:
                break
    finally:
        clients.discard(ws)
        if _ui_cb:
            _ui_cb(0.0, 0.0, 0.0, len(clients))
        print(f"[-] {request.remote}  ({len(clients)} connected)")
    return ws


async def _run_server():
    static_dir = os.path.dirname(os.path.abspath(__file__))
    app = web.Application()
    app.router.add_get("/ws", ws_handler)
    app.router.add_static("/", static_dir, show_index=True)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    await asyncio.Future()


server_error = None   # set if the aiohttp thread dies; shown in the GUI


def _server_thread():
    global server_error
    try:
        asyncio.run(_run_server())
    except Exception as exc:                          # noqa: BLE001
        server_error = f"{type(exc).__name__}: {exc}"
        print(f"[server] FAILED: {server_error}", file=sys.stderr)
        traceback.print_exc()


# ── GUI ───────────────────────────────────────────────────────────────────────
BG     = "#0c0c0c"
CARD   = "#111111"
EDGE   = "#1e1e1e"
GREEN  = "#00d96c"
AMBER  = "#f5a623"
DIM    = "#3a3a3a"
DIMTXT = "#555555"
WHITE  = "#cccccc"
FONT   = "Segoe UI"

def _local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


class SimTrackApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SimTrack")
        self.configure(bg=BG)
        self.resizable(False, False)
        self._build()
        self._health()

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self):
        pad = dict(padx=20)

        # Header
        tk.Label(self, text="SimTrack", bg=BG, fg=WHITE,
                 font=(FONT, 20, "bold")).pack(pady=(22, 2), **pad)
        tk.Label(self, text="Head tracking for sim racing",
                 bg=BG, fg=DIMTXT, font=(FONT, 9)).pack(pady=(0, 18), **pad)

        # ── Phone URL card ────────────────────────────────────────────────────
        self._card_start("OPEN ON PHONE")
        self._phone_url = tk.StringVar(value="starting secure tunnel…")
        tk.Label(self._card, textvariable=self._phone_url, bg=CARD, fg=GREEN,
                 font=("Consolas", 11, "bold"), wraplength=470, justify="left",
                 cursor="hand2").pack(anchor="w", padx=14, pady=(0, 4))
        self._phone_hint = tk.StringVar(
            value="The camera only works over HTTPS — waiting for the tunnel.")
        tk.Label(self._card, textvariable=self._phone_hint,
                 bg=CARD, fg=DIMTXT, font=(FONT, 8), wraplength=470,
                 justify="left").pack(anchor="w", padx=14, pady=(0, 6))
        tk.Label(self._card,
                 text=f"LAN: http://{_local_ip()}:{PORT}/demo.html  "
                      f"(PC demo only — phone camera will not start on http)",
                 bg=CARD, fg=DIMTXT, font=(FONT, 8)).pack(anchor="w",
                 padx=14, pady=(0, 10))
        self._card_end()

    # ── tunnel callbacks ─────────────────────────────────────────────────────
    def set_tunnel_url(self, url):
        self._phone_url.set(f"{url}/index.html")
        self._phone_hint.set("Open this in Safari / Chrome on your phone. "
                             "Allow camera when asked.")

    def set_tunnel_error(self, msg):
        self._phone_url.set("No HTTPS URL available")
        self._phone_hint.set(f"{msg} — the phone camera cannot start without one.")

        # ── Status card ───────────────────────────────────────────────────────
        self._card_start("STATUS")
        row = tk.Frame(self._card, bg=CARD)
        row.pack(fill="x", padx=14, pady=(0, 10))
        self._led = tk.Label(row, text="●", bg=CARD, fg=DIM,
                             font=(FONT, 13))
        self._led.pack(side="left")
        self._status = tk.StringVar(value="Waiting for phone…")
        tk.Label(row, textvariable=self._status, bg=CARD, fg=WHITE,
                 font=(FONT, 10)).pack(side="left", padx=(8, 0))
        self._card_end()

        # ── Angles card ───────────────────────────────────────────────────────
        self._card_start("TRACKING")
        row2 = tk.Frame(self._card, bg=CARD)
        row2.pack(fill="x", padx=14, pady=(0, 12))
        self._yaw_v   = tk.StringVar(value="0.0°")
        self._pitch_v = tk.StringVar(value="0.0°")
        self._roll_v  = tk.StringVar(value="0.0°")
        for lbl, var in [("Yaw", self._yaw_v), ("Pitch", self._pitch_v),
                          ("Roll", self._roll_v)]:
            box = tk.Frame(row2, bg="#181818",
                           highlightbackground=EDGE, highlightthickness=1)
            box.pack(side="left", expand=True, fill="x", padx=(0, 5))
            tk.Label(box, text=lbl, bg="#181818", fg=DIMTXT,
                     font=(FONT, 8)).pack(pady=(7, 1))
            tk.Label(box, textvariable=var, bg="#181818", fg=GREEN,
                     font=("Consolas", 15, "bold")).pack(pady=(0, 7))
        self._card_end()

        # ── Game compatibility ────────────────────────────────────────────────
        self._card_start("GAME COMPATIBILITY")
        games = [
            ("✓", "Assetto Corsa",          "FreeTrack  —  works out of the box"),
            ("✓", "Euro / American Truck",   "FreeTrack  —  works out of the box"),
            ("✓", "BeamNG.drive",            "FreeTrack  —  works out of the box"),
            ("⚙", "iRacing / ACC / Dirt",    "Needs OpenTrack  (see below)"),
        ]
        for icon, game, note in games:
            row = tk.Frame(self._card, bg=CARD)
            row.pack(fill="x", padx=14, pady=1)
            color = GREEN if icon == "✓" else AMBER
            tk.Label(row, text=icon, bg=CARD, fg=color,
                     font=(FONT, 9, "bold"), width=2).pack(side="left")
            tk.Label(row, text=game, bg=CARD, fg=WHITE,
                     font=(FONT, 9, "bold"), width=22, anchor="w").pack(side="left")
            tk.Label(row, text=note, bg=CARD, fg=DIMTXT,
                     font=(FONT, 8)).pack(side="left")

        tk.Label(self._card,
                 text=f"OpenTrack users: set Input = UDP over network, port "
                      f"{OPENTRACK_PORT}.",
                 bg=CARD, fg=WHITE, font=(FONT, 8)).pack(
            anchor="w", padx=14, pady=(8, 0))
        tk.Label(self._card,
                 text="Port must match OpenTrack exactly — change it in "
                      "config.json if yours differs.",
                 bg=CARD, fg=DIMTXT, font=(FONT, 8)).pack(
            anchor="w", padx=14, pady=(0, 10))
        self._card_end()

        self.geometry("540x540")

    # ── health poll ──────────────────────────────────────────────────────────
    def _health(self):
        """Surface failures that used to die silently in the server thread."""
        if server_error:
            self._led.config(fg="#ef4444")
            self._status.set(f"Server failed — {server_error}")
        elif not freetrack.active and not clients:
            # Only warn while idle -- never stomp on a live tracking readout.
            self._led.config(fg=AMBER)
            self._status.set(f"No game output — {freetrack.error}")
        self.after(1000, self._health)

    def _card_start(self, label):
        outer = tk.Frame(self, bg=CARD,
                         highlightbackground=EDGE, highlightthickness=1)
        outer.pack(fill="x", padx=20, pady=(0, 8))
        tk.Label(outer, text=label, bg=CARD, fg=DIMTXT,
                 font=(FONT, 7)).pack(anchor="w", padx=14, pady=(8, 4))
        self._card = outer

    def _card_end(self):
        self._card = None

    # ── live update (called from server thread via after) ─────────────────────
    def update_data(self, yaw, pitch, roll, n):
        self._yaw_v.set(f"{yaw:+.1f}°")
        self._pitch_v.set(f"{pitch:+.1f}°")
        self._roll_v.set(f"{roll:+.1f}°")
        if n > 0:
            self._led.config(fg=GREEN)
            self._status.set(f"Phone connected  ·  tracking active")
        else:
            self._led.config(fg=DIM)
            self._status.set("Waiting for phone…")


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    threading.Thread(target=_server_thread, daemon=True).start()

    app = SimTrackApp()

    # The LAN URL cannot start a phone camera (browsers require a secure
    # origin), so the tunnel is the only usable phone address today.
    tunnel = Tunnel(
        PORT,
        on_url=lambda u: app.after(0, lambda: app.set_tunnel_url(u)),
        on_error=lambda m: app.after(0, lambda: app.set_tunnel_error(m)),
    )
    tunnel.start()

    def _cb(yaw, pitch, roll, n):
        app.after(0, lambda: app.update_data(yaw, pitch, roll, n))

    _ui_cb = _cb
    app.mainloop()
