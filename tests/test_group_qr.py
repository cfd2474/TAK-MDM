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

"""Choosing a group when generating the provisioning QR (W121).

⚠️ **The test that matters is the end-to-end one.** Everything else here could
pass while a tablet still enrolled ungrouped: the point of the feature is that
scanning the code puts the device in the group *and* gives it the group's
policies without a second step, so that is asserted against a real enrolment
and a real check-in rather than against the token's scoping.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select

from fastapi.testclient import TestClient

from app.db.models import Device, DeviceGroup, EnrollmentToken
from app.services import enrollment as enrollment_service
from tests.conftest import ADMIN_HEADERS, generate_csr
from tests.test_checkin import checkin


import pytest


@pytest.fixture(autouse=True)
def _qr_renderable(client, settings):
    """⚠️ Without `agent_signature_checksum` the QR payload raises and the whole
    block — pill, secret and all — is replaced by an error banner, so every
    assertion here would fail for a reason unrelated to what it tests.

    ⚠️ Depends on `client` deliberately. As a bare autouse fixture it ran
    *before* `client`, which then reset `dependency_overrides` and silently
    undid the override."""
    from app.api.deps import get_settings
    from app.main import app

    configured = settings.model_copy(update={"agent_signature_checksum": "abc123"})
    app.dependency_overrides[get_settings] = lambda: configured
    yield
    app.dependency_overrides[get_settings] = lambda: settings


def _group(client: TestClient, db, name: str = "Field Tablets") -> DeviceGroup:
    client.post("/groups", data={"name": name}, headers=ADMIN_HEADERS,
                follow_redirects=False)
    return db.scalar(select(DeviceGroup).where(DeviceGroup.name == name))


def _primary(client: TestClient) -> None:
    client.post("/enrollment/primary", data={"name": "Primary"},
                headers=ADMIN_HEADERS, follow_redirects=False)


def _qr(client: TestClient, group_id: str | None = None):
    data = {"wifi_ssid": "", "wifi_password": "", "wifi_security": "WPA"}
    if group_id:
        data["group_id"] = group_id
    return client.post("/enrollment/qr", data=data, headers=ADMIN_HEADERS)


def _secret_from(html: str) -> str:
    """The page renders the secret inside a <pre> under a disclosure."""
    match = re.search(r"QR secret[^<]*</summary>\s*<pre[^>]*>([^<]+)</pre>", html)
    assert match, "no QR secret rendered on the page"
    return match.group(1).strip()


def _enroll_with(client: TestClient, secret: str, serial: str = "QRGROUP001") -> dict:
    response = client.post(
        "/api/v1/enroll",
        json={
            "token": secret,
            "csr_pem": generate_csr(),
            "serial_number": serial,
            "model": "SM-X828U",
            "os_version": "16",
        },
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


# --------------------------------------------------------------------------- #
# ⚠️ End to end
# --------------------------------------------------------------------------- #


def test_a_group_qr_enrols_the_device_into_the_group_with_its_policies(
    client: TestClient, db, mtls_headers
):
    """⚠️ The whole feature in one test.

    Scanning the code has to put the tablet in the group *and* deliver the
    group's policy stack on the first check-in. Asserting the token's scoping
    would pass while the device still landed ungrouped.
    """
    _primary(client)
    group = _group(client, db)
    policy = client.post(
        "/api/v1/policies",
        json={"name": "field pw", "policy_type": "PASSWORD", "spec": {"min_length": 9}},
    ).json()["id"]
    client.post(
        "/api/v1/assignments",
        json={"policy_id": policy, "scope": "group", "target_id": str(group.id), "rank": 1},
    )

    secret = _secret_from(_qr(client, str(group.id)).text)
    enrolled = _enroll_with(client, secret)

    device = db.get(Device, uuid.UUID(enrolled["device_id"]))
    assert [g.name for g in device.groups] == ["Field Tablets"]

    state = checkin(
        client, mtls_headers(enrolled["certificate_pem"]), force_full=True
    )["desired_state"]
    assert state["policy"].get("PASSWORD") == {"min_length": 9}


def test_no_group_selected_enrols_ungrouped_as_before(client: TestClient, db):
    """⚠️ The existing path must be untouched. A sticky or defaulted selection
    would be worse than no feature — a QR that quietly enrols into a group the
    operator forgot they picked."""
    _primary(client)
    _group(client, db)

    secret = _secret_from(_qr(client).text)
    enrolled = _enroll_with(client, secret)

    device = db.get(Device, uuid.UUID(enrolled["device_id"]))
    assert device.groups == []


# --------------------------------------------------------------------------- #
# The token behind it
# --------------------------------------------------------------------------- #


def test_the_group_token_is_reused_not_multiplied(client: TestClient, db):
    """One standing token per group, not one per QR — otherwise every code
    printed leaves another row to revoke separately."""
    _primary(client)
    group = _group(client, db)

    for _ in range(3):
        _qr(client, str(group.id))

    tokens = list(
        db.scalars(
            select(EnrollmentToken).where(
                EnrollmentToken.name == f"{enrollment_service.GROUP_TOKEN_PREFIX}Field Tablets"
            )
        )
    )
    assert len(tokens) == 1


def test_the_group_token_is_not_a_primary(client: TestClient, db):
    """⚠️ Only one live primary is allowed by a partial unique index, and the
    plain QR button must keep resolving to the real primary rather than to
    whichever group token was made last."""
    _primary(client)
    group = _group(client, db)
    _qr(client, str(group.id))

    token = db.scalar(
        select(EnrollmentToken).where(
            EnrollmentToken.name == f"{enrollment_service.GROUP_TOKEN_PREFIX}Field Tablets"
        )
    )
    assert token.is_primary is False
    assert enrollment_service.get_primary_token(db).name == "Primary"


def test_the_group_token_is_rescoped_rather_than_trusted(client: TestClient, db):
    """⚠️ A QR is a picture that says nothing about what it does, so the scoping
    is re-asserted on every use. Edited by hand, it would otherwise keep
    enrolling into the wrong place."""
    _primary(client)
    group = _group(client, db)
    other = _group(client, db, "Depot")
    _qr(client, str(group.id))

    token = db.scalar(
        select(EnrollmentToken).where(
            EnrollmentToken.name == f"{enrollment_service.GROUP_TOKEN_PREFIX}Field Tablets"
        )
    )
    token.groups = [other]
    db.commit()

    _qr(client, str(group.id))
    db.expire_all()

    token = db.scalar(
        select(EnrollmentToken).where(
            EnrollmentToken.name == f"{enrollment_service.GROUP_TOKEN_PREFIX}Field Tablets"
        )
    )
    assert [g.name for g in token.groups] == ["Field Tablets"]


# --------------------------------------------------------------------------- #
# The page
# --------------------------------------------------------------------------- #


def test_the_page_names_the_group_beside_the_code(client: TestClient, db):
    """⚠️ The QR itself is opaque. Without this an operator cannot tell two
    codes apart, and enrolling a shipment into the wrong group is silent."""
    _primary(client)
    group = _group(client, db)

    body = _qr(client, str(group.id)).text

    assert "Enrols into group: Field Tablets" in body


def test_the_page_says_plainly_when_no_group_is_attached(client: TestClient, db):
    _primary(client)
    _group(client, db)

    body = _qr(client).text

    assert "No group" in body


def test_the_enroll_page_offers_the_groups(client: TestClient, db):
    _primary(client)
    _group(client, db)

    body = client.get("/enrollment", headers=ADMIN_HEADERS).text

    assert 'name="group_id"' in body
    assert "Field Tablets" in body
