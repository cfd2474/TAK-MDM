# Copyright 2026 TAK-Solutions LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Operational commands.

``python -m app.cli init-pki`` materializes the keys the server and its reverse
proxy need. The app would create the device CA and bundle key lazily on first use,
but nginx has to read the CA certificate *at startup* to verify client
certificates — so in a containerized stack something must create it first.

``python -m app.cli seed-packages`` loads the applications shipped in ``dist/``
into the library, so a fresh deployment can enrol a device without an operator
uploading the agent by hand first.
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
from app.security import keyfiles


def _write_dev_server_cert(
    pki_dir: Path, hostname: str, extra_sans: list[str] | None = None
) -> tuple[Path, Path]:
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

    # A certificate is only valid for the names it lists. A tablet reaches this
    # server by the PC's LAN address, not "localhost", so that address has to be in
    # here or every connection from the device fails verification.
    alt_names: list[x509.GeneralName] = [x509.DNSName("localhost")]
    alt_names.append(x509.IPAddress(ipaddress.ip_address("127.0.0.1")))

    for name in [hostname, *(extra_sans or [])]:
        if not name or name == "localhost":
            continue
        try:
            alt_names.append(x509.IPAddress(ipaddress.ip_address(name)))
        except ValueError:
            alt_names.append(x509.DNSName(name))

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
    # ⚠️ A sixth private key, found by the guard in `tests/test_key_custody.py`
    # rather than by the audit that went looking for them — SEC_AUDIT S-2 counted
    # five and there are six. The development server certificate is the least
    # dangerous of them (it authenticates a dev listener, not a device or an
    # operator), which is exactly why it was the one missed.
    key_path.unlink(missing_ok=True)
    keyfiles.write_private(
        key_path,
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ),
    )
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
        if server_cert.exists() and not args.force_server_cert:
            print(f"dev TLS cert:       {server_cert} (kept)")
        else:
            # Only the TLS cert is reissued. The device CA is untouched, so
            # already-enrolled devices keep working.
            cert_path, _ = _write_dev_server_cert(pki_dir, args.hostname, args.san)
            names = ", ".join(["localhost", "127.0.0.1", args.hostname, *args.san])
            print(f"dev TLS cert:       {cert_path} (self-signed, DEVELOPMENT ONLY)")
            print(f"  valid for:        {names}")

    return 0


def seed_packages(args: argparse.Namespace) -> int:
    """Ingest the applications bundled with the source. Idempotent, best-effort.

    ⚠️ **A fresh deployment cannot enrol anything until the agent is in here.**
    The provisioning QR carries the signing checksum of the agent APK this server
    serves, so with an empty library there is no checksum to carry and the token
    page refuses outright — which an operator meets several screens away from
    anything that mentions an upload.

    Idempotence rests on ``ingest`` refusing a version code it already holds: a
    restart re-runs this and every build reports "already present". That is also
    why a rebuilt APK needs a *higher* version code to take effect; same code
    means same build, as far as the library is concerned.

    ⚠️ Never fatal. This runs on the startup path, and a deployment that
    refused to boot because a bundled APK could not be read would be far worse
    than one that starts with an empty library and says so.
    """
    from app.api.deps import _artifact_storage
    from app.db.base import SessionLocal
    from app.services import agent_update as agent_update_service
    from app.services import packages as package_service

    settings = get_settings()
    seed_dir = Path(args.directory or "/seed")
    if not seed_dir.is_dir():
        print(f"seed: {seed_dir} is not a directory — nothing to load")
        return 0

    files = sorted(
        p for p in seed_dir.iterdir()
        if p.suffix.lower() in (".apk", ".xapk", ".apks")
    )
    if not files:
        print(f"seed: no applications in {seed_dir}")
        return 0

    storage = _artifact_storage(str(settings.artifact_dir))
    for path in files:
        try:
            with SessionLocal() as session:
                result = package_service.ingest(session, storage, path.read_bytes())
                name = result.package.package_name
                version_name = result.version.version_name
                version_code = result.version.version_code

                # ⚠️ Offering the new agent to the fleet is part of loading it.
                # The agent and the server are one release: an update that put a
                # newer agent in the library and left every device on the old one
                # would be a fleet quietly running a build this server no longer
                # matches. Only on a *new* build — a restart re-runs this and
                # must not overrule an operator who pinned or paused the channel.
                published = False
                if name == settings.agent_package_name:
                    agent_update_service.publish(
                        session, version_code, updated_by="seed"
                    )
                    published = True

                session.commit()
                print(f"seed: loaded {name} {version_name} (versionCode {version_code})")
                if published:
                    print(
                        f"seed: offering {version_name} to the fleet "
                        f"(devices update on their next check-in)"
                    )
        except package_service.PackageError as exc:
            # The ordinary case on every restart after the first.
            print(f"seed: {path.name} not loaded — {exc}")
        except Exception as exc:  # noqa: BLE001 - startup must survive this
            print(f"seed: {path.name} FAILED — {type(exc).__name__}: {exc}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli", description="ATLAS operations")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init-pki", help="create the device CA and signing keys")
    init.add_argument("--pki-dir", default=None, help="override the configured PKI directory")
    init.add_argument(
        "--dev-server-cert",
        action="store_true",
        help="also emit a self-signed TLS cert for the local proxy (development only)",
    )
    init.add_argument("--hostname", default="localhost", help="hostname for the dev TLS cert")
    init.add_argument(
        "--san",
        action="append",
        default=[],
        metavar="NAME_OR_IP",
        help="extra name or IP the dev TLS cert should be valid for (repeatable)",
    )
    init.add_argument(
        "--force-server-cert",
        action="store_true",
        help="reissue the dev TLS cert even if one exists (leaves the device CA alone)",
    )
    init.set_defaults(func=init_pki)

    seed = subparsers.add_parser(
        "seed-packages", help="load the applications bundled in dist/ into the library"
    )
    seed.add_argument(
        "directory",
        nargs="?",
        default=None,
        help="directory of APKs to load (default: /seed)",
    )
    seed.set_defaults(func=seed_packages)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
