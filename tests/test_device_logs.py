"""Diagnostic log upload, retention, and the COLLECT_LOGS command.

Copyright 2026 TAK-Solutions LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.services import device_logs as log_service


def upload(client: TestClient, headers: dict, **kwargs):
    body = {"content": "boot\nenrolled\n", **kwargs}
    return client.post("/api/v1/device/logs", json=body, headers=headers)


# --------------------------------------------------------------------------- #
# Upload
# --------------------------------------------------------------------------- #


def test_enrolled_device_can_upload_its_log(client: TestClient, enrolled, mtls_headers):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])

    response = upload(client, headers, agent_version="0.3.0")

    assert response.status_code == 201
    assert response.json()["size_bytes"] == len("boot\nenrolled\n")


def test_upload_requires_a_device_certificate(client: TestClient):
    # The device surface is mTLS-only. Without the proxy-forwarded certificate
    # there is no device to attribute the bundle to.
    assert client.post("/api/v1/device/logs", json={"content": "x"}).status_code == 401


def test_oversized_bundle_is_refused_with_413(client: TestClient, enrolled, mtls_headers):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])

    oversized = "x" * (log_service.MAX_BUNDLE_BYTES + 1)
    response = upload(client, headers, content=oversized)

    # 413 rather than 400, so the agent knows the bundle is too big rather than
    # malformed and stops retrying something it cannot shrink.
    assert response.status_code == 413
    assert str(log_service.MAX_BUNDLE_BYTES) in response.json()["detail"]


def test_size_is_measured_in_bytes_not_characters(
    client: TestClient, enrolled, mtls_headers
):
    # A multi-byte character counts once as a character and several times on disk.
    # Measuring length in characters would let a bundle several times the cap
    # through, which is exactly how a "capped" field stops being capped.
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])

    response = upload(client, headers, content="é" * 10)

    assert response.status_code == 201
    assert response.json()["size_bytes"] == 20


def test_truncation_flag_is_recorded(client: TestClient, enrolled, mtls_headers):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])

    upload(client, headers, truncated=True)

    bundles = client.get(f"/api/v1/devices/{result['device_id']}/logs").json()
    # Without this the reader cannot tell a short log from a log whose beginning
    # was thrown away, and the missing part is usually the interesting one.
    assert bundles[0]["truncated"] is True


# --------------------------------------------------------------------------- #
# Retention
# --------------------------------------------------------------------------- #


def test_history_is_capped_per_device(client: TestClient, enrolled, mtls_headers):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])

    for index in range(log_service.MAX_BUNDLES_PER_DEVICE + 5):
        upload(client, headers, content=f"capture {index}\n")

    bundles = client.get(f"/api/v1/devices/{result['device_id']}/logs").json()
    assert len(bundles) == log_service.MAX_BUNDLES_PER_DEVICE


def test_pruning_keeps_the_newest(client: TestClient, enrolled, mtls_headers):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])

    for index in range(log_service.MAX_BUNDLES_PER_DEVICE + 3):
        upload(client, headers, content=f"capture {index}\n")

    newest = client.get(f"/api/v1/devices/{result['device_id']}/logs").json()[0]
    body = client.get(
        f"/api/v1/devices/{result['device_id']}/logs/{newest['id']}"
    ).json()

    # Pruning the wrong end would silently discard the capture an operator just
    # asked for and leave them reading one from last week.
    last = log_service.MAX_BUNDLES_PER_DEVICE + 2
    assert body["content"] == f"capture {last}\n"


def test_one_device_history_does_not_evict_another(
    client: TestClient, enrolled, mtls_headers
):
    first = enrolled()
    second = enrolled("SM-X520-SECOND")
    first_headers = mtls_headers(first["certificate_pem"])
    second_headers = mtls_headers(second["certificate_pem"])

    upload(client, first_headers, content="from the first device\n")
    for index in range(log_service.MAX_BUNDLES_PER_DEVICE + 3):
        upload(client, second_headers, content=f"capture {index}\n")

    remaining = client.get(f"/api/v1/devices/{first['device_id']}/logs").json()
    # Pruning without scoping to the device would empty a quiet tablet's history
    # every time a noisy one uploaded.
    assert len(remaining) == 1


# --------------------------------------------------------------------------- #
# The COLLECT_LOGS command
# --------------------------------------------------------------------------- #


def test_collect_logs_can_be_enqueued_and_delivered(
    client: TestClient, enrolled, mtls_headers
):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])

    client.post(
        f"/api/v1/devices/{result['device_id']}/commands",
        json={"command_type": "collect_logs"},
    )
    response = client.post("/api/v1/device/checkin", json={}, headers=headers).json()

    assert [c["command_type"] for c in response["commands"]] == ["collect_logs"]


def test_uploaded_bundle_is_linked_to_the_command(
    client: TestClient, enrolled, mtls_headers
):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])

    client.post(
        f"/api/v1/devices/{result['device_id']}/commands",
        json={"command_type": "collect_logs"},
    )
    delivered = client.post("/api/v1/device/checkin", json={}, headers=headers).json()
    command_id = delivered["commands"][0]["id"]

    upload(client, headers, command_id=command_id)

    bundles = client.get(f"/api/v1/devices/{result['device_id']}/logs").json()
    # The link is what lets an operator see which request produced which capture,
    # rather than guessing from timestamps.
    assert bundles[0]["command_id"] == command_id


def test_deleting_a_command_keeps_its_log_bundle(
    client: TestClient, enrolled, mtls_headers, db
):
    from app.db.models import DeviceCommand

    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    client.post(
        f"/api/v1/devices/{result['device_id']}/commands",
        json={"command_type": "collect_logs"},
    )
    delivered = client.post("/api/v1/device/checkin", json={}, headers=headers).json()
    command_id = delivered["commands"][0]["id"]
    upload(client, headers, command_id=command_id)

    db.query(DeviceCommand).filter(DeviceCommand.id == uuid.UUID(command_id)).delete()
    db.commit()

    bundles = client.get(f"/api/v1/devices/{result['device_id']}/logs").json()
    # SET NULL, not CASCADE: the evidence must outlive the request for it, or
    # tidying the command queue would destroy the diagnosis.
    assert len(bundles) == 1
    assert bundles[0]["command_id"] is None
