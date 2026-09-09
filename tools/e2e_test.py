#!/usr/bin/env python3
"""End-to-end test of the PC pipeline, no GUI, no game, any platform.

Boots the real aiohttp app from server_windows.py, connects a fake phone over
WebSocket, and verifies pose comes out the UDP side — plus that the server
refuses to serve anything beyond the two public pages.
"""

import asyncio
import json
import os
import socket
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import aiohttp  # noqa: E402
from aiohttp import web  # noqa: E402

import server_windows as sw  # noqa: E402
from freetrack import decode  # noqa: E402

HOST, PORT = "127.0.0.1", 18080
fails = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{('  ' + detail) if detail else ''}")
    if not ok:
        fails.append(label)


async def main():
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.bind((sw.OPENTRACK_IP, sw.OPENTRACK_PORT))
    udp.setblocking(False)
    loop = asyncio.get_running_loop()

    runner = web.AppRunner(sw.build_app())
    await runner.setup()
    await web.TCPSite(runner, HOST, PORT).start()
    base = f"http://{HOST}:{PORT}"

    async with aiohttp.ClientSession() as s:
        print("HTTP surface")
        for path, want in [("/", 200), ("/index.html", 200), ("/demo.html", 200),
                           ("/server_windows.py", 404), ("/freetrack.py", 404),
                           ("/key.pem", 404), ("/.git/config", 404),
                           ("/CLAUDE.md", 404), ("/../server.py", 404)]:
            async with s.get(base + path) as r:
                check(f"GET {path} -> {want}", r.status == want, f"got {r.status}")

        print("\nSelf-hosted MediaPipe assets")
        for path, want_type in [("/assets/vision_bundle.mjs", "text/javascript"),
                                ("/assets/wasm/vision_wasm_internal.wasm", "application/wasm"),
                                ("/assets/face_landmarker.task", "application/octet-stream")]:
            async with s.get(base + path) as r:
                check(f"GET {path}", r.status == 200 and r.headers["Content-Type"] == want_type,
                      f"{r.status} {r.headers.get('Content-Type')}")
        for path in ["/assets/../server_windows.py", "/assets/%2e%2e/key.pem",
                     "/assets/missing.wasm", "/assets/wasm/../../freetrack.py"]:
            async with s.get(base + path) as r:
                check(f"GET {path} -> 404", r.status == 404, f"got {r.status}")

        print("\nPipeline: phone -> WebSocket -> UDP")
        spectator = await s.ws_connect(base + "/ws")   # stands in for demo.html
        phone = await s.ws_connect(base + "/ws")

        await phone.send_str(json.dumps({"yaw": 12.5, "pitch": -3.25, "roll": 1.5}))
        data = await asyncio.wait_for(loop.sock_recv(udp, 64), 2)
        x, y, z, yaw, pitch, roll = struct.unpack("<6d", data)
        check("UDP packet is 48 bytes", len(data) == 48)
        check("yaw/pitch/roll intact", (yaw, pitch, roll) == (12.5, -3.25, 1.5),
              f"got {(yaw, pitch, roll)}")

        msg = await asyncio.wait_for(spectator.receive(), 2)
        relayed = json.loads(msg.data)
        check("relayed to other clients", relayed["yaw"] == 12.5)

        ft = sw.freetrack.read_back()
        check("FreeTrack buffer written (yaw inverted by default)",
              abs(ft["Yaw"] - (-12.5)) < 0.01, f"got {ft['Yaw']:.2f}")

        print("\nHostile input does not kill the stream")
        for bad in ["not json", '{"yaw": "x", "pitch": 0, "roll": 0}', '{"pitch": 1}',
                    '{"yaw": 1e999, "pitch": 0, "roll": 0}']:
            await phone.send_str(bad)
        await phone.send_str(json.dumps({"yaw": 1.0, "pitch": 2.0, "roll": 3.0}))
        got, seen = None, []
        deadline = loop.time() + 2
        while loop.time() < deadline:
            try:
                pkt = await asyncio.wait_for(loop.sock_recv(udp, 64), 0.5)
            except asyncio.TimeoutError:
                break
            vals = struct.unpack("<6d", pkt)[3:]
            seen.append(vals)
            got = vals
            if vals == (1.0, 2.0, 3.0):
                break
        check("stream alive after garbage", got == (1.0, 2.0, 3.0), f"last {got}")
        finite = all(v == v and abs(v) != float("inf") for vs in seen for v in vs)
        check("no non-finite values reached UDP", finite, f"saw {seen}")

        await phone.close()
        await spectator.close()

    await runner.cleanup()
    udp.close()

    print()
    if fails:
        print(f"{len(fails)} FAILED: {', '.join(fails)}")
        return 1
    print("All end-to-end checks passed.")
    return 0


sys.exit(asyncio.run(main()))
