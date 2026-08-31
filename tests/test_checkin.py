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

"""Desired-state check-in protocol, bundle signing, and the command queue."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import CommandStatus, DeviceCommand
from app.security.bundle import BundleSigner, canonical_json


def checkin(client: TestClient, headers: dict, **body) -> dict:
    response = client.post("/api/v1/device/checkin", json=body, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def make_policy(client: TestClient, name: str, min_length: int) -> dict:
    return client.post(
        "/api/v1/policies",
        json={"name": name, "policy_type": "PASSWORD", "spec": {"min_length": min_length}},
    ).json()


def assign_to_device(client: TestClient, policy_id: str, device_id: str, rank: int = 1) -> dict:
    return client.post(
        "/api/v1/assignments",
        json={
            "policy_id": policy_id,
            "scope": "device",
            "target_id": device_id,
            "rank": rank,
        },
    ).json()


# --------------------------------------------------------------------------- #
# Canonical JSON and signing
# --------------------------------------------------------------------------- #


def test_canonical_json_is_key_order_independent():
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})


def test_canonical_json_has_no_insignificant_whitespace():
    assert canonical_json({"a": [1, 2]}) == b'{"a":[1,2]}'


def test_signature_round_trips(signer: BundleSigner):
    document = {"state_version": 3, "policy": {"PASSWORD": {"min_length": 8}}}
    assert signer.verify(document, signer.sign(document)) is True


def test_signature_rejects_a_tampered_document(signer: BundleSigner):
    document = {"state_version": 3, "policy": {"PASSWORD": {"min_length": 8}}}
    signature = signer.sign(document)

    document["policy"]["PASSWORD"]["min_length"] = 4

    assert signer.verify(document, signature) is False


def test_signature_survives_key_reordering(signer: BundleSigner):
    """Canonicalization is what makes this true; without it the agent sees failures."""
    signature = signer.sign({"a": 1, "b": 2})
    assert signer.verify({"b": 2, "a": 1}, signature) is True


def test_bundle_public_key_is_published(client: TestClient, signer: BundleSigner):
    body = client.get("/api/v1/bundle-signing-key").json()

    assert body["algorithm"] == "ed25519"
    assert body["public_key"] == signer.public_key_base64()


def test_enrollment_hands_over_the_bundle_key(client: TestClient, enrolled, signer):
    """Trust is established during the one exchange already authenticated out of band."""
    assert enrolled()["bundle_signing_public_key"] == signer.public_key_base64()


# --------------------------------------------------------------------------- #
# Desired state
# --------------------------------------------------------------------------- #


def test_checkin_returns_a_signed_desired_state(
    client: TestClient, enrolled, mtls_headers, signer
):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    policy = make_policy(client, "Baseline", 8)
    assign_to_device(client, policy["id"], result["device_id"])

    body = checkin(client, headers, state_version=0)

    assert body["desired_state"]["policy"]["PASSWORD"]["min_length"] == 8
    assert signer.verify(body["desired_state"], body["signature"]) is True


def test_desired_state_is_withheld_when_unchanged(
    client: TestClient, enrolled, mtls_headers
):
    """The bandwidth saving that makes frequent check-in viable on a metered link."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    policy = make_policy(client, "Baseline", 8)
    assign_to_device(client, policy["id"], result["device_id"])

    first = checkin(client, headers, state_version=0)
    second = checkin(client, headers, state_version=first["state_version"])

    assert first["desired_state"] is not None
    assert second["desired_state"] is None
    assert second["signature"] is None
    assert second["policy_changed"] is False


