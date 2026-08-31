"""Simulate a device enrolling and checking in, end to end over real mTLS.

Runs the exact sequence the Kotlin agent will: mint an enrollment token, generate an
EC P-256 keypair, submit a CSR, receive a client certificate, then check in through
the nginx proxy presenting that certificate.

The bundle signature is verified here with a **deliberately independent**
implementation of canonical JSON — it does not import the server's. That is the
point: it is the contract the agent must reimplement in Kotlin, and if the two ever
disagree this script fails the same way a tablet in the field would.

    python scripts/dev_enroll.py --serial R5CN00TAK01

Requires `docker compose up` to be running.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.x509.oid import NameOID


def agent_canonical_json(payload: Any) -> bytes:
    """What the agent must implement: sorted keys, no padding, UTF-8."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def verify_bundle(document: dict, signature_b64: str, public_key_b64: str) -> bool:
    public_key = ed25519.Ed25519PublicKey.from_public_bytes(
        base64.b64decode(public_key_b64)
    )
    try:
        public_key.verify(base64.b64decode(signature_b64), agent_canonical_json(document))
    except Exception:
        return False
    return True


def generate_key_and_csr(common_name: str) -> tuple[ec.EllipticCurvePrivateKey, str]:
    """On a real device this key is generated inside the Keystore and never leaves."""
    key = ec.generate_private_key(ec.SECP256R1())
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)]))
        .sign(key, hashes.SHA256())
    )
    return key, csr.public_bytes(serialization.Encoding.PEM).decode()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default="R5CN00TAK01")
    parser.add_argument("--model", default="SM-G736U1")
    parser.add_argument(
        "--admin-url",
        default="http://127.0.0.1:8000",
        help="direct API, bypassing the proxy (development only)",
    )
    parser.add_argument("--device-url", default="https://localhost:8443")
    parser.add_argument("--pki-dir", default="pki", help="where the dev CA lives")
    parser.add_argument("--out-dir", default="pki/devices")
    args = parser.parse_args(argv)

    pki_dir = Path(args.pki_dir)
    server_ca = pki_dir / "server.crt"
    if not server_ca.exists():
        print(
            f"{server_ca} not found — is `docker compose up` running?", file=sys.stderr
        )
        return 1

    out_dir = Path(args.out_dir) / args.serial
    out_dir.mkdir(parents=True, exist_ok=True)

    admin = httpx.Client(base_url=args.admin_url, timeout=30)

    print("1. minting an enrollment token")
    created = admin.post(
        "/api/v1/enrollment-tokens",
        json={"name": f"dev-{args.serial}", "max_uses": 1},
    )
    created.raise_for_status()
    secret = created.json()["secret"]
    print(f"   token {secret[:8]}...")

    print("2. generating EC P-256 keypair and CSR")
    key, csr_pem = generate_key_and_csr(args.serial)

    print("3. enrolling through the proxy")
    device = httpx.Client(base_url=args.device_url, verify=str(server_ca), timeout=30)
    enrolled = device.post(
        "/api/v1/enroll",
        json={
            "token": secret,
            "csr_pem": csr_pem,
            "serial_number": args.serial,
            "model": args.model,
            "os_version": "16",
            "agent_version": "dev-0.1.0",
        },
    )
    enrolled.raise_for_status()
    result = enrolled.json()

    key_path = out_dir / "device.key"
    cert_path = out_dir / "device.crt"
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_path.write_text(result["certificate_pem"])
    print(f"   device id {result['device_id']}")
    print(f"   certificate -> {cert_path}")

    print("4. checking in over mTLS")
    mtls = httpx.Client(
        base_url=args.device_url,
        verify=str(server_ca),
        cert=(str(cert_path), str(key_path)),
        timeout=30,
    )
    checkin = mtls.post(
        "/api/v1/device/checkin",
        json={"state_version": -1, "agent_version": "dev-0.1.0"},
    )
    checkin.raise_for_status()
    body = checkin.json()

    print(f"   state_version      {body['state_version']}")
    print(f"   next check-in      {body['next_checkin_seconds']}s")
    print(f"   commands queued    {len(body['commands'])}")

    if body.get("desired_state"):
        ok = verify_bundle(
            body["desired_state"], body["signature"], result["bundle_signing_public_key"]
        )
        print(f"   bundle signature   {'VALID' if ok else 'INVALID'}")
        if not ok:
            print("   canonical JSON disagreement between agent and server", file=sys.stderr)
            return 1
        print(f"   policy             {json.dumps(body['desired_state']['policy'])}")

    # URL-encoded, because that is the form nginx forwards and the app decodes —
    # and because a raw PEM contains newlines that no HTTP client will send.
    forged_header = {"X-SSL-Client-Cert": quote(result["certificate_pem"])}

    print("\n5. confirming the proxy strips a forged certificate header")
    forged = httpx.Client(base_url=args.device_url, verify=str(server_ca), timeout=30)
    spoofed = forged.post("/api/v1/device/checkin", json={}, headers=forged_header)
    if spoofed.status_code == 403:
        print("   spoofing rejected at the edge (403)")
    else:
        print(
            f"   WARNING: expected 403, got {spoofed.status_code} — "
            "the proxy is not stripping X-SSL-Client-Cert",
            file=sys.stderr,
        )
        return 1

    print("\n6. demonstrating why the direct API port must stay off the network (R7)")
    direct = admin.post("/api/v1/device/checkin", json={}, headers=forged_header)
    if direct.status_code == 200:
        print(
            "   the direct port ACCEPTED a copied certificate whose private key we\n"
            "   never proved we hold. Possession is proven only by the TLS handshake\n"
            "   at the proxy, so port 8000 is bound to loopback and must never be\n"
            "   exposed. Always route devices through :8443."
        )
    else:
        print(f"   direct port returned {direct.status_code}")

    print(f"\ndone. reuse this identity with:\n"
          f"  curl --cacert {server_ca} --cert {cert_path} --key {key_path} \\\n"
          f"    -X POST {args.device_url}/api/v1/device/checkin \\\n"
          f"    -H 'content-type: application/json' -d '{{}}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
