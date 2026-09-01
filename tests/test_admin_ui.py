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

"""Admin console: rendering, form handling, and the stacking view."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient


def text_of(html: str) -> str:
    """Strip tags so assertions test what an operator reads, not the markup."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def create_policy(client: TestClient, name: str, policy_type: str, spec: str) -> str:
    response = client.post(
        "/policies",
        data={"name": name, "policy_type": policy_type, "spec": spec},
        follow_redirects=True,
    )
    assert response.status_code == 200, response.text
    return response.url.path.rsplit("/", 1)[-1]


# --------------------------------------------------------------------------- #
# Chassis
# --------------------------------------------------------------------------- #


def test_dashboard_renders_with_no_devices(client: TestClient):
    response = client.get("/")

    assert response.status_code == 200
    assert "No devices yet" in text_of(response.text)


def test_console_warns_when_auth_is_disabled(client: TestClient):
    """With auth off, the banner is the only thing flagging an open console."""
    body = text_of(client.get("/").text)

    assert "Admin authentication is disabled" in body
    assert "not signed in" in body


def test_admin_routes_are_absent_from_the_api_schema(client: TestClient):
    """They are a human surface; listing them as API would invite exposing them."""
    paths = client.get("/openapi.json").json()["paths"]

    assert "/policies" not in paths
    assert "/enrollment" not in paths
    assert "/api/v1/policies" in paths


def test_dashboard_lists_an_enrolled_device(client: TestClient, enrolled):
    enrolled(serial="R5CN00TAK99")

    assert "R5CN00TAK99" in client.get("/").text


# --------------------------------------------------------------------------- #
# Policy editor
# --------------------------------------------------------------------------- #


def test_create_policy_through_the_form(client: TestClient):
    policy_id = create_policy(client, "Console PW", "PASSWORD", '{"min_length": 11}')

    body = client.get(f"/policies/{policy_id}").text
    assert "Console PW" in body
    assert "min_length" in body


def test_invalid_spec_is_reported_not_swallowed(client: TestClient):
    response = client.post(
        "/policies",
        data={"name": "Bad", "policy_type": "PASSWORD", "spec": '{"min_length": 999}'},
        follow_redirects=True,
    )

    assert "error" in response.url.query.decode()
    assert client.get("/policies").text.count("Bad") == 0


def test_malformed_json_is_reported(client: TestClient):
    response = client.post(
        "/policies",
        data={"name": "Bad JSON", "policy_type": "PASSWORD", "spec": "{not json"},
        follow_redirects=True,
    )

    assert "error" in response.url.query.decode()


def test_duplicate_name_is_reported(client: TestClient):
    create_policy(client, "Dupe", "PASSWORD", '{"min_length": 8}')

    response = client.post(
        "/policies",
        data={"name": "Dupe", "policy_type": "PASSWORD", "spec": '{"min_length": 8}'},
        follow_redirects=True,
    )

    # Assert on the rendered page rather than the query string: that is what the
    # operator actually reads, and it is not URL-encoded.
    assert "already exists" in text_of(response.text)


def test_publishing_a_version_keeps_the_previous_one(client: TestClient):
    policy_id = create_policy(client, "Versioned", "PASSWORD", '{"min_length": 6}')

    client.post(
        f"/policies/{policy_id}/versions",
        data={"spec": '{"min_length": 14}'},
        follow_redirects=True,
    )

    body = text_of(client.get(f"/policies/{policy_id}").text)
    assert "v2" in body and "v1" in body


def test_policy_page_shows_merge_strategies(client: TestClient):
    """The reference an operator needs to predict how stacking will behave."""
    policy_id = create_policy(client, "Apps", "APP_CATALOG", "{}")

    body = client.get(f"/policies/{policy_id}").text
    assert "merge_by_key" in body
    assert "intersect" in body


# --------------------------------------------------------------------------- #
# Bulk assignment (F2)
# --------------------------------------------------------------------------- #


def test_assign_one_policy_to_several_devices(client: TestClient, enrolled):
    devices = [enrolled(serial=f"UI-BULK-{i}") for i in range(3)]
    policy_id = create_policy(client, "Fleet PW", "PASSWORD", '{"min_length": 9}')

    response = client.post(
        f"/policies/{policy_id}/targets",
        data={"rank": "40", "device_ids": [d["device_id"] for d in devices]},
        follow_redirects=True,
    )

    assert response.status_code == 200
    for device in devices:
        state = client.get(
            f"/api/v1/devices/{device['device_id']}/effective-policy"
        ).json()
        assert state["values"]["PASSWORD"]["min_length"] == 9


