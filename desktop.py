#!/usr/bin/env python3
"""
Desktop window: desktop.html rendered by the OS web view (Edge WebView2 on
Windows), which is what lets the helmet be a real WebGL model instead of
flat polygons. The page polls a small Python API for state at 30fps.

Anything failing here -- pywebview missing, no WebView2 runtime -- returns
False so the caller falls back to the classic tkinter window. The product
must open a window even on a machine we did not anticipate.
"""

from __future__ import annotations

import os


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
    try:
        webview.create_window(title, url=page, js_api=Api(), width=640, height=880,
                              min_size=(560, 720), background_color="#111315")
        webview.start()
    except Exception as exc:                             # noqa: BLE001
        print(f"[desktop] web view failed ({exc}); using classic window")
        return False
    return True
