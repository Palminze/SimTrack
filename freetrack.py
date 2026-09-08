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
        frame = self.pack(yaw_deg, pitch_deg, roll_deg, x_mm, y_mm, z_mm)
        if not self.active:
            self._buf[:] = frame
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
