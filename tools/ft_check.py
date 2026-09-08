#!/usr/bin/env python3
"""
FreeTrack diagnostics. Run on the Windows gaming PC.

  python tools/ft_check.py emit     sweep the head slowly side to side, so you can
                                    confirm the game reacts with no phone involved
  python tools/ft_check.py watch    decode whatever SimTrack is writing right now

'emit' is the fast way to prove the game link: start it, launch Assetto Corsa
with FreeTrack head tracking enabled, and the in-game view should pan.
If it does, the game side works and any remaining problem is phone-to-PC.
"""

import argparse
import math
import os
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
r = sub.add_parser("register", help="set the FreeTrackClient.dll registry path")
r.add_argument("dir", help="directory containing FreeTrackClient.dll")
r.set_defaults(fn=register)

args = p.parse_args()
sys.exit(args.fn(args))
