#!/usr/bin/env python3
"""
SimTrack — head tracking for sim racing from your phone's camera.

Runs on the gaming PC and is the only thing a customer installs:
- serves the phone setup page over http (:8080) and the tracker over https
  (:8443), using a certificate SimTrack issues to its own LAN address, so the
  phone camera works with no tunnel and nothing outside the home network
- receives head pose over WebSocket
- writes FreeTrack shared memory; the NPClient / freetrackclient DLLs in bin/
  hand it to games directly (TrackIR titles and FreeTrack titles alike)
- also emits UDP 4242 for anyone who prefers OpenTrack (optional)
"""

import asyncio
import json
import os
import socket
import struct
import subprocess
import sys
import threading
import tkinter as tk
import traceback

# ── Where things live ─────────────────────────────────────────────────────────
# PyInstaller (onedir) unpacks bundled data under sys._MEIPASS; config.json is
# looked for next to the executable so testers can edit it without digging.
FROZEN  = bool(getattr(sys, "frozen", False))
BASE    = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.dirname(sys.executable) if FROZEN else BASE


def _ensure(module, pip_name):
    """Source runs auto-install; the packaged exe already has everything."""
    try:
        return __import__(module)
    except ImportError:
        if FROZEN:
            raise
        print(f"Installing {pip_name}, please wait...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return __import__(module)


_ensure("aiohttp", "aiohttp")
_ensure("cryptography", "cryptography")
_ensure("qrcode", "qrcode")

import aiohttp                      # noqa: E402
from aiohttp import web             # noqa: E402

import certs                        # noqa: E402
from freetrack import FreeTrack, register_client_dll, register_npclient   # noqa: E402
from helmet import HelmetView       # noqa: E402

# The packaged app has no console, so everything printed goes to a log file
# testers can send back. Source runs keep printing to the terminal.
if FROZEN:
    _log = open(os.path.join(certs.user_dir(), "simtrack.log"), "a",
                buffering=1, encoding="utf-8")
    sys.stdout = sys.stderr = _log

# ── Settings ──────────────────────────────────────────────────────────────────
# Overridable in config.json next to the app, e.g. {"invert_yaw": true}.
# opentrack_port only matters to OpenTrack users; it varies by install and a
# mismatch is silent, hence it is shown in the window.
DEFAULTS = {
    "port": 8080,             # http: phone setup page + certificate download
    "https_port": 8443,       # https: the tracker itself
    "opentrack_ip": "127.0.0.1",
    "opentrack_port": 4242,
    "invert_yaw": False,
    "invert_pitch": False,
    "invert_roll": False,
}


def _load_config():
    cfg = dict(DEFAULTS)
    path = os.path.join(APP_DIR, "config.json")
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


def _local_ip():
    """The LAN address the phone will reach us on (no packets are sent)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:                                 # noqa: BLE001
        return "localhost"


CONFIG         = _load_config()
PORT           = CONFIG["port"]
HTTPS_PORT     = CONFIG["https_port"]
OPENTRACK_IP   = CONFIG["opentrack_ip"]
OPENTRACK_PORT = CONFIG["opentrack_port"]
LAN_IP         = _local_ip()
SETUP_URL      = f"http://{LAN_IP}:{PORT}/"
TRACKER_URL    = f"https://{LAN_IP}:{HTTPS_PORT}/"

DLL_DIR   = os.path.join(BASE, "bin")
GAMES_CSV = os.path.join(BASE, "dll", "games.csv")

udp_sock  = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
clients   = set()
_ui_cb    = None          # set once the GUI exists
CA_PATH   = None          # set once certificates are issued
server_error = None       # set if the server thread dies; shown in the GUI


# ── FreeTrack shared memory ───────────────────────────────────────────────────
# The byte layout lives in freetrack.py -- it must match the FreeTrack 2.0
# public interface exactly. Verify with: python tools/ft_check.py emit
freetrack = FreeTrack()
if freetrack.active:
    print("[FreeTrack] Shared memory open")

    # Games find SimTrack's client DLLs through these registry paths --
    # TrackIR titles via NPClient, FreeTrack titles via FreeTrackClient.
    for label, err in (("FreeTrack DLL", register_client_dll(DLL_DIR)),
                       ("TrackIR DLL", register_npclient(DLL_DIR))):
        print(f"[{label}] {'registered: ' + DLL_DIR if err is None else 'NOT registered: ' + err}")

    _missing = [n for n in ("NPClient.dll", "NPClient64.dll",
                            "freetrackclient.dll", "freetrackclient64.dll")
                if not os.path.exists(os.path.join(DLL_DIR, n))]
    if _missing:
        print(f"[warn] missing from bin/: {', '.join(_missing)} — "
              f"games cannot connect until they exist")

    freetrack.start_game_watch(GAMES_CSV)
else:
    print(f"[FreeTrack] Inactive: {freetrack.error}")


# ── Pose handling ─────────────────────────────────────────────────────────────
def _angle(v):
    """Reject non-finite pose values and clamp to a physical head range."""
    v = float(v)
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError("non-finite angle")
    return max(-180.0, min(180.0, v))


def _emit(yaw, pitch, roll):
    """One pose to every output: shared memory for the DLLs, UDP for OpenTrack."""
    freetrack.write(yaw, pitch, roll)
    udp_sock.sendto(struct.pack("<6d", 0.0, 0.0, 0.0, yaw, pitch, roll),
                    (OPENTRACK_IP, OPENTRACK_PORT))


async def ws_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    clients.add(ws)
    print(f"[+] {request.remote}  ({len(clients)} connected)")
    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    d     = json.loads(msg.data)
                    yaw   = _angle(d["yaw"])
                    pitch = _angle(d["pitch"])
                    roll  = _angle(d["roll"])
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    continue

                if CONFIG["invert_yaw"]:   yaw   = -yaw
                if CONFIG["invert_pitch"]: pitch = -pitch
                if CONFIG["invert_roll"]:  roll  = -roll

                _emit(yaw, pitch, roll)

                # Relay to any other connected page (the Mac demo uses this)
                for c in list(clients - {ws}):
                    try:
                        await c.send_str(msg.data)
                    except Exception:                 # noqa: BLE001
                        pass

                if _ui_cb:
                    _ui_cb(yaw, pitch, roll, len(clients))

            elif msg.type == aiohttp.WSMsgType.ERROR:
                break
    finally:
        clients.discard(ws)
        if not clients:
            # Phone gone: recentre rather than leave the game staring at the
            # last angle it received.
            _emit(0.0, 0.0, 0.0)
        if _ui_cb:
            _ui_cb(0.0, 0.0, 0.0, len(clients))
        print(f"[-] {request.remote}  ({len(clients)} connected)")
    return ws


# ── HTTP surface ──────────────────────────────────────────────────────────────
# Whitelist only. Serving the whole directory would hand out source and keys
# to anyone on the network who found the address.

# Self-hosted MediaPipe (assets/): browsers refuse to stream-compile wasm
# served as text/plain, and ES module imports need a javascript type.
ASSET_TYPES = {
    ".mjs":  "text/javascript",
    ".js":   "text/javascript",
    ".wasm": "application/wasm",
    ".task": "application/octet-stream",
    ".woff2": "font/woff2",
}


def build_app(ca_path=None):
    assets_dir = os.path.join(BASE, "assets")

    def file(name, **headers):
        async def handler(request):
            return web.FileResponse(os.path.join(BASE, name), headers=headers or None)
        return handler

    async def setup_page(request):
        with open(os.path.join(BASE, "setup.html"), encoding="utf-8") as fh:
            html = fh.read().replace("{{HTTPS_URL}}", TRACKER_URL)
        return web.Response(text=html, content_type="text/html")

    async def root(request):
        # Same address, two jobs: over https it is the tracker, over plain http
        # (which cannot start a camera) it is the one-time setup page.
        if request.secure:
            return await file("index.html")(request)
        return await setup_page(request)

    async def ca_cert(request):
        path = ca_path or CA_PATH
        if not path or not os.path.exists(path):
            raise web.HTTPNotFound()
        return web.FileResponse(path, headers={
            "Content-Type": "application/x-x509-ca-cert",
            "Content-Disposition": 'attachment; filename="simtrack-ca.crt"',
        })

    async def asset(request):
        full = os.path.realpath(os.path.join(assets_dir, request.match_info["path"]))
        # realpath + prefix check kills .. traversal out of assets/
        if not full.startswith(os.path.realpath(assets_dir) + os.sep):
            raise web.HTTPNotFound()
        ext = os.path.splitext(full)[1].lower()
        if ext not in ASSET_TYPES or not os.path.isfile(full):
            raise web.HTTPNotFound()
        return web.FileResponse(full, headers={"Content-Type": ASSET_TYPES[ext]})

    app = web.Application()
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/", root)
    app.router.add_get("/index.html", file("index.html"))
    app.router.add_get("/setup", setup_page)
    app.router.add_get("/simtrack-ca.crt", ca_cert)
    app.router.add_get("/assets/{path:.+}", asset)
    return app


async def _run_server():
    global CA_PATH
    paths = certs.ensure_certs(LAN_IP)
    CA_PATH = paths["ca"]
    print(f"[certs] CA {CA_PATH}")

    runner = web.AppRunner(build_app())
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    await web.TCPSite(runner, "0.0.0.0", HTTPS_PORT,
                      ssl_context=certs.ssl_context(paths["cert"], paths["key"])).start()
    print(f"[server] setup   {SETUP_URL}")
    print(f"[server] tracker {TRACKER_URL}")
    await asyncio.Future()


def _server_thread():
    global server_error
    try:
        asyncio.run(_run_server())
    except Exception as exc:                          # noqa: BLE001
        server_error = f"{type(exc).__name__}: {exc}"
        print(f"[server] FAILED: {server_error}", file=sys.stderr)
        traceback.print_exc()


# ── GUI ───────────────────────────────────────────────────────────────────────
# Same palette as the phone page: asphalt, warm off-white, one papaya accent.
BG     = "#111315"
CARD   = "#1a1d21"
INSET  = "#0b0d0f"
EDGE   = "#2a2f36"
ACCENT = "#ff7a1a"
GREEN  = ACCENT          # historical name, used for "good" state below
AMBER  = "#f5a623"
RED    = "#ff3b3b"
DIM    = "#3a4048"
DIMTXT = "#8a9099"
WHITE  = "#f2f0ea"
FONT   = "Segoe UI"
MONO   = "Consolas"


def _draw_qr(canvas, text, size):
    """Render a QR code onto a tkinter canvas with no image library needed."""
    import qrcode
    qr = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(text)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    n = len(matrix)
    cell = max(1, size // n)
    off = (size - cell * n) // 2
    canvas.create_rectangle(0, 0, size, size, fill="white", outline="")
    for y, row in enumerate(matrix):
        for x, dark in enumerate(row):
            if dark:
                canvas.create_rectangle(off + x * cell, off + y * cell,
                                        off + (x + 1) * cell, off + (y + 1) * cell,
                                        fill="black", outline="")


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
        # Livery-style header: wordmark on a papaya block, like the phone page.
        head = tk.Frame(self, bg=BG)
        head.pack(fill="x", padx=20, pady=(20, 14))
        tk.Label(head, text="  SIMTRACK  ", bg=ACCENT, fg=BG,
                 font=(FONT, 15, "bold", "italic")).pack(side="left")
        tk.Label(head, text="head tracking for sim racing", bg=BG, fg=DIMTXT,
                 font=(FONT, 9)).pack(side="left", padx=(12, 0))

        # ── Connect phone ─────────────────────────────────────────────────────
        self._card_start("CONNECT YOUR PHONE")
        row = tk.Frame(self._card, bg=CARD)
        row.pack(fill="x", padx=14, pady=(0, 10))

        qr_size = 132
        qr = tk.Canvas(row, width=qr_size, height=qr_size, bg="white",
                       highlightthickness=0)
        qr.pack(side="left", padx=(0, 16))
        if LAN_IP != "localhost":
            _draw_qr(qr, SETUP_URL, qr_size)
        else:
            qr.create_text(qr_size // 2, qr_size // 2, text="no network",
                           fill="black", font=(FONT, 9))

        steps = tk.Frame(row, bg=CARD)
        steps.pack(side="left", fill="both", expand=True)
        for n, text in (("1", "Scan this code with your phone's camera"),
                        ("2", "Install the SimTrack certificate (one time)"),
                        ("3", "Open the tracker link on that page")):
            line = tk.Frame(steps, bg=CARD)
            line.pack(anchor="w", pady=(0, 5))
            tk.Label(line, text=n, bg=CARD, fg=GREEN, width=2,
                     font=(MONO, 10, "bold")).pack(side="left")
            tk.Label(line, text=text, bg=CARD, fg=WHITE,
                     font=(FONT, 9)).pack(side="left")
        tk.Label(steps, text=f"or type  {SETUP_URL}", bg=CARD, fg=DIMTXT,
                 font=(MONO, 8)).pack(anchor="w", pady=(6, 0))
        tk.Label(steps, text=f"tracker  {TRACKER_URL}", bg=CARD, fg=DIMTXT,
                 font=(MONO, 8)).pack(anchor="w")
        self._card_end()

        # ── Status ────────────────────────────────────────────────────────────
        self._card_start("STATUS")
        row = tk.Frame(self._card, bg=CARD)
        row.pack(fill="x", padx=14, pady=(0, 10))
        self._led = tk.Label(row, text="●", bg=CARD, fg=DIM, font=(FONT, 13))
        self._led.pack(side="left")
        self._status = tk.StringVar(value="Starting…")
        tk.Label(row, textvariable=self._status, bg=CARD, fg=WHITE,
                 font=(FONT, 10), wraplength=440, justify="left").pack(
            side="left", padx=(8, 0))
        self._card_end()

        # ── Tracking ──────────────────────────────────────────────────────────
        self._card_start("TRACKING")
        row2 = tk.Frame(self._card, bg=CARD)
        row2.pack(fill="x", padx=14, pady=(0, 12))
        # The helmet mirrors the driver, so a glance confirms every axis;
        # the numbers stack beside it.
        self._helmet = HelmetView(row2, width=230, height=190, bg=INSET)
        self._helmet.pack(side="left", padx=(0, 10))
        stack = tk.Frame(row2, bg=CARD)
        stack.pack(side="left", fill="both", expand=True)
        self._yaw_v   = tk.StringVar(value="+0.0°")
        self._pitch_v = tk.StringVar(value="+0.0°")
        self._roll_v  = tk.StringVar(value="+0.0°")
        for lbl, var in (("Yaw", self._yaw_v), ("Pitch", self._pitch_v),
                         ("Roll", self._roll_v)):
            box = tk.Frame(stack, bg=INSET)
            box.pack(fill="x", pady=(0, 6))
            tk.Label(box, text=lbl, bg=INSET, fg=DIMTXT,
                     font=(FONT, 8)).pack(anchor="w", padx=10, pady=(6, 0))
            tk.Label(box, textvariable=var, bg=INSET, fg=WHITE,
                     font=(MONO, 17, "bold")).pack(anchor="w", padx=10, pady=(0, 6))
        self._card_end()

        # ── Games ─────────────────────────────────────────────────────────────
        self._card_start("GAMES")
        games = (
            ("✓", "Assetto Corsa · iRacing · ACC", "built in — start SimTrack, then the game"),
            ("✓", "ETS2 · ATS · BeamNG",           "built in — enable FreeTrack in game settings"),
            ("⚙", "Anything via OpenTrack",       f"optional — UDP input, port {OPENTRACK_PORT}"),
        )
        for icon, game, note in games:
            line = tk.Frame(self._card, bg=CARD)
            line.pack(fill="x", padx=14, pady=1)
            tk.Label(line, text=icon, bg=CARD, fg=GREEN if icon == "✓" else AMBER,
                     font=(FONT, 9, "bold"), width=2).pack(side="left")
            tk.Label(line, text=game, bg=CARD, fg=WHITE,
                     font=(FONT, 9, "bold"), width=26, anchor="w").pack(side="left")
            tk.Label(line, text=note, bg=CARD, fg=DIMTXT,
                     font=(FONT, 8)).pack(side="left")
        tk.Label(self._card, text="", bg=CARD).pack(pady=(0, 4))
        self._card_end()

        self.geometry("580x740")

    # ── health poll ──────────────────────────────────────────────────────────
    def _health(self):
        """Surface failures instead of letting them look like 'waiting'."""
        if server_error:
            self._led.config(fg=RED)
            self._status.set(f"Server failed — {server_error}")
        elif CA_PATH is None:
            self._led.config(fg=DIM)
            self._status.set("Starting…")
        elif not freetrack.active and not clients:
            self._led.config(fg=AMBER)
            self._status.set(f"No game output — {freetrack.error}")
        elif freetrack.current_game and not clients:
            self._led.config(fg=AMBER)
            self._status.set(f"{freetrack.current_game} connected — waiting for phone…")
        elif not clients:
            self._led.config(fg=DIM)
            self._status.set("Waiting for phone…")
        self.after(1000, self._health)

    def _card_start(self, label):
        # Flat panels, no outlines: contrast against the ground does the work.
        outer = tk.Frame(self, bg=CARD)
        outer.pack(fill="x", padx=20, pady=(0, 8))
        tk.Label(outer, text=label, bg=CARD, fg=ACCENT,
                 font=(FONT, 7, "bold")).pack(anchor="w", padx=14, pady=(8, 4))
        self._card = outer

    def _card_end(self):
        self._card = None

    # ── live update (called from server thread via after) ─────────────────────
    def update_data(self, yaw, pitch, roll, n):
        self._yaw_v.set(f"{yaw:+.1f}°")
        self._pitch_v.set(f"{pitch:+.1f}°")
        self._roll_v.set(f"{roll:+.1f}°")
        self._helmet.set_pose(yaw, pitch, roll)
        if n > 0:
            self._led.config(fg=GREEN)
            self._status.set("Phone connected  ·  tracking active")
        else:
            self._led.config(fg=DIM)
            self._status.set("Waiting for phone…")


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    threading.Thread(target=_server_thread, daemon=True).start()

    app = SimTrackApp()

    def _cb(yaw, pitch, roll, n):
        app.after(0, lambda: app.update_data(yaw, pitch, roll, n))

    _ui_cb = _cb
    app.mainloop()
