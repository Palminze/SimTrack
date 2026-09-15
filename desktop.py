#!/usr/bin/env python3
"""
Desktop window: desktop.html rendered by the OS web view (Edge WebView2 on
Windows), which is what lets the helmet be a real WebGL model instead of
flat polygons. The page polls a small Python API for state at 30fps.

run() returns False for every way this can fail -- pywebview missing, no
WebView2 runtime, a window that never appears -- so the caller falls back to
the classic tkinter window. Returning True when no window was ever shown is
the dangerous case: the caller skips the fallback, main() ends, and the
daemon server thread dies with it, leaving the user a process that exited
silently. So a window that was never shown counts as failure.
"""

from __future__ import annotations

import os
import time


def run(state_fn, qr_fn, base_dir: str, title: str = "SimTrack") -> bool:
    try:
        import webview                                   # pywebview
    except Exception as exc:                             # noqa: BLE001
        print(f"[desktop] web view unavailable ({exc}); using classic window")
        return False

    class Api:
        def state(self):
            return state_fn()

        def qr(self):
            return qr_fn()

    page = os.path.join(base_dir, "desktop.html")
    shown = {"ok": False}

    try:
        window = webview.create_window(title, url=page, js_api=Api(),
                                       width=640, height=880, min_size=(560, 720),
                                       background_color="#111315")
    except Exception as exc:                             # noqa: BLE001
        print(f"[desktop] could not create window ({exc}); using classic window")
        return False

    # Push the QR and first state in as soon as the document loads, rather
    # than waiting for the page to call back through the js_api bridge. If
    # that bridge fails to attach, the window would otherwise sit there with
    # a blank QR square and no address -- the user's only way in, gone.
    def _bootstrap():
        try:
            import json
            payload = json.dumps({"state": state_fn(), "qr": qr_fn()})
            window.evaluate_js(f"window.applyBoot && window.applyBoot({payload})")
        except Exception as exc:                         # noqa: BLE001
            print(f"[desktop] could not push initial state ({exc})")

    try:
        window.events.loaded += _bootstrap
    except Exception:                                    # noqa: BLE001
        pass

    # Prefer the real signal; fall back to timing if this pywebview build
    # does not expose the event.
    observed = True
    try:
        window.events.shown += lambda: shown.__setitem__("ok", True)
    except Exception:                                    # noqa: BLE001
        observed = False

    started = time.time()
    try:
        webview.start()
    except Exception as exc:                             # noqa: BLE001
        print(f"[desktop] web view failed ({exc}); using classic window")
        return False

    if observed and not shown["ok"]:
        print("[desktop] window never appeared; using classic window")
        return False
    if not observed and time.time() - started < 1.5:
        print("[desktop] web view closed immediately; using classic window")
        return False
    return True
