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


def test_console_warns_that_it_is_unauthenticated(client: TestClient):
    """The warning is the only thing standing between this and an open console."""
    assert "No authentication on this console" in text_of(client.get("/").text)


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


def test_creating_a_token_shows_the_secret_once(client: TestClient):
    response = client.post(
        "/enrollment", data={"name": "Console token"}, follow_redirects=True
    )

    body = text_of(response.text)
    assert "only time the secret is shown" in body


def test_qr_is_withheld_without_a_signature_checksum(client: TestClient):
    """Matches the API's behaviour: no payload beats one that fails on the tablet."""
    response = client.post("/enrollment", data={"name": "No checksum"}, follow_redirects=True)

    assert "<svg" not in response.text
    assert "QR withheld" in text_of(response.text)


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


def test_token_scoping_from_the_form(client: TestClient):
    group = client.post("/api/v1/groups", json={"name": "Console Group"}).json()

    client.post(
        "/enrollment",
        data={"name": "Scoped", "group_ids": [group["id"]]},
        follow_redirects=True,
    )

    tokens = client.get("/api/v1/enrollment-tokens").json()
    assert any(t["name"] == "Scoped" and t["groups"] for t in tokens)