def test_unticking_a_device_removes_the_assignment(client: TestClient, enrolled):
    """The form describes the complete target set, so removal happens here too."""
    keep = enrolled(serial="UI-KEEP")
    drop = enrolled(serial="UI-DROP")
    policy_id = create_policy(client, "Fleet PW", "PASSWORD", '{"min_length": 9}')

    client.post(
        f"/policies/{policy_id}/targets",
        data={"rank": "10", "device_ids": [keep["device_id"], drop["device_id"]]},
        follow_redirects=True,
    )
    client.post(
        f"/policies/{policy_id}/targets",
        data={"rank": "10", "device_ids": [keep["device_id"]]},
        follow_redirects=True,
    )

    assert client.get(
        f"/api/v1/devices/{drop['device_id']}/effective-policy"
    ).json()["values"] == {}
    assert client.get(
        f"/api/v1/devices/{keep['device_id']}/effective-policy"
    ).json()["values"]["PASSWORD"]["min_length"] == 9


def test_assignment_checkboxes_reflect_current_state(client: TestClient, enrolled):
    device = enrolled(serial="UI-CHECKED")
    policy_id = create_policy(client, "Fleet PW", "PASSWORD", '{"min_length": 9}')
    client.post(
        f"/policies/{policy_id}/targets",
        data={"rank": "10", "device_ids": [device["device_id"]]},
        follow_redirects=True,
    )

    body = client.get(f"/policies/{policy_id}").text
    marker = f'value="{device["device_id"]}"'
    assert marker in body
    assert "checked" in body[body.index(marker) : body.index(marker) + 120]


# --------------------------------------------------------------------------- #
# Stacking view
# --------------------------------------------------------------------------- #


def test_device_page_explains_where_a_value_came_from(client: TestClient, enrolled, assign):
    device = enrolled(serial="UI-PROV")
    weak = create_policy(client, "Convenience", "PASSWORD", '{"min_length": 4}')
    strong = create_policy(client, "Hardened", "PASSWORD", '{"min_length": 12}')
    assign(weak, device["device_id"], rank=99)
    assign(strong, device["device_id"], rank=1)

    body = text_of(client.get(f"/devices/{device['device_id']}").text)

    assert "min_length" in body
    assert "Hardened" in body          # the winning source is named
    assert "max" in body                # the strategy that decided it
    assert "Convenience" in body        # and what it beat


def test_device_page_lists_policies_in_resolution_order(client: TestClient, enrolled, assign):
    device = enrolled(serial="UI-ORDER")
    low = create_policy(client, "Low Rank", "PASSWORD", '{"min_length": 4}')
    high = create_policy(client, "High Rank", "PASSWORD", '{"min_length": 6}')
    assign(low, device["device_id"], rank=1)
    assign(high, device["device_id"], rank=99)

    body = client.get(f"/devices/{device['device_id']}").text

    assert body.index("High Rank") < body.index("Low Rank")


def test_device_page_surfaces_conflicts(client: TestClient, enrolled, assign):
    device = enrolled(serial="UI-CONFLICT")
    first = create_policy(client, "Field Kiosk", "APP_CATALOG", '{"kiosk_package": "com.atakmap.app"}')
    second = create_policy(client, "Warehouse", "APP_CATALOG", '{"kiosk_package": "com.scanner"}')
    assign(first, device["device_id"], rank=50)
    assign(second, device["device_id"], rank=10)

    body = text_of(client.get(f"/devices/{device['device_id']}").text)

    assert "conflict" in body.lower()
    assert "com.scanner" in body


def test_unknown_device_is_404(client: TestClient):
    assert client.get("/devices/00000000-0000-0000-0000-000000000000").status_code == 404


# --------------------------------------------------------------------------- #
# Enrollment and QR
# --------------------------------------------------------------------------- #


def test_enrollment_page_renders(client: TestClient):
    assert client.get("/enrollment").status_code == 200


def test_creating_a_token_lands_on_its_qr_page(client: TestClient):
    """One place renders QR codes, so there is no 'you should have saved it' path."""
    response = client.post(
        "/enrollment", data={"name": "Console token"}, follow_redirects=True
    )

    assert response.url.path.endswith("/qr")
    assert "Console token" in response.text


def test_qr_is_withheld_without_a_signature_checksum(client: TestClient):
    """Matches the API's behaviour: no payload beats one that fails on the tablet."""
    response = client.post("/enrollment", data={"name": "No checksum"}, follow_redirects=True)

    assert "<svg" not in response.text
    assert "agent_signature_checksum is not configured" in text_of(response.text)


def test_qr_renders_when_a_checksum_is_configured(client: TestClient, settings):
    from app.api.deps import get_settings
    from app.main import app

    configured = settings.model_copy(update={"agent_signature_checksum": "abc123"})
    app.dependency_overrides[get_settings] = lambda: configured
    try:
        response = client.post(
            "/enrollment", data={"name": "With checksum"}, follow_redirects=True
        )
        assert "<svg" in response.text
        assert "factory-reset" in text_of(response.text)
    finally:
        app.dependency_overrides[get_settings] = lambda: settings


