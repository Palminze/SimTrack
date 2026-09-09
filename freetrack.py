#!/usr/bin/env python3
"""
FreeTrack 2.0 shared-memory interface.

Games that support FreeTrack (Assetto Corsa, ETS2, ATS, BeamNG, ...) read head
pose from a named shared-memory block. The layout below is the FreeTrack 2.0
public interface and must match byte for byte -- a wrong field order does not
error, it just feeds the game garbage.

    typedef struct FTData {
        int32_t DataID;                       // frame counter
        int32_t CamWidth, CamHeight;
        float   Yaw, Pitch, Roll, X, Y, Z;    // virtual pose (radians / mm)
        float   RawYaw, RawPitch, RawRoll;    // unfiltered pose
        float   RawX, RawY, RawZ;
        float   X1, Y1, X2, Y2, X3, Y3, X4, Y4;   // marker points (unused)
    } FTData;                                  // 92 bytes

    typedef struct FTHeap {
        FTData  data;
        int32_t GameID;
        uint8_t table[8];
        int32_t GameID2;
    } FTHeap;                                  // 108 bytes

Two details that are easy to get wrong:
  * Angles are RADIANS, not degrees.
  * Translations are MILLIMETRES.
"""

from __future__ import annotations

import math
import struct
import sys
import threading
import time

FT_DATA   = struct.Struct("<3i20f")        # 92 bytes
FT_HEAP   = struct.Struct("<3i20f i 8s i")  # 108 bytes

HEAP_NAME  = "FT_SharedMem"
MUTEX_NAME = "FT_Mutext"   # sic -- the original FreeTrack typo, kept for compatibility

CAM_WIDTH  = 640
CAM_HEIGHT = 480

_D2R = math.pi / 180.0


class FreeTrack:
    """Writes head pose into the FreeTrack 2.0 shared-memory block.

    On non-Windows platforms it falls back to an in-process buffer so the
    packing logic stays testable off the target machine.
    """

    def __init__(self, invert_yaw: bool = True, invert_pitch: bool = True,
                 invert_roll: bool = False) -> None:
        self.frame = 0
        self.active = False
        self.error: str | None = None
        self.invert_yaw = invert_yaw
        self.invert_pitch = invert_pitch
        self.invert_roll = invert_roll
        self._mutex = None
        self._buf = bytearray(FT_HEAP.size)   # test fallback
        self.mm = None
        self.current_game: str | None = None

        if sys.platform != "win32":
            self.error = "not on Windows -- shared memory disabled"
            return

        import mmap
        try:
            self.mm = mmap.mmap(-1, FT_HEAP.size, HEAP_NAME)
            self.active = True
        except Exception as exc:                      # noqa: BLE001
            self.error = f"could not map {HEAP_NAME}: {exc}"
            return

        # A mutex guards the block against torn reads. Games tolerate its
        # absence, but opentrack creates it and so do we.
        try:
            import ctypes
            self._mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
        except Exception:                             # noqa: BLE001
            self._mutex = None

    # ── pose ────────────────────────────────────────────────────────────────
    def pack(self, yaw_deg: float, pitch_deg: float, roll_deg: float,
             x_mm: float = 0.0, y_mm: float = 0.0, z_mm: float = 0.0) -> bytes:
        """Build one FTHeap frame. Angles in, degrees; angles out, radians."""
        yaw   = (-yaw_deg   if self.invert_yaw   else yaw_deg)   * _D2R
        pitch = (-pitch_deg if self.invert_pitch else pitch_deg) * _D2R
        roll  = (-roll_deg  if self.invert_roll  else roll_deg)  * _D2R

        self.frame = (self.frame + 1) & 0x7FFFFFFF
        return FT_HEAP.pack(
            self.frame, CAM_WIDTH, CAM_HEIGHT,
            yaw, pitch, roll, x_mm, y_mm, z_mm,          # virtual pose
            yaw, pitch, roll, x_mm, y_mm, z_mm,          # raw pose (same source)
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,      # marker points
            0, b"\x00" * 8, 0,                            # GameID, table, GameID2
        )

    def write(self, yaw_deg: float, pitch_deg: float, roll_deg: float,
              x_mm: float = 0.0, y_mm: float = 0.0, z_mm: float = 0.0) -> None:
        # Write ONLY the FTData block (first 92 bytes). The heap tail past it
        # (GameID/table/GameID2) belongs to the game handshake -- writing the
        # full frame here would zero the game's announcement on every pose.
        frame = self.pack(yaw_deg, pitch_deg, roll_deg, x_mm, y_mm, z_mm)[:FT_DATA.size]
        if not self.active:
            self._buf[:FT_DATA.size] = frame
            return

        if self._mutex:
            import ctypes
            ctypes.windll.kernel32.WaitForSingleObject(self._mutex, 16)
        try:
            self.mm.seek(0)
            self.mm.write(frame)
        finally:
            if self._mutex:
                import ctypes
                ctypes.windll.kernel32.ReleaseMutex(self._mutex)

    # ── game handshake ──────────────────────────────────────────────────────
    # A TrackIR/FreeTrack game announces itself by writing its ID into the
    # heap; the tracker answers with the game's scramble table and echoes the
    # ID into GameID2. Until that answer arrives, NPClient reports no data.
    def _read_tail(self) -> "tuple[int, bytes, int]":
        if self.active:
            self.mm.seek(_GAMEID_OFF)
            raw = self.mm.read(_TAIL.size)
        else:
            raw = bytes(self._buf[_GAMEID_OFF:_GAMEID_OFF + _TAIL.size])
        gid, table, gid2 = _TAIL.unpack(raw)
        return gid, table, gid2

    def _write_tail(self, gid: int, table: bytes, gid2: int) -> None:
        raw = _TAIL.pack(gid, table, gid2)
        if self.active:
            self.mm.seek(_GAMEID_OFF)
            self.mm.write(raw)
        else:
            self._buf[_GAMEID_OFF:_GAMEID_OFF + _TAIL.size] = raw

    def poll_game(self, csv_path: str) -> "str | None":
        """One handshake step; returns the game name when a new game appears."""
        gid, _table, gid2 = self._read_tail()
        if gid == 0 or gid == gid2:
            return None
        name, table = lookup_game(csv_path, gid)
        self._write_tail(gid, table, gid)
        self.current_game = name
        return name

    def start_game_watch(self, csv_path: str, on_game=None) -> None:
        def run():
            while True:
                try:
                    name = self.poll_game(csv_path)
                    if name and on_game:
                        on_game(name)
                except Exception:                     # noqa: BLE001
                    pass
                time.sleep(0.5)
        threading.Thread(target=run, daemon=True).start()

    # ── introspection ───────────────────────────────────────────────────────
    def read_back(self) -> dict:
        """Decode whatever is currently in the block. For the checker tool."""
        if self.active:
            self.mm.seek(0)
            raw = self.mm.read(FT_HEAP.size)
        else:
            raw = bytes(self._buf)
        return decode(raw)


