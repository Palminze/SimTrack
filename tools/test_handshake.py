#!/usr/bin/env python3
"""Game-ID handshake tests: CSV lookup and the GameID/GameID2 echo. Any OS."""

import os
import struct
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from freetrack import FreeTrack, lookup_game, _GAMEID_OFF, _TAIL  # noqa: E402

CSV = os.path.join(ROOT, "dll", "games.csv")
fails = []


def check(label, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}: got {got!r}, want {want!r}")
    if not ok:
        fails.append(label)


print("CSV lookups against the real games.csv")
name, table = lookup_game(CSV, 14101)
check("iRacing name", name, "iRacing")
check("iRacing table is zero (unscrambled)", table, bytes(8))
name, table = lookup_game(CSV, 8140)
check("ACC name", name, "Assetto Corsa Competizione")
name, table = lookup_game(CSV, 999999)
check("unknown id still answered", name, "game id 999999")

print("\nScrambled-title decode (synthetic row, non-V160 + 22-hex FTN id)")
with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as fh:
    fh.write("No;Game Name;Game protocol;Supported since;Verified;By;INTERNATIONAL_ID;FTN_ID\n")
    fh.write("1;Fake Scrambled Game;FreeTrack20;V170;V;test;12345;0102030405060708090A0B\n")
    tmp = fh.name
name, table = lookup_game(tmp, 12345)
os.unlink(tmp)
check("scrambled name", name, "Fake Scrambled Game")
check("table = first 8 FTN bytes", table, bytes([1, 2, 3, 4, 5, 6, 7, 8]))

print("\nHandshake against the in-process buffer")
ft = FreeTrack()
check("no game yet", ft.poll_game(CSV), None)

# The game announces itself by writing its ID into the heap.
struct.pack_into("<i", ft._buf, _GAMEID_OFF, 14101)
check("new game detected", ft.poll_game(CSV), "iRacing")
gid, table, gid2 = _TAIL.unpack(bytes(ft._buf[_GAMEID_OFF:_GAMEID_OFF + _TAIL.size]))
check("GameID preserved", gid, 14101)
check("GameID2 echoed", gid2, 14101)
check("zero table written", table, bytes(8))
check("current_game exposed", ft.current_game, "iRacing")
check("second poll is idle (already acked)", ft.poll_game(CSV), None)

# Pose writes must not clobber the handshake tail.
ft.write(10.0, 5.0, 1.0)
gid, table, gid2 = _TAIL.unpack(bytes(ft._buf[_GAMEID_OFF:_GAMEID_OFF + _TAIL.size]))
check("GameID survives pose writes", gid, 14101)
check("GameID2 survives pose writes", gid2, 14101)

print()
if fails:
    print(f"{len(fails)} FAILED: {', '.join(fails)}")
    sys.exit(1)
print("All handshake checks passed.")
