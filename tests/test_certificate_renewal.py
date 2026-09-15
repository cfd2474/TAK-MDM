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

"""A device renews its own certificate (W174).

⚠️ **This endpoint is authenticated by the certificate it replaces.** That is what
makes it safe to add beside unauthenticated enrolment: only a device already
holding a valid identity can extend one, so it opens no new way in. The tests that
matter most are the ones proving it cannot be used to obtain an identity, and the
ones proving a failed renewal leaves the device exactly as it was.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import DeviceCertificate
from app.services import certificate_renewal


def _csr(key, common_name="renewal"):
    return (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)]))
        .sign(key, hashes.SHA256())
        .public_bytes(serialization.Encoding.PEM)
        .decode()
    )


def _enrol_keeping_key(client: TestClient, serial: str = "R5CN00TAK01"):
    """Enrol a device and keep its private key.

    ⚠️ The shared `enrolled` fixture throws the key away — nothing needed it until
    renewal, which must prove the *same* key is reused. Written here rather than
    changing the fixture every other test depends on.
    """
    from tests.conftest import ADMIN_HEADERS

    created = client.post(
        "/api/v1/enrollment-tokens",
        json={"name": "Renewal Token", "group_ids": []},
        headers=ADMIN_HEADERS,
    )
    assert created.status_code == 201, created.text

    key = ec.generate_private_key(ec.SECP256R1())
    response = client.post(
        "/api/v1/enroll",
        json={
            "token": created.json()["secret"],
            "csr_pem": _csr(key, common_name="unverified"),
            "serial_number": serial,
            "model": "SM-G736U1",
            "os_version": "16",
        },
    )
    assert response.status_code == 201, response.text
    return response.json(), key


# --------------------------------------------------------------------------- #
# The ordinary path
# --------------------------------------------------------------------------- #


def test_a_device_renews_over_its_own_connection(client: TestClient, db, mtls_headers):
    result, key = _enrol_keeping_key(client)
    headers = mtls_headers(result["certificate_pem"])

    response = client.post(
        "/api/v1/device/certificate", json={"csr_pem": _csr(key)}, headers=headers
    )

    assert response.status_code == 200, response.text
    body = response.json()
    fresh = x509.load_pem_x509_certificate(body["certificate_pem"].encode())
    old = x509.load_pem_x509_certificate(result["certificate_pem"].encode())
    assert fresh.serial_number != old.serial_number
    assert fresh.public_key().public_numbers() == old.public_key().public_numbers()


def test_the_new_certificate_authenticates(client: TestClient, db, mtls_headers):
    """The point of the whole exercise: the device can use what it was given."""
    from tests.test_checkin import checkin

    result, key = _enrol_keeping_key(client)
    headers = mtls_headers(result["certificate_pem"])

    renewed = client.post(
        "/api/v1/device/certificate", json={"csr_pem": _csr(key)}, headers=headers
    ).json()["certificate_pem"]

    body = checkin(client, mtls_headers(renewed))

    assert body["device_id"] == result["device_id"]


def test_the_old_certificate_keeps_working(client: TestClient, db, mtls_headers):
    """⚠️ It authenticated the request that asked for the new one.

    Revoking on issue would cut the connection carrying the reply, and a device
    that never received the answer would have destroyed the credential it had.
    """
    from tests.test_checkin import checkin

    result, key = _enrol_keeping_key(client)
    headers = mtls_headers(result["certificate_pem"])

    client.post("/api/v1/device/certificate", json={"csr_pem": _csr(key)}, headers=headers)

    assert checkin(client, headers)["device_id"] == result["device_id"]


def test_both_certificates_are_on_record(client: TestClient, db, mtls_headers):
    result, key = _enrol_keeping_key(client)
    headers = mtls_headers(result["certificate_pem"])

    client.post("/api/v1/device/certificate", json={"csr_pem": _csr(key)}, headers=headers)
    db.expire_all()

    rows = db.scalars(select(DeviceCertificate)).all()
    assert len(rows) == 2
    assert all(row.revoked_at is None for row in rows)


def test_the_answer_carries_the_whole_trust_bundle(client: TestClient, db, mtls_headers):
    """⚠️ Not just the issuer. A device that stored only its own issuer could not
    build a chain once that intermediate retired."""
    result, key = _enrol_keeping_key(client)
    headers = mtls_headers(result["certificate_pem"])

    body = client.post(
        "/api/v1/device/certificate", json={"csr_pem": _csr(key)}, headers=headers
    ).json()

    assert "BEGIN CERTIFICATE" in body["ca_pem"]


# --------------------------------------------------------------------------- #
# ⚠️ It must not become a way in
# --------------------------------------------------------------------------- #


def test_renewal_without_a_certificate_is_refused(client: TestClient, enrolled):
    """The endpoint sits beside unauthenticated enrolment; it must not be one."""
    key = ec.generate_private_key(ec.SECP256R1())

    response = client.post("/api/v1/device/certificate", json={"csr_pem": _csr(key)})

    assert response.status_code == 401


def test_a_request_for_a_different_key_is_refused(
    client: TestClient, db, enrolled, mtls_headers
):
    """⚠️ The agent's own installer refuses a certificate issued for a key it does
    not hold, so issuing one would produce a certificate the device is obliged to
    throw away — a renewal that fails silently on both sides."""
    result, _ = _enrol_keeping_key(client)
    headers = mtls_headers(result["certificate_pem"])
    stranger = ec.generate_private_key(ec.SECP256R1())

    response = client.post(
        "/api/v1/device/certificate", json={"csr_pem": _csr(stranger)}, headers=headers
    )

    assert response.status_code == 400
    assert "different key" in response.json()["detail"]


def test_a_malformed_request_is_refused(client: TestClient, db, mtls_headers):
    result, _ = _enrol_keeping_key(client)
    headers = mtls_headers(result["certificate_pem"])

    response = client.post(
        "/api/v1/device/certificate", json={"csr_pem": "not a csr"}, headers=headers
    )

    assert response.status_code == 400


def test_a_refused_renewal_records_nothing(client: TestClient, db, mtls_headers):
    """A device that was told no keeps exactly what it had."""
    result, _ = _enrol_keeping_key(client)
    headers = mtls_headers(result["certificate_pem"])
    stranger = ec.generate_private_key(ec.SECP256R1())

    client.post(
        "/api/v1/device/certificate", json={"csr_pem": _csr(stranger)}, headers=headers
    )
    db.expire_all()

    assert len(db.scalars(select(DeviceCertificate)).all()) == 1


def test_a_revoked_device_cannot_renew(client: TestClient, db, mtls_headers):
    """⚠️ Otherwise revocation is not revocation: a device told to stop could
    extend itself indefinitely on the credential being withdrawn."""
    from datetime import datetime as _dt

    result, key = _enrol_keeping_key(client)
    headers = mtls_headers(result["certificate_pem"])

    record = db.scalars(select(DeviceCertificate)).one()
    record.revoked_at = _dt.now(timezone.utc)
    db.commit()

    response = client.post(
        "/api/v1/device/certificate", json={"csr_pem": _csr(key)}, headers=headers
    )

    assert response.status_code == 403


# --------------------------------------------------------------------------- #
# When to renew
# --------------------------------------------------------------------------- #


def test_a_fresh_certificate_is_not_due():
    expiry = datetime.now(timezone.utc) + timedelta(days=800)

    assert not certificate_renewal.should_renew(expiry, window_days=30)


def test_one_inside_the_window_is_due():
    expiry = datetime.now(timezone.utc) + timedelta(days=20)

    assert certificate_renewal.should_renew(expiry, window_days=30)


def test_an_expired_certificate_reads_as_due():
    """A lapsed device cannot reach the endpoint, but a caller reasoning about a
    stored expiry should get the obvious answer."""
    expiry = datetime.now(timezone.utc) - timedelta(days=1)

    assert certificate_renewal.should_renew(expiry, window_days=30)


def test_a_naive_expiry_is_read_as_utc():
    """Everything stored is UTC; a naive value must not take the host's zone."""
    expiry = (datetime.now(timezone.utc) + timedelta(days=800)).replace(tzinfo=None)

    assert not certificate_renewal.should_renew(expiry, window_days=30)


