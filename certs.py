#!/usr/bin/env python3
"""
SimTrack's own certificate authority.

Phone browsers only expose the camera on https:// origins, and no public CA
will issue a certificate for a private LAN address. So SimTrack issues its
own: a local CA is created once per PC, the phone trusts it once, and from
then on https://<lan-ip>:8443 is a fully trusted origin -- no tunnel, no
third party, no URL that changes.

Constraints baked in here are Apple's rules for a leaf cert to be trusted on
iOS: RSA >= 2048, SHA-256, a SubjectAlternativeName (CN alone is ignored),
ExtendedKeyUsage serverAuth, and validity of at most 825 days.
"""

from __future__ import annotations

import datetime as dt
import ipaddress
import os
import ssl
import sys

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

CA_NAME   = "SimTrack Local CA"
CA_DAYS   = 3650
LEAF_DAYS = 800        # under Apple's 825-day cap, with margin
RENEW_IF_LESS_THAN = dt.timedelta(days=30)


def user_dir() -> str:
    """Per-user writable folder for the CA and server certificate."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "SimTrack")
    else:
        d = os.path.join(os.path.expanduser("~"), ".simtrack")
    os.makedirs(d, exist_ok=True)
    return d


# ── helpers ─────────────────────────────────────────────────────────────────
def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _new_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _write_key(path: str, key: rsa.RSAPrivateKey) -> None:
    with open(path, "wb") as fh:
        fh.write(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption()))
    if sys.platform != "win32":
        os.chmod(path, 0o600)


def _write_cert(path: str, cert: x509.Certificate) -> None:
    with open(path, "wb") as fh:
        fh.write(cert.public_bytes(serialization.Encoding.PEM))


def _load_cert(path: str) -> x509.Certificate:
    with open(path, "rb") as fh:
        return x509.load_pem_x509_certificate(fh.read())


def _load_key(path: str):
    with open(path, "rb") as fh:
        return serialization.load_pem_private_key(fh.read(), password=None)


# ── CA ──────────────────────────────────────────────────────────────────────
def ensure_ca(d: str):
    """Load the local CA, creating it on first run. Returns (cert, key)."""
    crt, key_path = os.path.join(d, "simtrack-ca.crt"), os.path.join(d, "simtrack-ca.key")
    if os.path.exists(crt) and os.path.exists(key_path):
        return _load_cert(crt), _load_key(key_path)

    key = _new_key()
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, CA_NAME),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SimTrack"),
    ])
    now = _now()
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=CA_DAYS))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(
                digital_signature=False, content_commitment=False,
                key_encipherment=False, data_encipherment=False,
                key_agreement=False, key_cert_sign=True, crl_sign=True,
                encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
                           critical=False)
            .sign(key, hashes.SHA256()))
    _write_key(key_path, key)
    _write_cert(crt, cert)
    return cert, key


# ── server certificate ──────────────────────────────────────────────────────
def _leaf_covers(cert: x509.Certificate, ips: set[str]) -> bool:
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return False
    have = {str(ip) for ip in san.get_values_for_type(x509.IPAddress)}
    fresh = cert.not_valid_after_utc - _now() > RENEW_IF_LESS_THAN
    return ips <= have and fresh


def ensure_server_cert(d: str, ips: set[str]):
    """Issue (or reuse) a leaf cert for these IPs, signed by the local CA.

    Reissued automatically when the PC's LAN address changes or the cert is
    within 30 days of expiry. Returns (cert_path, key_path).
    """
    ca_cert, ca_key = ensure_ca(d)
    crt, key_path = os.path.join(d, "server.crt"), os.path.join(d, "server.key")
    if os.path.exists(crt) and os.path.exists(key_path):
        if _leaf_covers(_load_cert(crt), ips):
            return crt, key_path

    key = _new_key()
    now = _now()
    san = x509.SubjectAlternativeName(
        [x509.IPAddress(ipaddress.ip_address(ip)) for ip in sorted(ips)]
        + [x509.DNSName("localhost")])
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SimTrack")]))
            .issuer_name(ca_cert.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=LEAF_DAYS))
            .add_extension(san, critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(
                digital_signature=True, content_commitment=False,
                key_encipherment=True, data_encipherment=False,
                key_agreement=False, key_cert_sign=False, crl_sign=False,
                encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
                           critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(
                ca_cert.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256()))
    _write_key(key_path, key)
    _write_cert(crt, cert)
    return crt, key_path


def ensure_certs(lan_ip: str, d: str | None = None) -> dict:
    """One call from the server: returns paths for cert, key and the CA cert."""
    d = d or user_dir()
    ips = {lan_ip, "127.0.0.1"} if lan_ip != "localhost" else {"127.0.0.1"}
    cert, key = ensure_server_cert(d, ips)
    return {"cert": cert, "key": key, "ca": os.path.join(d, "simtrack-ca.crt")}


def ssl_context(cert_path: str, key_path: str) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(cert_path, key_path)
    return ctx
