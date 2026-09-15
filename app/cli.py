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
from app.security.ca import (
    CertificateAuthority,
    CertificateError,
    issue_intermediate,
)
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


def ca_status(args: argparse.Namespace) -> int:
    """Report the certificate authority as JSON, for a tool to render.

    ⚠️ Read-only and never raises on a half-finished ceremony. The state this is
    most needed in is the broken one — root key removed, intermediate missing — and
    a status command that threw there would leave an operator with a blank page
    instead of the sentence explaining what to do.
    """
    import json as _json

    settings = get_settings()
    pki_dir = Path(args.pki_dir or settings.pki_dir)
    report: dict = {
        "pki_dir": str(pki_dir),
        "root_certificate": (pki_dir / "ca.crt").exists(),
        # ⚠️ The single most important field. `false` is the goal state, and an
        # operator who has run the ceremony but left the key behind has changed
        # nothing about their exposure (SEC_AUDIT S-2).
        "root_key_on_server": (pki_dir / "ca.key").exists(),
        "ok": False,
    }

    try:
        ca = CertificateAuthority.load_or_create(
            pki_dir,
            common_name=settings.ca_common_name,
            validity_days=settings.ca_validity_days,
        )
    except Exception as exc:
        report["error"] = str(exc)
        print(_json.dumps(report, indent=2))
        return 0

    certificate = ca.certificate
    expires = certificate.not_valid_after_utc
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=dt.timezone.utc)
    remaining = expires - dt.datetime.now(dt.timezone.utc)

    report.update(
        ok=True,
        issuing_subject=certificate.subject.rfc4514_string(),
        # utc-by-design: a certificate's validity is a UTC instant, and this is
        # machine-readable output rather than a rendered page.
        issuing_expires=expires.strftime("%Y-%m-%d"),
        issuing_days_left=remaining.days,
        # More than one anchor means the root has been separated from the signer.
        trust_anchors=len(ca.trusted),
        is_split=len(ca.trusted) > 1,
        device_cert_validity_days=settings.device_cert_validity_days,
        renew_within_days=settings.device_cert_renew_within_days,
        # Months, because reissuing needs the root fetched from wherever it went.
        needs_attention=remaining.days < 180,
    )
    print(_json.dumps(report, indent=2))
    return 0


def ca_issue_intermediate(args: argparse.Namespace) -> int:
    """Issue the intermediate that signs from now on, and say what to do next.

    ⚠️ The instructions matter as much as the certificate. An operator who runs
    this and leaves `ca.key` on the server has changed the plumbing and gained
    nothing: the root is still sitting on an internet-facing machine, which is the
    entire finding (SEC_AUDIT S-2).
    """
    settings = get_settings()
    pki_dir = Path(args.pki_dir or settings.pki_dir)

    # ⚠️ A device authenticates only while its *issuer* is also valid, and
    # nothing renews a device certificate — `sign_csr` is reachable from enrolment
    # and nowhere else. So an intermediate shorter than the device certificate
    # validity silently caps every certificate it issues, and recovering a
    # truncated device means a factory reset and a re-provision.
    device_days = settings.device_cert_validity_days
    if args.days < device_days:
        lost = device_days - args.days
        print(f"WARNING: this intermediate is valid for {args.days} days, but device")
        print(f"certificates are issued for {device_days}. Every device this signs will")
        print(f"stop authenticating {lost} days before its own certificate expires, and")
        print("there is no renewal — each one needs a factory reset and re-provision.")
        print()
        print(f"Use --days {device_days + 365} to leave a year of issuing at full device life,")
        print("or keep this if you have accepted the re-enrolment.")
        print()

    try:
        certificate = issue_intermediate(
            pki_dir,
            common_name=args.common_name or f"{settings.ca_common_name} Issuing CA",
            validity_days=args.days,
        )
    except CertificateError as exc:
        print(f"could not issue an intermediate: {exc}")
        return 1

    # utc-by-design: a certificate's validity window is a UTC instant by
    # definition, this is a date printed in a terminal rather than rendered in the
    # console, and the CLI has no session to read the display timezone from.
    expires = certificate.not_valid_after_utc.strftime("%Y-%m-%d")
    print(f"issuing CA:   {pki_dir / 'issuing.crt'}")
    print(f"  subject:    {certificate.subject.rfc4514_string()}")
    print(f"  expires:    {expires}")
    print(f"  serial:     {certificate.serial_number:x}")
    print()
    print("ATLAS now signs device certificates with this intermediate.")
    print("Nothing on any enrolled device changes: they chain to the root, which")
    print("has not moved.")
    print()
    print("NEXT, and the only part that improves anything:")
    print(f"  1. Copy {pki_dir / 'ca.key'} somewhere off this machine.")
    print("     A password manager, an encrypted USB stick, a printed paper backup —")
    print("     anywhere an attacker who owns this server cannot reach.")
    print(f"  2. Delete {pki_dir / 'ca.key'} from this machine.")
    print("  3. Restart ATLAS and confirm a device still checks in.")
    print()
    print("You need the root key again only to issue the next intermediate, or to")
    print("revoke this one. Losing it means no new intermediate can ever be issued,")
    print(f"and every device must re-enrol after {expires}.")
    return 0


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

    status = subparsers.add_parser(
        "ca-status", help="report the certificate authority as JSON"
    )
    status.add_argument("--pki-dir", default=None)
    status.set_defaults(func=ca_status)

    intermediate = subparsers.add_parser(
        "ca-issue-intermediate",
        help="sign an issuing CA with the root, so the root can go offline",
    )
    intermediate.add_argument("--pki-dir", default=None)
    intermediate.add_argument("--common-name", default=None)
    intermediate.add_argument(
        "--days", type=int, default=1825,
        help="how long the intermediate is valid. Five years by default: devices "
             "renew their own certificates (W174) and roll onto the current "
             "issuer by themselves, so rotating costs a ceremony and nothing "
             "else. ⚠️ It must still exceed the device certificate validity, or "
             "certificates are truncated between renewals.",
    )
    intermediate.set_defaults(func=ca_issue_intermediate)

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