def test_force_full_resends_the_bundle(client: TestClient, enrolled, mtls_headers):
    """Escape hatch for an agent whose local cache is gone."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])

    current = checkin(client, headers, state_version=0)["state_version"]
    body = checkin(client, headers, state_version=current, force_full=True)

    assert body["desired_state"] is not None


def test_desired_state_omits_provenance_and_policy_names(
    client: TestClient, enrolled, mtls_headers
):
    """A lost tablet must not carry the fleet's policy structure on it."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    policy = make_policy(client, "Confidential Policy Name", 8)
    assign_to_device(client, policy["id"], result["device_id"])

    body = checkin(client, headers, state_version=0)
    serialized = canonical_json(body["desired_state"]).decode()

    assert "provenance" not in serialized
    assert "Confidential Policy Name" not in serialized
    assert "conflicts" not in serialized


def test_bundle_is_deterministic_for_a_state_version(
    client: TestClient, enrolled, mtls_headers
):
    """Stable bytes per version is what lets a bundle be cached or relayed (D9)."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])

    first = checkin(client, headers, state_version=-1)
    second = checkin(client, headers, state_version=-1)

    assert first["desired_state"] == second["desired_state"]
    assert first["signature"] == second["signature"]


def test_policy_change_bumps_the_version_and_resends(
    client: TestClient, enrolled, mtls_headers
):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    policy = make_policy(client, "Baseline", 8)
    assign_to_device(client, policy["id"], result["device_id"])

    first = checkin(client, headers, state_version=0)
    client.post(f"/api/v1/policies/{policy['id']}/versions", json={"spec": {"min_length": 14}})
    second = checkin(client, headers, state_version=first["state_version"])

    assert second["policy_changed"] is True
    assert second["desired_state"]["policy"]["PASSWORD"]["min_length"] == 14


def test_next_checkin_is_jittered(client: TestClient, enrolled, mtls_headers):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])

    intervals = {checkin(client, headers)["next_checkin_seconds"] for _ in range(15)}

    # 900s +/- 20%
    assert all(720 <= value <= 1080 for value in intervals)
    assert len(intervals) > 1, "a constant interval would return the fleet in lockstep"


# --------------------------------------------------------------------------- #
# Convergence reporting
# --------------------------------------------------------------------------- #


def test_device_reports_the_version_it_applied(client: TestClient, enrolled, mtls_headers):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    policy = make_policy(client, "Baseline", 8)
    assign_to_device(client, policy["id"], result["device_id"])
    current = checkin(client, headers, state_version=0)["state_version"]

    checkin(client, headers, state_version=current, applied_state_version=current)

    device = client.get(f"/api/v1/devices/{result['device_id']}").json()
    assert device["acked_state_version"] == current
    assert device["compliance_status"] == "compliant"


def test_apply_errors_mark_the_device_degraded(client: TestClient, enrolled, mtls_headers):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    current = checkin(client, headers, state_version=0)["state_version"]

    checkin(
        client,
        headers,
        state_version=current,
        applied_state_version=current,
        apply_errors=["could not set min_length: Knox licence inactive"],
    )

    device = client.get(f"/api/v1/devices/{result['device_id']}").json()
    assert device["compliance_status"] == "degraded"
    assert "Knox" in device["compliance_detail"]


def test_total_failure_is_distinguished_from_partial(
    client: TestClient, enrolled, mtls_headers
):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])

    checkin(client, headers, apply_errors=["policy engine unavailable"])

    device = client.get(f"/api/v1/devices/{result['device_id']}").json()
    assert device["compliance_status"] == "failed"


def test_acked_version_never_walks_backwards(client: TestClient, enrolled, mtls_headers):
    """A stale duplicate check-in must not regress the convergence record."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    policy = make_policy(client, "Baseline", 8)
    assign_to_device(client, policy["id"], result["device_id"])
    current = checkin(client, headers, state_version=0)["state_version"]

    checkin(client, headers, applied_state_version=current)
    checkin(client, headers, applied_state_version=0)

    device = client.get(f"/api/v1/devices/{result['device_id']}").json()
    assert device["acked_state_version"] == current