def test_the_window_is_days_remaining_not_a_fraction_of_life():
    """⚠️ So that changing the issued validity does not silently move when every
    device in the fleet decides to renew."""
    soon = datetime.now(timezone.utc) + timedelta(days=10)

    assert certificate_renewal.should_renew(soon, window_days=30)
    assert not certificate_renewal.should_renew(soon, window_days=5)


def test_a_corrupted_request_is_refused(client: TestClient, db, mtls_headers):
    """A request whose bytes have been damaged is rejected, not signed.

    ⚠️ **This exercises the parse, not the signature check.** Mutation-checking
    showed that removing `is_signature_valid` changes nothing any test can see, and
    that is honest rather than a gap: a CSR must also carry the device's *own*
    public key, so the worst a bad signature could buy is a certificate for the key
    the caller already holds. The signature check is defence in depth and is kept
    for that reason, not because anything downstream depends on it.

    Building a CSR that parses cleanly and carries a genuinely invalid signature
    needs DER surgery; it was judged not worth the fixture for a guard that cannot
    matter while the key-match check stands.
    """
    result, key = _enrol_keeping_key(client)
    headers = mtls_headers(result["certificate_pem"])

    valid = _csr(key)
    body = "".join(valid.splitlines()[1:-1])
    # Flip a byte deep inside the DER, which lands in the signature.
    corrupted = body[:-8] + ("A" if body[-8] != "A" else "B") + body[-7:]
    tampered = "-----BEGIN CERTIFICATE REQUEST-----\n" + corrupted + "\n-----END CERTIFICATE REQUEST-----\n"

    response = client.post(
        "/api/v1/device/certificate", json={"csr_pem": tampered}, headers=headers
    )

    assert response.status_code == 400


