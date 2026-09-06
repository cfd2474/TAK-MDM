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

"""Warnings are not failures (W50).

A policy naming an older build than the device already carries is a mismatch to
report, not a failure to converge — the newer build satisfies the requirement, and
Android refuses the downgrade regardless.

The assertion that matters most is the one about the **agent-update gate**: a
DEGRADED device is refused new agent builds, so filing this as an error would cut
a healthy device off from every future update over a version mismatch nobody
intends to act on. That is the deadlock W41 hit, reached from another direction.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import ComplianceStatus, Device
from app.services import agent_update


def _device(db) -> Device:
    device = db.scalar(select(Device))
    db.refresh(device)
    return device


def _checkin(client: TestClient, headers: dict, **body) -> None:
    body.setdefault("state_version", 1)
    body.setdefault("applied_state_version", 1)
    response = client.post("/api/v1/device/checkin", json=body, headers=headers)
    assert response.status_code == 200, response.text


def test_a_warning_alone_leaves_the_device_compliant(client, db, enrolled, mtls_headers):
    headers = mtls_headers(enrolled()["certificate_pem"])

    _checkin(
        client,
        headers,
        apply_warnings=["com.android.chrome: the device has versionCode 12, newer than 10"],
    )

    device = _device(db)
    assert device.compliance_status is ComplianceStatus.COMPLIANT
    assert device.compliance_detail is None
    assert "versionCode 12" in device.compliance_warnings


def test_a_warned_device_is_still_offered_agent_updates():
    """The reason warnings exist as their own tier at all.

    `decide` refuses a DEGRADED device, so a benign version mismatch filed as an
    error would silently stop that device receiving another agent build ever.
    """
    offered = agent_update.decide(
        target_version_code=60,
        device_version_code=59,
        compliance=ComplianceStatus.COMPLIANT,
        settled=True,
    )
    refused = agent_update.decide(
        target_version_code=60,
        device_version_code=59,
        compliance=ComplianceStatus.DEGRADED,
        settled=True,
    )

    assert offered.offer is True
    assert refused.offer is False


def test_errors_still_degrade(client, db, enrolled, mtls_headers):
    """Warnings must not have softened the real failure path."""
    headers = mtls_headers(enrolled()["certificate_pem"])

    _checkin(client, headers, apply_errors=["something genuinely broke"])

    device = _device(db)
    assert device.compliance_status is ComplianceStatus.DEGRADED
    assert "genuinely broke" in device.compliance_detail


def test_errors_and_warnings_are_kept_apart(client, db, enrolled, mtls_headers):
    headers = mtls_headers(enrolled()["certificate_pem"])

    _checkin(
        client,
        headers,
        apply_errors=["a real failure"],
        apply_warnings=["a version mismatch"],
    )

    device = _device(db)
    assert device.compliance_status is ComplianceStatus.DEGRADED
    assert device.compliance_detail == "a real failure"
    assert device.compliance_warnings == "a version mismatch"


def test_a_resolved_warning_stops_being_reported(client, db, enrolled, mtls_headers):
    """Warnings are rewritten on every report, so raising the policy to match the
    device clears the notice rather than leaving it to haunt the console."""
    headers = mtls_headers(enrolled()["certificate_pem"])

    _checkin(client, headers, apply_warnings=["a version mismatch"])
    assert _device(db).compliance_warnings is not None

    _checkin(client, headers, apply_warnings=[])
    assert _device(db).compliance_warnings is None


def test_an_empty_report_leaves_the_previous_verdict_alone(client, db, enrolled, mtls_headers):
    """A check-in carrying nothing is not a claim that all is well."""
    headers = mtls_headers(enrolled()["certificate_pem"])

    _checkin(client, headers, apply_warnings=["a version mismatch"])

    response = client.post("/api/v1/device/checkin", json={}, headers=headers)
    assert response.status_code == 200

    assert _device(db).compliance_warnings is not None