def test_silent_checkin_leaves_the_previous_verdict(
    client: TestClient, enrolled, mtls_headers
):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    checkin(client, headers, applied_state_version=0)

    checkin(client, headers)  # reports nothing about convergence

    device = client.get(f"/api/v1/devices/{result['device_id']}").json()
    assert device["compliance_status"] == "compliant"


def test_reenrollment_resets_convergence(client: TestClient, enrolled, mtls_headers):
    """A wiped device has applied nothing, whatever it claimed before."""
    from tests.test_enrollment import create_token
    from tests.conftest import generate_csr

    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    policy = make_policy(client, "Baseline", 8)
    assign_to_device(client, policy["id"], result["device_id"])
    current = checkin(client, headers, state_version=0)["state_version"]
    checkin(client, headers, applied_state_version=current)

    client.post(
        "/api/v1/enroll",
        json={
            "token": create_token(client, name="Re-enroll")["secret"],
            "csr_pem": generate_csr(),
            "serial_number": "R5CN00TAK01",
        },
    )

    device = client.get(f"/api/v1/devices/{result['device_id']}").json()
    assert device["acked_state_version"] == 0
    assert device["compliance_status"] == "unknown"


# --------------------------------------------------------------------------- #
# Command queue
# --------------------------------------------------------------------------- #


