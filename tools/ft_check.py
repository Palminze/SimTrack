#!/usr/bin/env python3
"""
FreeTrack diagnostics. Run on the Windows gaming PC.

  python tools/ft_check.py emit     sweep into FreeTrack shared memory
                                    (ETS2, ATS, BeamNG)
  python tools/ft_check.py udp      sweep to opentrack over UDP 4242
                                    (Assetto Corsa, ACC, iRacing, Dirt)
  python tools/ft_check.py watch    decode whatever SimTrack is writing right now

Both sweep a synthetic head so the game link can be proven with no phone
involved. If the in-game view pans, the game side works and anything still
broken is phone-to-PC.

Pick by game: Assetto Corsa has no FreeTrack option -- it reads TrackIR, so it
needs the 'udp' route through opentrack. ETS2, ATS and BeamNG read FreeTrack
shared memory directly, so they take 'emit'.
"""

import argparse
import math
import os
import socket
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from freetrack import FreeTrack, register_client_dll  # noqa: E402


def emit(args):
    ft = FreeTrack()
    if not ft.active:
        print(f"[!] FreeTrack inactive: {ft.error}")
        return 1
    print("[ok] FT_SharedMem mapped. Sweeping +/-25 deg yaw, +/-10 deg pitch.")
    print("     Launch the game now. Ctrl+C to stop.\n")
    t0 = time.time()
    try:
        while True:
            t = time.time() - t0
            yaw = 25.0 * math.sin(t * 0.6)
            pitch = 10.0 * math.sin(t * 0.35)
            ft.write(yaw, pitch, 0.0)
            sys.stdout.write(f"\r  yaw {yaw:+6.1f}  pitch {pitch:+6.1f}  frame {ft.frame}   ")
            sys.stdout.flush()
            time.sleep(1 / 60)
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


def udp(args):
    """Sweep over UDP to opentrack. Covers Assetto Corsa, ACC, iRacing, Dirt.

    Opentrack's 'UDP over network' input expects six little-endian doubles:
    x, y, z, yaw, pitch, roll. Translations in cm, angles in degrees.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dest = (args.host, args.port)
    print(f"[ok] Sending sweep to opentrack at {args.host}:{args.port}.")
    print("     In opentrack set Input = 'UDP over network', then press Start.")
    print("     Ctrl+C to stop.\n")
    t0 = time.time()
    try:
        while True:
            t = time.time() - t0
            yaw = 25.0 * math.sin(t * 0.6)
            pitch = 10.0 * math.sin(t * 0.35)
            sock.sendto(struct.pack("<6d", 0.0, 0.0, 0.0, yaw, pitch, 0.0), dest)
            sys.stdout.write(f"\r  yaw {yaw:+6.1f}  pitch {pitch:+6.1f}   ")
            sys.stdout.flush()
            time.sleep(1 / 60)
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


def probe(args):
    """Answer 'is anything actually listening on this port?' without guesswork.

    Binding the WILDCARD address is what makes this reliable. Binding
    127.0.0.1:port can succeed on Windows even while another process holds
    0.0.0.0:port, because those are distinct addresses -- which produces a
    false "nothing is listening". Opentrack binds the wildcard, so we probe
    the wildcard too.
    """
    print(f"Probing UDP {args.host}:{args.port}\n")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listening = False
    try:
        sock.bind(("0.0.0.0", args.port))   # wildcard: see docstring
        sock.close()
        print(f"  [!] Nothing is listening on {args.port}.")
        print("      Opentrack is not bound here, which means tracking is not")
        print("      actually running -- opentrack only opens the port after")
        print("      Start, and only when Input is 'UDP over network'.")
        print("      Cross-check with:  netstat -ano | findstr " + str(args.port))
    except OSError as exc:
        listening = True
        print(f"  [ok] Port {args.port} is held by another process ({exc.errno}).")
        print("       That is opentrack listening. Port is correct.")

    print("\n  Sending 60 test packets...")
    out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sent = 0
    for i in range(60):
        yaw = 25.0 * math.sin(i / 10.0)
        try:
            out.sendto(struct.pack("<6d", 0.0, 0.0, 0.0, yaw, 0.0, 0.0),
                       (args.host, args.port))
            sent += 1
        except OSError as exc:
            print(f"  [!] send failed: {exc}")
            break
        time.sleep(1 / 60)
    out.close()
    print(f"  [ok] {sent}/60 packets sent, 48 bytes each.\n")

    if listening:
        print("  Verdict: packets are reaching opentrack's port. If the octopus")
        print("  still did not move, the mismatch is inside opentrack -- check")
        print("  Input is 'UDP over network' (not a camera tracker) and that")
        print("  the Start button is engaged.")
    else:
        print("  Verdict: wrong port. Nothing was there to receive them.")
    return 0


def watch(args):
    ft = FreeTrack()
    if not ft.active:
        print(f"[!] FreeTrack inactive: {ft.error}")
        return 1
    print("[ok] Reading FT_SharedMem. Ctrl+C to stop.\n")
    last, stale = -1, 0
    try:
        while True:
            d = ft.read_back()
            moving = d["DataID"] != last
            stale = 0 if moving else stale + 1
            last = d["DataID"]
            flag = "live" if stale < 30 else "STALE - nothing is writing"
            sys.stdout.write(
                f"\r  yaw {d['Yaw']:+7.1f}  pitch {d['Pitch']:+7.1f}  "
                f"roll {d['Roll']:+7.1f}  id {d['DataID']:<8} {flag}   ")
            sys.stdout.flush()
            time.sleep(1 / 30)
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


def register(args):
    err = register_client_dll(args.dir)
    if err:
        print(f"[!] {err}")
        return 1
    print(f"[ok] HKCU\\Software\\FreeTrack\\FreeTrackClient\\Path = {args.dir}")
    return 0


p = argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter)
sub = p.add_subparsers(dest="cmd", required=True)
sub.add_parser("emit", help="write a test sweep into shared memory").set_defaults(fn=emit)
sub.add_parser("watch", help="decode the current shared memory").set_defaults(fn=watch)
u = sub.add_parser("udp", help="send a test sweep to opentrack over UDP")
u.add_argument("--host", default="127.0.0.1")
u.add_argument("--port", type=int, default=4242)
u.set_defaults(fn=udp)
pr = sub.add_parser("probe", help="check whether anything is listening on the UDP port")
pr.add_argument("--host", default="127.0.0.1")
pr.add_argument("--port", type=int, default=4242)
pr.set_defaults(fn=probe)
r = sub.add_parser("register", help="set the FreeTrackClient.dll registry path")
r.add_argument("dir", help="directory containing FreeTrackClient.dll")
r.set_defaults(fn=register)

args = p.parse_args()
sys.exit(args.fn(args))