def configured_checksum(client: TestClient, settings):
    """Enable QR rendering for a test by supplying a signature checksum."""
    from app.api.deps import get_settings
    from app.main import app

    configured = settings.model_copy(update={"agent_signature_checksum": "abc123"})
    app.dependency_overrides[get_settings] = lambda: configured
    return lambda: app.dependency_overrides.__setitem__(get_settings, lambda: settings)


def test_a_past_tokens_qr_can_be_shown_again(client: TestClient, settings):
    """The point of sealing secrets: an old token is still scannable tomorrow."""
    restore = configured_checksum(client, settings)
    try:
        created = client.post(
            "/enrollment", data={"name": "Reusable"}, follow_redirects=True
        )
        token_id = created.url.path.split("/")[-2]

        # Come back later, as a fresh page load rather than the creation response.
        again = client.get(f"/enrollment/{token_id}/qr")

        assert again.status_code == 200
        assert "<svg" in again.text
    finally:
        restore()


def test_token_list_links_to_the_qr(client: TestClient):
    client.post("/enrollment", data={"name": "Listed"}, follow_redirects=True)

    assert "Show QR" in client.get("/enrollment").text


def test_wifi_credentials_are_embedded_when_supplied(client: TestClient, settings):
    restore = configured_checksum(client, settings)
    try:
        created = client.post(
            "/enrollment", data={"name": "Wifi"}, follow_redirects=True
        )
        token_id = created.url.path.split("/")[-2]

        response = client.post(
            f"/enrollment/{token_id}/qr",
            data={
                "wifi_ssid": "TAK-Field",
                "wifi_password": "hunter2",
                "wifi_security": "WPA",
            },
        )

        body = response.text
        assert "PROVISIONING_WIFI_SSID" in body
        assert "TAK-Field" in body
        assert "Wi-Fi embedded" in text_of(body)
    finally:
        restore()


def test_wifi_password_is_not_persisted(client: TestClient, settings, db):
    """It is used for one render; storing it would be a second recoverable secret."""
    from sqlalchemy import select

    from app.db.models import EnrollmentToken

    restore = configured_checksum(client, settings)
    try:
        created = client.post("/enrollment", data={"name": "Wifi"}, follow_redirects=True)
        token_id = created.url.path.split("/")[-2]
        client.post(
            f"/enrollment/{token_id}/qr",
            data={"wifi_ssid": "TAK-Field", "wifi_password": "hunter2"},
        )

        token = db.scalars(select(EnrollmentToken)).one()
        assert "hunter2" not in str(token.__dict__)

        # And a later render does not silently carry it forward.
        assert "hunter2" not in client.get(f"/enrollment/{token_id}/qr").text
    finally:
        restore()


def test_qr_refuses_a_revoked_token(client: TestClient, settings):
    """A scannable code that cannot enrol costs someone a factory reset."""
    restore = configured_checksum(client, settings)
    try:
        created = client.post("/enrollment", data={"name": "Doomed"}, follow_redirects=True)
        token_id = created.url.path.split("/")[-2]
        client.post(f"/api/v1/enrollment-tokens/{token_id}/revoke")

        response = client.get(f"/enrollment/{token_id}/qr")

        assert "<svg" not in response.text
        assert "revoked" in text_of(response.text)
    finally:
        restore()


def test_qr_refuses_a_used_up_token(client: TestClient, settings, db):
    from sqlalchemy import select

    from app.db.models import EnrollmentToken

    restore = configured_checksum(client, settings)
    try:
        created = client.post(
            "/enrollment", data={"name": "One shot", "max_uses": "1"}, follow_redirects=True
        )
        token_id = created.url.path.split("/")[-2]
        assert "<svg" in client.get(f"/enrollment/{token_id}/qr").text

        token = db.scalars(
            select(EnrollmentToken).where(EnrollmentToken.name == "One shot")
        ).one()
        token.use_count = 1
        db.commit()

        response = client.get(f"/enrollment/{token_id}/qr")

        assert "<svg" not in response.text
        assert "used all 1 time" in text_of(response.text)
    finally:
        restore()


def test_qr_refuses_an_expired_token(client: TestClient, settings, db):
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from app.db.models import EnrollmentToken

    restore = configured_checksum(client, settings)
    try:
        created = client.post("/enrollment", data={"name": "Stale"}, follow_redirects=True)
        token_id = created.url.path.split("/")[-2]

        token = db.scalars(
            select(EnrollmentToken).where(EnrollmentToken.name == "Stale")
        ).one()
        token.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()

        response = client.get(f"/enrollment/{token_id}/qr")

        assert "<svg" not in response.text
        assert "expired" in text_of(response.text)
    finally:
        restore()


