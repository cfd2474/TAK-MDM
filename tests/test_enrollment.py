"""Enrollment, device identity, and mTLS authentication."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings, get_settings
from app.db.models import Device, DeviceCertificate, EnrollmentToken
from app.main import app
from app.security.ca import CertificateAuthority
from app.services import provisioning
from tests.conftest import generate_csr


def create_token(client: TestClient, **overrides) -> dict:
    body = {"name": "Field Rollout", **overrides}
    response = client.post("/api/v1/enrollment-tokens", json=body)
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# Tokens
# --------------------------------------------------------------------------- #


def test_token_secret_is_returned_once_and_not_stored(client: TestClient, db):
    created = create_token(client)
    secret = created["secret"]

    stored = db.scalars(select(EnrollmentToken)).all()
    assert len(stored) == 1
    # Only a hash is persisted, so a database dump yields nothing usable.
    assert stored[0].token_hash != secret
    assert secret not in str(stored[0].__dict__)

    listed = client.get("/api/v1/enrollment-tokens").json()
    assert "secret" not in listed[0]
    assert listed[0]["prefix"] == secret[:8]


def test_enroll_with_unknown_token_is_rejected(client: TestClient):
    response = client.post(
        "/api/v1/enroll",
        json={
            "token": "not-a-real-token",
            "csr_pem": generate_csr(),
            "serial_number": "R5CN00TAK01",
        },
    )
    assert response.status_code == 401


def test_revoked_token_cannot_enroll(client: TestClient):
    created = create_token(client)
    client.post(f"/api/v1/enrollment-tokens/{created['token']['id']}/revoke")

    response = client.post(
        "/api/v1/enroll",
        json={
            "token": created["secret"],
            "csr_pem": generate_csr(),
            "serial_number": "R5CN00TAK01",
        },
    )
    assert response.status_code == 401


def test_expired_token_cannot_enroll(client: TestClient, db):
    created = create_token(client)

    token = db.scalars(select(EnrollmentToken)).one()
    token.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()

    response = client.post(
        "/api/v1/enroll",
        json={
            "token": created["secret"],
            "csr_pem": generate_csr(),
            "serial_number": "R5CN00TAK01",
        },
    )
    assert response.status_code == 401


def test_token_use_limit_is_enforced(client: TestClient):
    created = create_token(client, max_uses=1)
    secret = created["secret"]

    first = client.post(
        "/api/v1/enroll",
        json={"token": secret, "csr_pem": generate_csr(), "serial_number": "DEVICE-1"},
    )
    second = client.post(
        "/api/v1/enroll",
        json={"token": secret, "csr_pem": generate_csr(), "serial_number": "DEVICE-2"},
    )

    assert first.status_code == 201
    assert second.status_code == 401


def test_unlimited_token_enrolls_a_whole_shipment(client: TestClient):
    """The KME case: one profile, many devices."""
    secret = create_token(client, max_uses=None)["secret"]

    for index in range(5):
        response = client.post(
            "/api/v1/enroll",
            json={
                "token": secret,
                "csr_pem": generate_csr(),
                "serial_number": f"DEVICE-{index}",
            },
        )
        assert response.status_code == 201

    assert len(client.get("/api/v1/devices").json()) == 5


# --------------------------------------------------------------------------- #
# Certificate issuance
# --------------------------------------------------------------------------- #


def test_enrollment_issues_a_certificate_bound_to_the_device(client: TestClient, ca):
    result = client.post(
        "/api/v1/enroll",
        json={
            "token": create_token(client)["secret"],
            "csr_pem": generate_csr(),
            "serial_number": "R5CN00TAK01",
        },
    ).json()

    certificate = x509.load_pem_x509_certificate(result["certificate_pem"].encode())

    ca.verify(certificate)  # raises if the chain does not hold
    assert str(CertificateAuthority.device_id_from(certificate)) == result["device_id"]


def test_csr_subject_is_not_trusted(client: TestClient):
    """A CSR asking to be called something else is ignored, not honoured."""
    result = client.post(
        "/api/v1/enroll",
        json={
            "token": create_token(client)["secret"],
            "csr_pem": generate_csr(common_name="00000000-0000-0000-0000-000000000000"),
            "serial_number": "R5CN00TAK01",
        },
    ).json()

    certificate = x509.load_pem_x509_certificate(result["certificate_pem"].encode())
    assert str(CertificateAuthority.device_id_from(certificate)) == result["device_id"]


def test_malformed_csr_is_rejected(client: TestClient):
    response = client.post(
        "/api/v1/enroll",
        json={
            "token": create_token(client)["secret"],
            "csr_pem": "-----BEGIN CERTIFICATE REQUEST-----\nnonsense\n-----END CERTIFICATE REQUEST-----",
            "serial_number": "R5CN00TAK01",
        },
    )
    assert response.status_code == 422


def test_rsa_key_is_rejected(client: TestClient):
    response = client.post(
        "/api/v1/enroll",
        json={
            "token": create_token(client)["secret"],
            "csr_pem": generate_csr(use_rsa=True),
            "serial_number": "R5CN00TAK01",
        },
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Re-enrollment
# --------------------------------------------------------------------------- #


def test_reenrollment_readopts_the_device_and_revokes_the_old_certificate(
    client: TestClient, db
):
    """A wipe plus KME re-enroll is routine and must not orphan the device."""
    first = client.post(
        "/api/v1/enroll",
        json={
            "token": create_token(client)["secret"],
            "csr_pem": generate_csr(),
            "serial_number": "R5CN00TAK01",
        },
    ).json()

    second = client.post(
        "/api/v1/enroll",
        json={
            "token": create_token(client, name="Second")["secret"],
            "csr_pem": generate_csr(),
            "serial_number": "R5CN00TAK01",
        },
    ).json()

    assert first["device_id"] == second["device_id"]
    assert len(client.get("/api/v1/devices").json()) == 1

    certificates = db.scalars(select(DeviceCertificate)).all()
    revoked = [c for c in certificates if c.revoked_at is not None]
    assert len(certificates) == 2
    assert len(revoked) == 1


def test_reenrollment_preserves_group_membership(client: TestClient):
    group = client.post("/api/v1/groups", json={"name": "Field Teams"}).json()

    first = client.post(
        "/api/v1/enroll",
        json={
            "token": create_token(client, group_ids=[group["id"]])["secret"],
            "csr_pem": generate_csr(),
            "serial_number": "R5CN00TAK01",
        },
    ).json()

    policy = client.post(
        "/api/v1/policies",
        json={"name": "Group PW", "policy_type": "PASSWORD", "spec": {"min_length": 8}},
    ).json()
    client.post(
        "/api/v1/assignments",
        json={
            "policy_id": policy["id"],
            "scope": "group",
            "target_id": group["id"],
            "rank": 1,
        },
    )

    # Re-enroll with a token carrying no scoping at all.
    client.post(
        "/api/v1/enroll",
        json={
            "token": create_token(client, name="Bare")["secret"],
            "csr_pem": generate_csr(),
            "serial_number": "R5CN00TAK01",
        },
    )

    effective = client.get(
        f"/api/v1/devices/{first['device_id']}/effective-policy"
    ).json()
    assert effective["values"]["PASSWORD"]["min_length"] == 8


# --------------------------------------------------------------------------- #
# Token scoping ties enrollment to the Chunk 1 policy engine
# --------------------------------------------------------------------------- #


def test_token_scoping_lands_the_device_in_its_policy_stack(client: TestClient):
    group = client.post("/api/v1/groups", json={"name": "Field Teams"}).json()
    tag = client.post("/api/v1/tags", json={"name": "quarantine"}).json()

    group_policy = client.post(
        "/api/v1/policies",
        json={"name": "Group PW", "policy_type": "PASSWORD", "spec": {"min_length": 8}},
    ).json()
    tag_policy = client.post(
        "/api/v1/policies",
        json={
            "name": "No Camera",
            "policy_type": "RESTRICTIONS",
            "spec": {"allow_camera": False},
        },
    ).json()
    for policy, scope, target in (
        (group_policy, "group", group["id"]),
        (tag_policy, "tag", tag["id"]),
    ):
        client.post(
            "/api/v1/assignments",
            json={"policy_id": policy["id"], "scope": scope, "target_id": target, "rank": 1},
        )

    result = client.post(
        "/api/v1/enroll",
        json={
            "token": create_token(client, group_ids=[group["id"]], tag_ids=[tag["id"]])[
                "secret"
            ],
            "csr_pem": generate_csr(),
            "serial_number": "R5CN00TAK01",
        },
    ).json()

    # The device arrives already carrying its policy — no second manual step.
    effective = client.get(
        f"/api/v1/devices/{result['device_id']}/effective-policy"
    ).json()
    assert effective["values"]["PASSWORD"]["min_length"] == 8
    assert effective["values"]["RESTRICTIONS"]["allow_camera"] is False
    assert result["state_version"] >= 1


# --------------------------------------------------------------------------- #
# mTLS authentication
# --------------------------------------------------------------------------- #


def test_checkin_with_a_valid_certificate(client: TestClient, enrolled, mtls_headers):
    result = enrolled()

    response = client.post(
        "/api/v1/device/checkin",
        json={"state_version": result["state_version"], "agent_version": "0.1.0"},
        headers=mtls_headers(result["certificate_pem"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["device_id"] == result["device_id"]
    assert body["policy_changed"] is False


def test_checkin_reports_a_policy_change(client: TestClient, enrolled, mtls_headers):
    result = enrolled()

    response = client.post(
        "/api/v1/device/checkin",
        json={"state_version": result["state_version"] - 1},
        headers=mtls_headers(result["certificate_pem"]),
    )
    assert response.json()["policy_changed"] is True


def test_checkin_records_the_device_report(client: TestClient, enrolled, mtls_headers):
    result = enrolled()

    client.post(
        "/api/v1/device/checkin",
        json={"agent_version": "1.2.3", "os_version": "16"},
        headers=mtls_headers(result["certificate_pem"]),
    )

    device = client.get(f"/api/v1/devices/{result['device_id']}").json()
    assert device["agent_version"] == "1.2.3"
    assert device["last_checkin_at"] is not None


def test_checkin_without_a_certificate_is_unauthorized(client: TestClient, enrolled):
    enrolled()
    assert client.post("/api/v1/device/checkin", json={}).status_code == 401


def test_checkin_with_a_malformed_certificate_is_unauthorized(
    client: TestClient, enrolled, mtls_headers
):
    enrolled()
    response = client.post(
        "/api/v1/device/checkin", json={}, headers=mtls_headers("not a certificate")
    )
    assert response.status_code == 401


def test_certificate_from_another_ca_is_rejected(
    client: TestClient, enrolled, mtls_headers, tmp_path
):
    """A self-signed impostor CA must not be able to mint a valid device identity."""
    result = enrolled()
    rogue = CertificateAuthority.load_or_create(
        tmp_path / "rogue", common_name="Rogue CA", validity_days=30
    )
    forged = rogue.sign_csr(
        generate_csr(),
        device_id=uuid.UUID(result["device_id"]),
        serial_number="R5CN00TAK01",
        validity_days=30,
    )

    response = client.post(
        "/api/v1/device/checkin", json={}, headers=mtls_headers(forged.to_pem())
    )
    assert response.status_code == 401


def test_revoked_certificate_is_forbidden(client: TestClient, enrolled, mtls_headers):
    result = enrolled()
    client.post(f"/api/v1/devices/{result['device_id']}/retire")

    response = client.post(
        "/api/v1/device/checkin",
        json={},
        headers=mtls_headers(result["certificate_pem"]),
    )
    assert response.status_code == 403


def test_url_encoded_certificate_header_is_accepted(
    client: TestClient, enrolled, mtls_headers
):
    """nginx forwards $ssl_client_escaped_cert URL-encoded."""
    from urllib.parse import quote

    result = enrolled()
    response = client.post(
        "/api/v1/device/checkin",
        json={},
        headers=mtls_headers(quote(result["certificate_pem"])),
    )
    assert response.status_code == 200


def test_old_certificate_stops_working_after_reenrollment(
    client: TestClient, enrolled, mtls_headers
):
    first = enrolled()

    client.post(
        "/api/v1/enroll",
        json={
            "token": create_token(client, name="Re-enroll")["secret"],
            "csr_pem": generate_csr(),
            "serial_number": "R5CN00TAK01",
        },
    )

    response = client.post(
        "/api/v1/device/checkin", json={}, headers=mtls_headers(first["certificate_pem"])
    )
    assert response.status_code == 403


# --------------------------------------------------------------------------- #
# Provisioning payloads
# --------------------------------------------------------------------------- #


def test_kme_payload_is_always_available(client: TestClient):
    created = create_token(client)
    kme = created["provisioning"]["kme"]

    assert kme["custom_json_data"]["enrollment_token"] == created["secret"]
    assert kme["mdm_package_name"]


def test_qr_payload_is_withheld_without_a_signature_checksum(client: TestClient):
    """Android rejects provisioning without it, and the on-device failure is opaque."""
    created = create_token(client)

    assert created["provisioning"]["qr"] is None
    assert "signature" in created["provisioning"]["qr_unavailable_reason"].lower()


def test_qr_payload_contains_the_android_extras(settings: Settings):
    configured = settings.model_copy(update={"agent_signature_checksum": "abc123"})

    payload = provisioning.qr_payload(configured, "secret-value", wifi_ssid="TAK-Field")

    assert (
        payload["android.app.extra.PROVISIONING_ADMIN_EXTRAS_BUNDLE"]["enrollment_token"]
        == "secret-value"
    )
    assert payload["android.app.extra.PROVISIONING_DEVICE_ADMIN_SIGNATURE_CHECKSUM"] == "abc123"
    assert payload["android.app.extra.PROVISIONING_WIFI_SSID"] == "TAK-Field"


def test_qr_payload_omits_wifi_when_not_requested(settings: Settings):
    configured = settings.model_copy(update={"agent_signature_checksum": "abc123"})

    payload = provisioning.qr_payload(configured, "secret-value")

    assert "android.app.extra.PROVISIONING_WIFI_SSID" not in payload


def test_provisioning_can_be_rerendered_with_a_held_secret(client: TestClient):
    secret = create_token(client)["secret"]

    response = client.post("/api/v1/provisioning/payloads", json={"secret": secret})

    assert response.status_code == 200
    assert response.json()["kme"]["custom_json_data"]["enrollment_token"] == secret


def test_provisioning_rerender_rejects_an_unknown_secret(client: TestClient):
    response = client.post("/api/v1/provisioning/payloads", json={"secret": "made-up"})
    assert response.status_code == 404
