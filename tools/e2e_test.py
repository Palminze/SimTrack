#!/usr/bin/env python3
"""End-to-end test of the PC pipeline, no GUI, no game, any platform.

Boots the real aiohttp app from server_windows.py on both an http and an
https site (with a certificate from a throwaway CA), plays phone over a
secure WebSocket, and verifies pose comes out the UDP side -- plus that the
server serves exactly the public surface and nothing else.
"""

import asyncio
import json
import os
import socket
import struct
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import aiohttp  # noqa: E402
from aiohttp import web  # noqa: E402

import certs  # noqa: E402
import server_windows as sw  # noqa: E402

HOST, HTTP, HTTPS = "127.0.0.1", 18080, 18443
fails = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{('  ' + detail) if detail else ''}")
    if not ok:
        fails.append(label)


async def recv_udp(udp, loop, timeout=2.0):
    pkt = await asyncio.wait_for(loop.sock_recv(udp, 64), timeout)
    return struct.unpack("<6d", pkt)


async def main(tmp):
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.bind((sw.OPENTRACK_IP, sw.OPENTRACK_PORT))
    udp.setblocking(False)
    loop = asyncio.get_running_loop()

    paths = certs.ensure_certs(HOST, tmp)
    runner = web.AppRunner(sw.build_app(ca_path=paths["ca"]))
    await runner.setup()
    await web.TCPSite(runner, HOST, HTTP).start()
    await web.TCPSite(runner, HOST, HTTPS,
                      ssl_context=certs.ssl_context(paths["cert"], paths["key"])).start()
    http, https = f"http://{HOST}:{HTTP}", f"https://{HOST}:{HTTPS}"

    async with aiohttp.ClientSession() as s:
        print("Public surface (http)")
        for path, want in [("/", 200), ("/index.html", 200), ("/setup", 200),
                           ("/simtrack-ca.crt", 200),
                           ("/demo.html", 404), ("/server_windows.py", 404),
                           ("/freetrack.py", 404), ("/certs.py", 404),
                           ("/key.pem", 404), ("/.git/config", 404),
                           ("/CLAUDE.md", 404), ("/../server.py", 404)]:
            async with s.get(http + path) as r:
                check(f"GET {path} -> {want}", r.status == want, f"got {r.status}")

        print("\nOne address, two jobs")
        async with s.get(http + "/") as r:
            body = await r.text()
            check("http / is the setup page", "Connect your phone" in body)
            check("setup page has the tracker url filled in",
                  "{{HTTPS_URL}}" not in body and "https://" in body)
        async with s.get(https + "/", ssl=False) as r:
            body = await r.text()
            check("https / is the tracker", r.status == 200 and 'id="cal"' in body)
        async with s.get(http + "/simtrack-ca.crt") as r:
            ca = await r.read()
            check("CA download is a certificate",
                  r.headers["Content-Type"] == "application/x-x509-ca-cert"
                  and ca.startswith(b"-----BEGIN CERTIFICATE-----"))
            check("CA download is an attachment",
                  "simtrack-ca.crt" in r.headers.get("Content-Disposition", ""))

        print("\nSelf-hosted MediaPipe assets")
        for path, want_type in [("/assets/vision_bundle.mjs", "text/javascript"),
                                ("/assets/wasm/vision_wasm_internal.wasm", "application/wasm"),
                                ("/assets/face_landmarker.task", "application/octet-stream"),
                                ("/assets/fonts/ChakraPetch-700i.woff2", "font/woff2")]:
            async with s.get(https + path, ssl=False) as r:
                check(f"GET {path}", r.status == 200 and r.headers["Content-Type"] == want_type,
                      f"{r.status} {r.headers.get('Content-Type')}")
        for path in ["/assets/../server_windows.py", "/assets/%2e%2e/key.pem",
                     "/assets/missing.wasm", "/assets/wasm/../../freetrack.py"]:
            async with s.get(http + path) as r:
                check(f"GET {path} -> 404", r.status == 404, f"got {r.status}")

        print("\nPipeline: phone (wss) -> server -> UDP + shared memory")
        spectator = await s.ws_connect(http + "/ws")            # stands in for the Mac demo
        phone = await s.ws_connect(https + "/ws", ssl=False)     # the real path

        await phone.send_str(json.dumps({"yaw": 12.5, "pitch": -3.25, "roll": 1.5}))
        x, y, z, yaw, pitch, roll = await recv_udp(udp, loop)
        check("yaw/pitch/roll intact over wss", (yaw, pitch, roll) == (12.5, -3.25, 1.5),
              f"got {(yaw, pitch, roll)}")
        msg = await asyncio.wait_for(spectator.receive(), 2)
        check("relayed to other clients", json.loads(msg.data)["yaw"] == 12.5)
        ft = sw.freetrack.read_back()
        check("FreeTrack buffer written (yaw inverted by protocol)",
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
                vals = (await recv_udp(udp, loop, 0.5))[3:]
            except asyncio.TimeoutError:
                break
            seen.append(vals)
            got = vals
            if vals == (1.0, 2.0, 3.0):
                break
        check("stream alive after garbage", got == (1.0, 2.0, 3.0), f"last {got}")
        finite = all(v == v and abs(v) != float("inf") for vs in seen for v in vs)
        check("no non-finite values reached UDP", finite, f"saw {seen}")

        print("\nPhone disconnects: view recentres instead of freezing")
        await phone.close()
        await spectator.close()
        zeroed = False
        deadline = loop.time() + 2
        while loop.time() < deadline:
            try:
                vals = (await recv_udp(udp, loop, 0.5))[3:]
            except asyncio.TimeoutError:
                break
            if vals == (0.0, 0.0, 0.0):
                zeroed = True
                break
        check("zero pose sent on last disconnect", zeroed)
        check("shared memory recentred", abs(sw.freetrack.read_back()["Yaw"]) < 0.01)

    await runner.cleanup()
    udp.close()

    print()
    if fails:
        print(f"{len(fails)} FAILED: {', '.join(fails)}")
        return 1
    print("All end-to-end checks passed.")
    return 0


with tempfile.TemporaryDirectory() as _tmp:
    sys.exit(asyncio.run(main(_tmp)))
