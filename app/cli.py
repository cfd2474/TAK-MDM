"""Operational commands.

``python -m app.cli init-pki`` materializes the keys the server and its reverse
proxy need. The app would create the device CA and bundle key lazily on first use,
but nginx has to read the CA certificate *at startup* to verify client
certificates — so in a containerized stack something must create it first.
"""

from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from app.config import get_settings
from app.security.bundle import BundleSigner
from app.security.ca import CertificateAuthority


def _write_dev_server_cert(pki_dir: Path, hostname: str) -> tuple[Path, Path]:
    """A self-signed TLS certificate for the local reverse proxy.

    **Development only.** A real deployment terminates TLS with a certificate from a
    CA browsers and devices already trust; this exists so `docker compose up` yields
    a working mTLS endpoint without external dependencies. It is deliberately kept
    separate from the device CA — that one signs device identities and must not also
    be a web server key.
    """
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])
    now = dt.datetime.now(dt.timezone.utc)

    alt_names: list[x509.GeneralName] = [x509.DNSName(hostname)]
    if hostname != "localhost":
        alt_names.append(x509.DNSName("localhost"))
    alt_names.append(x509.IPAddress(ipaddress.ip_address("127.0.0.1")))

    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    cert_path = pki_dir / "server.crt"
    key_path = pki_dir / "server.key"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    key_path.chmod(0o600)
    return cert_path, key_path


def init_pki(args: argparse.Namespace) -> int:
    settings = get_settings()
    pki_dir = Path(args.pki_dir or settings.pki_dir)
    pki_dir.mkdir(parents=True, exist_ok=True)

    # Both are load-or-create, so this command is idempotent: re-running it never
    # rotates a key out from under enrolled devices.
    CertificateAuthority.load_or_create(
        pki_dir,
        common_name=settings.ca_common_name,
        validity_days=settings.ca_validity_days,
    )
    signer = BundleSigner.load_or_create(pki_dir)

    print(f"device CA:          {pki_dir / 'ca.crt'}")
    print(f"bundle signing key: {pki_dir / 'bundle_signing.key'}")
    print(f"bundle public key:  {signer.public_key_base64()}")

    if args.dev_server_cert:
        server_cert = pki_dir / "server.crt"
        if server_cert.exists():
            print(f"dev TLS cert:       {server_cert} (kept)")
        else:
            cert_path, _ = _write_dev_server_cert(pki_dir, args.hostname)
            print(f"dev TLS cert:       {cert_path} (self-signed, DEVELOPMENT ONLY)")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli", description="TAK MDM operations")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init-pki", help="create the device CA and signing keys")
    init.add_argument("--pki-dir", default=None, help="override the configured PKI directory")
    init.add_argument(
        "--dev-server-cert",
        action="store_true",
        help="also emit a self-signed TLS cert for the local proxy (development only)",
    )
    init.add_argument("--hostname", default="localhost", help="hostname for the dev TLS cert")
    init.set_defaults(func=init_pki)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
