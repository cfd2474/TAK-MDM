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

"""Admin authentication via Authentik forward auth.

The boundary these tests describe is the whole of the console's protection, so they
check both directions: that admin routes refuse the unauthenticated, and that the
device surface is not caught in the same net.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.security.admin_auth import AuthMode

ADMIN_PATHS = [
    "/",
    "/policies",
    # Reads the app library to answer what an ATAK build declares (W90).
    "/policies/pref-schema",
    "/enrollment",
    "/api/v1/devices",
    "/api/v1/policies",
    "/api/v1/policy-types",
    "/api/v1/enrollment-tokens",
    "/api/v1/packages",
    "/api/v1/files",
]


@pytest.fixture
def protected(client: TestClient, settings: Settings):
    """Switch the running app into forward-auth mode for one test."""
    secured = settings.model_copy(update={"admin_auth_mode": AuthMode.FORWARD_AUTH.value})
    app.dependency_overrides[get_settings] = lambda: secured
    yield client
    app.dependency_overrides[get_settings] = lambda: settings


def as_admin(groups: str = "takmdm-admins") -> dict[str, str]:
    return {"x-authentik-username": "mleckliter", "x-authentik-groups": groups}


# --------------------------------------------------------------------------- #
# Refusal
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("path", ADMIN_PATHS)
def test_admin_routes_refuse_unauthenticated_requests(protected: TestClient, path: str):
    """Fail closed: a missing header means the proxy did not authenticate this."""
    assert protected.get(path).status_code == 401


def test_authenticated_but_wrong_group_is_forbidden(protected: TestClient):
    response = protected.get("/api/v1/devices", headers=as_admin(groups="everyone|staff"))

    assert response.status_code == 403
    assert "takmdm-admins" in response.json()["detail"]


def test_no_groups_at_all_is_forbidden(protected: TestClient):
    response = protected.get(
        "/api/v1/devices", headers={"x-authentik-username": "someone"}
    )
    assert response.status_code == 403


def test_writes_are_refused_too(protected: TestClient):
    """A read-only guard would leave the dangerous half of the API open."""
    response = protected.post(
        "/api/v1/policies",
        json={"name": "Sneaky", "policy_type": "PASSWORD", "spec": {"min_length": 4}},
    )
    assert response.status_code == 401


# --------------------------------------------------------------------------- #
# Admission
# --------------------------------------------------------------------------- #


def test_admin_group_member_is_admitted(protected: TestClient):
    assert protected.get("/api/v1/devices", headers=as_admin()).status_code == 200


def test_console_renders_for_an_admin(protected: TestClient):
    response = protected.get("/", headers=as_admin())

    assert response.status_code == 200
    assert "mleckliter" in response.text
    # The "auth disabled" warning must disappear once auth is on, or it trains
    # operators to ignore it.
    assert "Admin authentication is disabled" not in response.text


def test_comma_separated_groups_are_accepted(protected: TestClient):
    """Authentik joins with '|' by default, but commas are a common configuration."""
    response = protected.get(
        "/api/v1/devices", headers=as_admin(groups="staff, takmdm-admins")
    )
    assert response.status_code == 200


def test_blank_required_group_admits_any_authenticated_user(
    client: TestClient, settings: Settings
):
    """For deployments where Authentik itself restricts who reaches the app."""
    secured = settings.model_copy(
        update={"admin_auth_mode": AuthMode.FORWARD_AUTH.value, "admin_group": ""}
    )
    app.dependency_overrides[get_settings] = lambda: secured
    try:
        response = client.get(
            "/api/v1/devices", headers={"x-authentik-username": "anyone"}
        )
        assert response.status_code == 200
    finally:
        app.dependency_overrides[get_settings] = lambda: settings


# --------------------------------------------------------------------------- #
# The device surface must not be caught by the admin guard
# --------------------------------------------------------------------------- #


def test_enrollment_stays_open_to_devices(protected: TestClient):
    """A tablet in its setup wizard cannot perform an interactive login."""
    response = protected.post(
        "/api/v1/enroll",
        json={"token": "bogus", "csr_pem": "x", "serial_number": "S1"},
    )

    # 401 for a bad *token*, not for a missing admin header — the request reached
    # the endpoint. Anything else would mean devices can no longer enrol.
    assert response.status_code == 401
    assert "enrollment token" in response.json()["detail"]


def test_agent_apk_stays_open(protected: TestClient):
    response = protected.get("/api/v1/provisioning/agent.apk")

    # 404 because no agent is uploaded in this test database — but it was reached.
    assert response.status_code == 404
    assert "admin" not in response.json()["detail"].lower()


def test_device_checkin_is_governed_by_mtls_not_admin_auth(protected: TestClient):
    response = protected.post("/api/v1/device/checkin", json={})

    assert response.status_code == 401
    assert "client certificate" in response.json()["detail"]


def test_enrolled_device_can_still_check_in(protected: TestClient, enrolled, mtls_headers):
    """The end-to-end proof that turning on admin auth did not break the fleet."""
    device = enrolled()

    response = protected.post(
        "/api/v1/device/checkin", json={}, headers=mtls_headers(device["certificate_pem"])
    )
    assert response.status_code == 200


def test_healthz_stays_open(protected: TestClient):
    assert protected.get("/healthz").status_code == 200


# --------------------------------------------------------------------------- #
# Attribution
# --------------------------------------------------------------------------- #


def test_policy_version_records_its_author(protected: TestClient):
    policy = protected.post(
        "/api/v1/policies",
        json={"name": "Attributed", "policy_type": "PASSWORD", "spec": {"min_length": 8}},
        headers=as_admin(),
    ).json()

    protected.post(
        f"/api/v1/policies/{policy['id']}/versions",
        json={"spec": {"min_length": 12}},
        headers=as_admin(),
    )

    versions = protected.get(
        f"/api/v1/policies/{policy['id']}", headers=as_admin()
    ).json()["versions"]
    assert versions[-1]["published_by"] == "mleckliter"


def test_enrollment_token_records_who_minted_it(protected: TestClient, db):
    from sqlalchemy import select

    from app.db.models import EnrollmentToken

    protected.post(
        "/api/v1/enrollment-tokens", json={"name": "Attributed"}, headers=as_admin()
    )

    token = db.scalars(select(EnrollmentToken)).one()
    assert token.created_by == "mleckliter"


def test_attribution_is_null_when_auth_is_disabled(client: TestClient, db):
    """Better an honest gap in the audit trail than a fabricated author."""
    from sqlalchemy import select

    from app.db.models import EnrollmentToken

    client.post("/api/v1/enrollment-tokens", json={"name": "Anonymous"})

    assert db.scalars(select(EnrollmentToken)).one().created_by is None
