#!/usr/bin/env python3
"""
Cloudflare quick tunnel.

Phone browsers only expose the camera on secure origins, so the LAN address
(http://192.168.x.x:8080) can never start tracking no matter what permissions
the user grants. Until SimTrack ships real certificates, a tunnel is the only
way to hand the phone an https:// URL.

start.bat downloaded cloudflared but nothing ever launched it, so on Windows
the tunnel simply never existed.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import urllib.request

CLOUDFLARED_URL = ("https://github.com/cloudflare/cloudflared/releases/latest/"
                   "download/cloudflared-windows-amd64.exe")
URL_RE = re.compile(rb"https://[a-z0-9-]+\.trycloudflare\.com")

HERE = os.path.dirname(os.path.abspath(__file__))


def _exe_path() -> str:
    name = "cloudflared.exe" if sys.platform == "win32" else "cloudflared"
    return os.path.join(HERE, name)


def ensure_cloudflared(log=print) -> str | None:
    """Return a path to cloudflared, downloading it on Windows if needed."""
    path = _exe_path()
    if os.path.exists(path):
        return path

    if sys.platform != "win32":
        for candidate in ("/usr/local/bin/cloudflared", "/opt/homebrew/bin/cloudflared",
                          "/tmp/cloudflared"):
            if os.path.exists(candidate):
                return candidate
        log("[tunnel] cloudflared not found — install it with: brew install cloudflared")
        return None

    log("[tunnel] downloading cloudflared…")
    try:
        urllib.request.urlretrieve(CLOUDFLARED_URL, path)
        log("[tunnel] downloaded")
        return path
    except Exception as exc:                          # noqa: BLE001
        log(f"[tunnel] download failed: {exc}")
        return None


class Tunnel:
    """Runs `cloudflared tunnel --url` and reports the public https URL.

    cloudflared prints its banner to stderr, so that is where the URL appears.
    """

    def __init__(self, port: int, on_url=None, on_error=None, log=print):
        self.port = port
        self.url: str | None = None
        self.error: str | None = None
        self._on_url = on_url
        self._on_error = on_error
        self._log = log
        self._proc = None

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def _fail(self, msg: str) -> None:
        self.error = msg
        self._log(f"[tunnel] {msg}")
        if self._on_error:
            self._on_error(msg)

    def _run(self) -> None:
        exe = ensure_cloudflared(self._log)
        if not exe:
            self._fail("cloudflared unavailable — phone cannot get an HTTPS URL")
            return

        cmd = [exe, "tunnel", "--url", f"http://localhost:{self.port}",
               "--no-autoupdate"]
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                creationflags=flags)
        except Exception as exc:                      # noqa: BLE001
            self._fail(f"could not launch cloudflared: {exc}")
            return

        self._log("[tunnel] starting…")
        for line in self._proc.stderr:
            match = URL_RE.search(line)
            if match and not self.url:
                self.url = match.group(0).decode()
                self._log(f"[tunnel] {self.url}")
                if self._on_url:
                    self._on_url(self.url)

        code = self._proc.wait()
        if not self.url:
            self._fail(f"cloudflared exited ({code}) without publishing a URL")

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