def decode(raw: bytes) -> dict:
    f = FT_HEAP.unpack(raw)
    r2d = 180.0 / math.pi
    return {
        "DataID": f[0], "CamWidth": f[1], "CamHeight": f[2],
        "Yaw": f[3] * r2d, "Pitch": f[4] * r2d, "Roll": f[5] * r2d,
        "X": f[6], "Y": f[7], "Z": f[8],
        "GameID": f[23], "GameID2": f[25],
    }


# Offsets of the handshake tail inside FTHeap: GameID right after FTData,
# then the 8-byte scramble table, then GameID2 (the tracker's acknowledgement).
_GAMEID_OFF = FT_DATA.size          # 92
_TAIL       = struct.Struct("<i8si")


def lookup_game(csv_path: str, game_id: int):
    """Map a game's reported ID to (name, 8-byte table) via games.csv.

    Games listed as protocol version V160 (and any row without a full 22-hex
    FTN id) use a zero table -- their data is not scrambled. Unknown IDs get
    a zero table too, which works for every unscrambled title.
    """
    zero = bytes(8)
    want = str(game_id)
    try:
        with open(csv_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                cols = line.rstrip("\n\r").split(";")
                if len(cols) == 8 and cols[6].strip() == want:
                    name, since, ftn = cols[1], cols[3].strip(), cols[7].strip()
                    if since != "V160" and len(ftn) == 22:
                        return name, bytes.fromhex(ftn)[:8]
                    return name, zero
    except OSError:
        pass
    return f"game id {game_id}", zero


def register_client_dll(dll_dir: str) -> str | None:
    """Point FreeTrack-aware games at FreeTrackClient.dll.

    Most games do not read the shared memory directly -- they load
    FreeTrackClient.dll and find it through this registry key. Without it,
    writing shared memory alone does nothing. Returns an error string on
    failure, None on success.
    """
    if sys.platform != "win32":
        return "not on Windows"
    try:
        import winreg
        key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,
                                 r"Software\FreeTrack\FreeTrackClient", 0,
                                 winreg.KEY_SET_VALUE)
        with key:
            winreg.SetValueEx(key, "Path", 0, winreg.REG_SZ, dll_dir)
        return None
    except Exception as exc:                          # noqa: BLE001
        return str(exc)


def register_npclient(dll_dir: str) -> str | None:
    """Point TrackIR games at NPClient.dll / NPClient64.dll.

    TrackIR titles (Assetto Corsa, iRacing, ...) find the client DLL through
    this key; with it set they load SimTrack's NPClient directly -- no
    TrackIR software, no opentrack process.
    """
    if sys.platform != "win32":
        return "not on Windows"
    try:
        import winreg
        key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,
                                 r"Software\NaturalPoint\NATURALPOINT\NPClient Location",
                                 0, winreg.KEY_SET_VALUE)
        with key:
            winreg.SetValueEx(key, "Path", 0, winreg.REG_SZ, dll_dir)
        return None
    except Exception as exc:                          # noqa: BLE001
        return str(exc)
