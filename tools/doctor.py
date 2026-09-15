#!/usr/bin/env python3
"""
SimTrack doctor -- answers "why can't my phone reach the PC?" in one run.

    python tools\\doctor.py          diagnose
    python tools\\doctor.py --fix    diagnose, then add the firewall rule
                                     (needs an administrator PowerShell)

Checks the whole path the phone takes, in the order it takes it, and stops
guessing: the LAN address, whether SimTrack is listening, whether the PC can
fetch its own pages, whether Windows Firewall would let another device in,
and whether the certificate matches the current address.
"""

from __future__ import annotations

import argparse
import os
import socket
import ssl
import subprocess
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HTTP_PORT, HTTPS_PORT = 8080, 8443
problems: list[str] = []


def say(ok, label, detail=""):
    mark = "OK  " if ok else "FAIL"
    print(f"  [{mark}] {label}" + (f"  — {detail}" if detail else ""))


def lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:                                     # noqa: BLE001
        return "localhost"


def listening(port: int) -> bool:
    """A bind that fails means something already holds the port -- good."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("0.0.0.0", port))
        return False
    except OSError:
        return True
    finally:
        s.close()


def fetch(url: str, insecure=False) -> tuple[bool, str]:
    ctx = ssl._create_unverified_context() if insecure else None
    try:
        with urllib.request.urlopen(url, timeout=4, context=ctx) as r:
            return r.status == 200, f"HTTP {r.status}"
    except Exception as exc:                              # noqa: BLE001
        return False, type(exc).__name__ + f": {exc}"


def ps(cmd: str) -> str:
    try:
        return subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                              capture_output=True, text=True, timeout=25).stdout.strip()
    except Exception:                                     # noqa: BLE001
        return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true", help="add the firewall rule")
    args = ap.parse_args()
    win = sys.platform == "win32"

    ip = lan_ip()
    print(f"\nSimTrack doctor\n  this PC: {ip}\n")

    print("1. Is SimTrack running?")
    up_http, up_https = listening(HTTP_PORT), listening(HTTPS_PORT)
    say(up_http, f"port {HTTP_PORT} (setup page)")
    say(up_https, f"port {HTTPS_PORT} (tracker)")
    if not (up_http and up_https):
        problems.append(
            "SimTrack is not listening. Start it (start.bat) and leave the window "
            "open, then run this again. If its window never appears, run "
            "`start.bat --classic`.")
        print("\n" + verdict())
        return 1

    print("\n2. Can this PC reach its own pages?")
    for label, url, insecure in (("setup over localhost", f"http://127.0.0.1:{HTTP_PORT}/", False),
                                 ("setup over the LAN address", f"http://{ip}:{HTTP_PORT}/", False),
                                 ("tracker over the LAN address", f"https://{ip}:{HTTPS_PORT}/", True)):
        ok, detail = fetch(url, insecure)
        say(ok, label, "" if ok else detail)
        if not ok:
            problems.append(f"The PC cannot load {url} itself — that is a SimTrack "
                            f"problem, not a network one. Check its window for an error.")

    if win:
        print("\n3. Would Windows Firewall let the phone in?")
        prof = ps("(Get-NetFirewallProfile -Name Private).Enabled")
        rules = ps("Get-NetFirewallRule -Direction Inbound -Enabled True -Action Allow "
                   "-ErrorAction SilentlyContinue | Get-NetFirewallPortFilter "
                   f"-ErrorAction SilentlyContinue | Where-Object {{ $_.LocalPort -eq '{HTTP_PORT}' "
                   f"-or $_.LocalPort -eq '{HTTPS_PORT}' }} | Measure-Object | "
                   "Select-Object -ExpandProperty Count")
        py_rule = ps("Get-NetFirewallApplicationFilter -ErrorAction SilentlyContinue | "
                     "Where-Object { $_.Program -like '*python*' -or $_.Program -like '*SimTrack*' } | "
                     "Measure-Object | Select-Object -ExpandProperty Count")
        on = prof.strip().lower() in ("true", "1")
        say(True, "Private profile firewall", "on" if on else "off")
        have_port = rules.isdigit() and int(rules) > 0
        have_app = py_rule.isdigit() and int(py_rule) > 0
        say(have_port or have_app or not on, "an inbound rule covers SimTrack",
            f"port rules: {rules or '0'}, app rules: {py_rule or '0'}")
        if on and not (have_port or have_app):
            problems.append(
                "Windows Firewall has no rule for SimTrack, so other devices are "
                "blocked. Fix: open PowerShell as administrator and run\n"
                f"    New-NetFirewallRule -DisplayName \"SimTrack\" -Direction Inbound "
                f"-Protocol TCP -LocalPort {HTTP_PORT},{HTTPS_PORT} -Action Allow -Profile Private\n"
                "  (or re-run this with --fix from an administrator PowerShell)")

        if args.fix:
            print("\n   adding the firewall rule…")
            out = ps("New-NetFirewallRule -DisplayName 'SimTrack' -Direction Inbound "
                     f"-Protocol TCP -LocalPort {HTTP_PORT},{HTTPS_PORT} -Action Allow "
                     "-Profile Private,Domain -ErrorAction SilentlyContinue | "
                     "Select-Object -ExpandProperty DisplayName")
            say(bool(out), "rule added",
                "" if out else "needs an administrator PowerShell (right-click → Run as administrator)")

        print("\n4. Is the network one the phone can share?")
        cat = ps("(Get-NetConnectionProfile | Select-Object -First 1).NetworkCategory")
        say(cat.strip().lower() != "public", "network is Private, not Public", cat or "unknown")
        if cat.strip().lower() == "public":
            problems.append(
                "This network is set to Public, which blocks other devices even with "
                "a firewall rule. Settings → Network & Internet → WiFi → your network "
                "→ set network profile to Private.")

    print("\n5. Certificate")
    try:
        import certs
        d = certs.user_dir()
        have = os.path.exists(os.path.join(d, "server.crt"))
        say(have, "issued for this address", d)
        if not have:
            problems.append("No certificate yet — start SimTrack once, it makes its own.")
    except Exception as exc:                              # noqa: BLE001
        say(False, "certificate check", str(exc))

    print(f"\n  Phone should open:  http://{ip}:{HTTP_PORT}/")
    print("\n" + verdict())
    return 1 if problems else 0


def verdict() -> str:
    if not problems:
        return ("VERDICT: the PC side is healthy.\n"
                "  If the phone still cannot load the page, it is not on the same "
                "network:\n"
                "   • check the WiFi name on the phone matches this PC's\n"
                "   • turn mobile data off on the phone and retry\n"
                "   • guest networks and 'AP isolation' block devices from seeing "
                "each other — use the main network")
    out = ["VERDICT: " + ("1 problem found" if len(problems) == 1
                          else f"{len(problems)} problems found")]
    for i, p in enumerate(problems, 1):
        out.append(f"\n  {i}. {p}")
    return "\n".join(out)


if __name__ == "__main__":
    sys.exit(main())
