#!/usr/bin/env python3
"""
SimTrack server — single port for HTTP + WebSocket, tunnel with cloudflared for HTTPS.

Setup:
  pip3 install aiohttp
  python3 server.py

Then in a NEW terminal:
  brew install cloudflared
  cloudflared tunnel --url http://localhost:8080

Open the cloudflare URL on your iPhone — camera will work.
"""

import asyncio
import json
import os
import socket
import struct
import sys

try:
    import aiohttp
    from aiohttp import web
except ImportError:
    sys.exit("Missing dependency: run  pip3 install aiohttp")

OPENTRACK_IP   = "127.0.0.1"
OPENTRACK_PORT = 4242
PORT           = 8080

udp     = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
clients = set()


async def ws_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    clients.add(ws)
    addr = request.remote
    print(f"\n  [+] Connected: {addr}  ({len(clients)} total)")
    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data  = json.loads(msg.data)
                    yaw   = float(data["yaw"])
                    pitch = float(data["pitch"])
                    roll  = float(data["roll"])
                except (KeyError, ValueError, json.JSONDecodeError):
                    continue

                # Forward to OpenTrack
                udp.sendto(struct.pack("<6d", 0.0, 0.0, 0.0, yaw, pitch, roll),
                           (OPENTRACK_IP, OPENTRACK_PORT))

                # Relay to all other clients (e.g. demo.html on Mac)
                for c in list(clients - {ws}):
                    try:
                        await c.send_str(msg.data)
                    except Exception:
                        pass

                sys.stdout.write(
                    f"\r  Yaw {yaw:+7.1f}°  Pitch {pitch:+7.1f}°  Roll {roll:+7.1f}°   "
                )
                sys.stdout.flush()

            elif msg.type == aiohttp.WSMsgType.ERROR:
                break
    finally:
        clients.discard(ws)
        print(f"\n  [-] Disconnected: {addr}  ({len(clients)} total)")
    return ws


async def main():
    static_dir = os.path.dirname(os.path.abspath(__file__))

    app = web.Application()
    app.router.add_get("/ws", ws_handler)
    app.router.add_static("/", static_dir, show_index=True)

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()

    print("=" * 56)
    print("  SimTrack")
    print("=" * 56)
    print(f"  Mac demo:  http://localhost:{PORT}/demo.html")
    print()
    print(f"  For iPhone, run in a NEW terminal:")
    print(f"    /tmp/cloudflared tunnel --url http://localhost:{PORT}")
    print()
    print(f"  Then open the  trycloudflare.com  URL on your iPhone")
    print("=" * 56)
    print("  Waiting for connections...\n")

    await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nSimTrack stopped.")