def test_unknown_token_qr_is_404(client: TestClient):
    assert client.get(
        "/enrollment/00000000-0000-0000-0000-000000000000/qr"
    ).status_code == 404


def test_token_scoping_from_the_form(client: TestClient):
    group = client.post("/api/v1/groups", json={"name": "Console Group"}).json()

    client.post(
        "/enrollment",
        data={"name": "Scoped", "group_ids": [group["id"]]},
        follow_redirects=True,
    )

    tokens = client.get("/api/v1/enrollment-tokens").json()
    assert any(t["name"] == "Scoped" and t["groups"] for t in tokens)


# --------------------------------------------------------------------------- #
# Diagnostics
# --------------------------------------------------------------------------- #


def test_device_page_offers_log_collection(client: TestClient, enrolled):
    device = enrolled(serial="UI-LOGS")

    body = client.get(f"/devices/{device['device_id']}").text

    assert "Collect logs" in body
    assert f"/devices/{device['device_id']}/collect-logs" in body


def test_device_page_says_when_no_logs_exist(client: TestClient, enrolled):
    device = enrolled(serial="UI-NOLOGS")

    body = text_of(client.get(f"/devices/{device['device_id']}").text)

    # An empty table with no explanation reads like a broken page.
    assert "No logs collected" in body


def test_collect_logs_button_queues_a_command(client: TestClient, enrolled):
    device = enrolled(serial="UI-QUEUE")

    client.post(
        f"/devices/{device['device_id']}/collect-logs", follow_redirects=False
    )

    commands = client.get(f"/api/v1/devices/{device['device_id']}/commands").json()
    assert [c["command_type"] for c in commands] == ["collect_logs"]


def test_page_shows_a_request_is_already_in_flight(client: TestClient, enrolled):
    device = enrolled(serial="UI-INFLIGHT")
    client.post(f"/devices/{device['device_id']}/collect-logs", follow_redirects=False)

    body = text_of(client.get(f"/devices/{device['device_id']}").text)

    # Without this an operator who sees nothing happen queues another, and another.
    assert "already in flight" in body


def test_an_uploaded_log_is_listed_and_readable(
    client: TestClient, enrolled, mtls_headers
):
    device = enrolled(serial="UI-READ")
    headers = mtls_headers(device["certificate_pem"])
    client.post(
        "/api/v1/device/logs",
        json={"content": "E/Reconciler: install failed\n", "agent_version": "0.3.0"},
        headers=headers,
    )

    listing = client.get(f"/devices/{device['device_id']}").text
    assert "0.3.0" in listing

    bundle_id = client.get(f"/api/v1/devices/{device['device_id']}/logs").json()[0]["id"]
    body = client.get(f"/devices/{device['device_id']}/logs/{bundle_id}").text
    assert "install failed" in body


def test_a_log_cannot_be_read_through_another_device(
    client: TestClient, enrolled, mtls_headers
):
    owner = enrolled(serial="UI-OWNER")
    other = enrolled(serial="UI-OTHER")
    client.post(
        "/api/v1/device/logs",
        json={"content": "private\n"},
        headers=mtls_headers(owner["certificate_pem"]),
    )
    bundle_id = client.get(f"/api/v1/devices/{owner['device_id']}/logs").json()[0]["id"]

    # Scoped to the device as well as the id, so a guessed id reveals nothing
    # (the same rule as D34).
    response = client.get(f"/devices/{other['device_id']}/logs/{bundle_id}")
    assert response.status_code == 404


def test_device_page_lists_identifiers(client: TestClient, enrolled):
    device = enrolled(serial="UI-IDENT")

    body = text_of(client.get(f"/devices/{device['device_id']}").text)

    assert "Identity" in body
    assert "UI-IDENT" in body


def test_device_page_warns_when_there_is_no_hardware_serial(client: TestClient):
    from tests.conftest import ADMIN_HEADERS, generate_csr

    secret = client.post(
        "/api/v1/enrollment-tokens", json={"name": "weak"}, headers=ADMIN_HEADERS
    ).json()["secret"]
    device = client.post(
        "/api/v1/enroll",
        json={
            "token": secret,
            "csr_pem": generate_csr(),
            "serial_number": "SM-X520-deadbeefdeadbeef",
            "identifiers": [
                {"kind": "android_id", "value": "SM-X520-deadbeefdeadbeef"}
            ],
        },
    ).json()

    body = text_of(client.get(f"/devices/{device['device_id']}").text)

    # A device one wipe away from becoming a duplicate is invisible from anything
    # else on the page, so it has to be said outright.
    assert "No hardware serial" in body