def enqueue(client: TestClient, device_id: str, command_type: str, **extra) -> dict:
    response = client.post(
        f"/api/v1/devices/{device_id}/commands",
        json={"command_type": command_type, **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_queued_command_is_delivered_on_checkin(client: TestClient, enrolled, mtls_headers):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    command = enqueue(client, result["device_id"], "reboot")

    body = checkin(client, headers)

    assert [c["id"] for c in body["commands"]] == [command["id"]]
    assert body["commands"][0]["command_type"] == "reboot"


def test_command_is_redelivered_until_acknowledged(
    client: TestClient, enrolled, mtls_headers
):
    """At-least-once: a device that dies mid-execution must get it again."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    enqueue(client, result["device_id"], "reboot")

    first = checkin(client, headers)
    second = checkin(client, headers)

    assert len(first["commands"]) == 1
    assert len(second["commands"]) == 1


def test_acknowledged_command_is_not_redelivered(
    client: TestClient, enrolled, mtls_headers
):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    command = enqueue(client, result["device_id"], "reboot")

    checkin(client, headers)
    after_ack = checkin(
        client, headers, results=[{"command_id": command["id"], "succeeded": True}]
    )
    assert after_ack["commands"] == []

    stored = client.get(f"/api/v1/devices/{result['device_id']}/commands").json()
    assert stored[0]["status"] == "succeeded"


def test_command_finished_this_cycle_is_not_handed_back(
    client: TestClient, enrolled, mtls_headers
):
    """Results are applied before delivery is computed, within the same request."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    command = enqueue(client, result["device_id"], "reboot")
    checkin(client, headers)

    body = checkin(
        client, headers, results=[{"command_id": command["id"], "succeeded": True}]
    )

    assert body["commands"] == []


def test_failed_command_records_the_error(client: TestClient, enrolled, mtls_headers):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    command = enqueue(client, result["device_id"], "screenshot")

    checkin(
        client,
        headers,
        results=[
            {"command_id": command["id"], "succeeded": False, "error": "permission denied"}
        ],
    )

    stored = client.get(f"/api/v1/devices/{result['device_id']}/commands").json()
    assert stored[0]["status"] == "failed"
    assert stored[0]["error"] == "permission denied"


def test_acknowledging_twice_is_harmless(client: TestClient, enrolled, mtls_headers):
    """A device retrying a check-in whose response was lost must not be punished."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    command = enqueue(client, result["device_id"], "reboot")
    checkin(client, headers)

    report = [{"command_id": command["id"], "succeeded": True}]
    checkin(client, headers, results=report)
    body = checkin(client, headers, results=report)

    assert body["unknown_command_ids"] == []
    stored = client.get(f"/api/v1/devices/{result['device_id']}/commands").json()
    assert stored[0]["status"] == "succeeded"


def test_result_for_another_devices_command_is_rejected(
    client: TestClient, enrolled, mtls_headers
):
    """The command id alone must never be enough to select the row."""
    victim = enrolled(serial="VICTIM-1")
    attacker = enrolled(serial="ATTACKER-1")
    command = enqueue(client, victim["device_id"], "wipe")

    body = checkin(
        client,
        mtls_headers(attacker["certificate_pem"]),
        results=[{"command_id": command["id"], "succeeded": True}],
    )

    assert body["unknown_command_ids"] == [command["id"]]
    stored = client.get(f"/api/v1/devices/{victim['device_id']}/commands").json()
    assert stored[0]["status"] == "pending"


def test_expired_command_is_never_delivered(
    client: TestClient, enrolled, mtls_headers, db
):
    """A LOCATE from three weeks ago answers a question nobody is still asking."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    command = enqueue(client, result["device_id"], "locate")

    stored = db.get(DeviceCommand, uuid.UUID(command["id"]))
    stored.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    body = checkin(client, headers)

    assert body["commands"] == []
    listed = client.get(f"/api/v1/devices/{result['device_id']}/commands").json()
    assert listed[0]["status"] == "expired"


def test_command_gives_up_after_max_attempts(client: TestClient, enrolled, mtls_headers):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    enqueue(client, result["device_id"], "reboot", max_attempts=2)

    delivered = [len(checkin(client, headers)["commands"]) for _ in range(4)]

    assert delivered == [1, 1, 0, 0]
    listed = client.get(f"/api/v1/devices/{result['device_id']}/commands").json()
    assert listed[0]["status"] == "expired"
    assert "max attempts" in listed[0]["error"]


def test_ttl_defaults_differ_by_command_type(client: TestClient, enrolled):
    """A LOCATE goes stale in hours; a WIPE on a lost device stays worth doing."""
    result = enrolled()

    locate = enqueue(client, result["device_id"], "locate")
    wipe = enqueue(client, result["device_id"], "wipe")

    assert datetime.fromisoformat(locate["expires_at"]) < datetime.fromisoformat(
        wipe["expires_at"]
    )


def test_clear_app_data_requires_a_package(client: TestClient, enrolled):
    result = enrolled()

    response = client.post(
        f"/api/v1/devices/{result['device_id']}/commands",
        json={"command_type": "clear_app_data"},
    )

    assert response.status_code == 422


def test_cancelled_command_is_not_delivered(client: TestClient, enrolled, mtls_headers):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    command = enqueue(client, result["device_id"], "reboot")

    client.post(f"/api/v1/commands/{command['id']}/cancel")

    assert checkin(client, headers)["commands"] == []


def test_commands_are_delivered_in_creation_order(
    client: TestClient, enrolled, mtls_headers
):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    first = enqueue(client, result["device_id"], "lock")
    second = enqueue(client, result["device_id"], "reboot")

    body = checkin(client, headers)

    assert [c["id"] for c in body["commands"]] == [first["id"], second["id"]]


def test_admin_can_inspect_the_desired_state(client: TestClient, enrolled, signer):
    result = enrolled()
    policy = make_policy(client, "Baseline", 8)
    assign_to_device(client, policy["id"], result["device_id"])

    body = client.get(f"/api/v1/devices/{result['device_id']}/desired-state").json()

    assert body["desired_state"]["policy"]["PASSWORD"]["min_length"] == 8
    assert signer.verify(body["desired_state"], body["signature"]) is True
    assert body["compliance_status"] == "unknown"


def test_commands_require_mtls(client: TestClient, enrolled):
    result = enrolled()
    enqueue(client, result["device_id"], "reboot")

    assert client.post("/api/v1/device/checkin", json={}).status_code == 401
