#!/usr/bin/env python3
"""Certificate authority checks. Run anywhere: python3 tools/test_certs.py

Guards the constraints iOS enforces before trusting a leaf certificate --
a wrong one here means a phone that silently refuses the https link.
"""

import datetime as dt
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cryptography import x509                               # noqa: E402
from cryptography.x509.oid import ExtendedKeyUsageOID       # noqa: E402

import certs                                                # noqa: E402

fails = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{('  ' + detail) if detail else ''}")
    if not ok:
        fails.append(label)


def load(path):
    with open(path, "rb") as fh:
        return x509.load_pem_x509_certificate(fh.read())


with tempfile.TemporaryDirectory() as d:
    print("First run: CA + leaf issued")
    p = certs.ensure_certs("192.168.1.42", d)
    ca, leaf = load(p["ca"]), load(p["cert"])
    check("CA is a CA", ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca)
    check("leaf signed by CA", leaf.issuer == ca.subject)
    san = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    ips = {str(i) for i in san.get_values_for_type(x509.IPAddress)}
    check("SAN carries LAN ip + loopback", ips == {"192.168.1.42", "127.0.0.1"}, str(ips))
    eku = leaf.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    check("EKU serverAuth", ExtendedKeyUsageOID.SERVER_AUTH in eku)
    days = (leaf.not_valid_after_utc - leaf.not_valid_before_utc).days
    check("validity within Apple's 825-day cap", days <= 825, f"{days} days")
    check("RSA 2048", leaf.public_key().key_size == 2048)
    check("SHA-256", leaf.signature_hash_algorithm.name == "sha256")

    print("\nSecond run: reused, not reissued")
    before = os.path.getmtime(p["cert"])
    p2 = certs.ensure_certs("192.168.1.42", d)
    check("same leaf file", os.path.getmtime(p2["cert"]) == before)
    check("same CA", load(p2["ca"]).serial_number == ca.serial_number)

    print("\nLAN address changed: leaf reissued under the same CA")
    p3 = certs.ensure_certs("10.0.0.7", d)
    leaf3 = load(p3["cert"])
    ips3 = {str(i) for i in leaf3.extensions.get_extension_for_class(
        x509.SubjectAlternativeName).value.get_values_for_type(x509.IPAddress)}
    check("new ip in SAN", "10.0.0.7" in ips3, str(ips3))
    check("CA unchanged", load(p3["ca"]).serial_number == ca.serial_number)
    check("phone trust survives (same issuer)", leaf3.issuer == ca.subject)

    print("\nTLS context loads the pair")
    try:
        certs.ssl_context(p3["cert"], p3["key"])
        check("ssl_context", True)
    except Exception as exc:                                  # noqa: BLE001
        check("ssl_context", False, str(exc))

print()
if fails:
    print(f"{len(fails)} FAILED: {', '.join(fails)}")
    sys.exit(1)
print("All certificate checks passed.")