def test_the_bundle_carries_every_anchor_not_just_the_issuer(tmp_path, db):
    """⚠️ The rotation case, which a single-certificate CA cannot show.

    A device that stored only its own issuer could not build a chain once that
    intermediate retired — so the answer has to carry the whole trust store, and
    that is only visible on a CA that has one.
    """
    from app.security.ca import CertificateAuthority, issue_intermediate
    from app.db.models import Device, EnrollmentState

    pki = tmp_path / "pki"
    CertificateAuthority.load_or_create(pki, common_name="Bundle Root", validity_days=3650)
    issue_intermediate(pki, common_name="Bundle Issuing", validity_days=1190)
    ca = CertificateAuthority.load_or_create(
        pki, common_name="Bundle Root", validity_days=3650
    )
    assert len(ca.trusted) == 2, "the fixture must have an intermediate to be meaningful"

    device = Device(
        serial_number="BUNDLE-1", enrollment_state=EnrollmentState.ENROLLED,
        state_version=0, acked_state_version=0,
    )
    db.add(device)
    db.flush()

    key = ec.generate_private_key(ec.SECP256R1())
    issued = ca.sign_csr(
        _csr(key), device_id=device.id, serial_number="BUNDLE-1", validity_days=90
    )
    presented = x509.load_pem_x509_certificate(issued.to_pem().encode())

    renewal = certificate_renewal.renew(
        db, device, presented, _csr(key), ca=ca, validity_days=90
    )

    assert renewal.ca_pem.count("BEGIN CERTIFICATE") == 2


def test_a_naive_expiry_is_read_as_utc_not_as_the_hosts_zone():
    """⚠️ Everything stored is UTC, and a naive value must not take the host's zone.

    ⚠️ **This test cannot fail on a host whose local zone is UTC**, because the two
    readings agree there — the same blind spot recorded for
    `test_a_naive_timestamp_is_read_as_utc_not_as_the_servers_zone` in
    `test_timezone.py`. It was mutation-checked on a host at UTC-7. That is why the
    code says `replace(tzinfo=utc)` explicitly rather than relying on a default.
    """
    aware = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)
    naive = aware.replace(tzinfo=None)
    # ⚠️ Three hours *inside* the window, so that reading the value in any zone
    # west of UTC pushes it back outside and the two answers differ. A `now` two
    # hours outside made both readings "not due" and the test could not fail.
    now = aware - timedelta(days=30) + timedelta(hours=3)

    assert certificate_renewal.should_renew(
        naive, now=now, window_days=30
    ) == certificate_renewal.should_renew(aware, now=now, window_days=30)
