#!/usr/bin/env python3
"""Window-state checks. Run anywhere: python3 tools/test_state.py

The desktop page draws only what app_state()/qr_matrix() return, so their
shape is the contract; and the web-view host must fall back cleanly when it
cannot run, or a customer gets no window at all.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import desktop           # noqa: E402
import server_windows as sw  # noqa: E402

fails = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{('  ' + detail) if detail else ''}")
    if not ok:
        fails.append(label)


print("app_state()")
s = sw.app_state()
need = {"status", "level", "pose", "clients", "game", "setup_url", "tracker_url",
        "lan_ip", "opentrack_port", "missing_dlls"}
check("has every key the page reads", need <= set(s), f"missing {need - set(s)}")
check("level is one the page styles", s["level"] in {"ok", "warn", "idle", "error"}, s["level"])
check("pose is three numbers", len(s["pose"]) == 3 and all(isinstance(v, float) for v in s["pose"]))
check("JSON-serialisable (crosses the bridge)", json.dumps(s) is not None)
check("urls carry the ports", ":8080/" in s["setup_url"] and ":8443/" in s["tracker_url"],
      f"{s['setup_url']} {s['tracker_url']}")

print("\nPose flows into state")
sw.LAST["pose"] = (12.5, -3.25, 1.5)
check("latest pose reported", sw.app_state()["pose"] == [12.5, -3.25, 1.5])
sw.LAST["pose"] = (0.0, 0.0, 0.0)

print("\nqr_matrix()")
m = sw.qr_matrix()
if sw.LAN_IP == "localhost":
    check("no network → empty matrix, page skips it", m == [])
else:
    check("square matrix", len(m) > 20 and all(len(r) == len(m) for r in m), f"{len(m)}x{len(m[0]) if m else 0}")
    check("cells are 0/1", all(v in (0, 1) for r in m for v in r))
    check("finder pattern present (top-left 7x7 border is dark)",
          all(m[0][i] == 1 and m[6][i] == 1 and m[i][0] == 1 and m[i][6] == 1 for i in range(7)))

print("\nWeb view fallback")
try:
    import webview  # noqa: F401
    print("  SKIP  pywebview importable here; not opening a window in a test")
except Exception:
    check("run() returns False without pywebview instead of raising",
          desktop.run(sw.app_state, sw.qr_matrix, sw.BASE) is False)

print()
if fails:
    print(f"{len(fails)} FAILED: {', '.join(fails)}")
    sys.exit(1)
print("All state checks passed.")
