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

"""Unassigning a policy from the device page (W118).

⚠️ **The load-bearing tests here are the refusals.** Removing a device-scoped
assignment is the easy half; the risk is a group or tag assignment being deleted
from a page that looks per-device, which would silently unassign the policy from
every device sharing it.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from fastapi.testclient import TestClient

from app.db.models import Assignment, Device, DeviceGroup
from tests.conftest import ADMIN_HEADERS


def _policy(client: TestClient, name: str = "removable") -> str:
    response = client.post(
        "/api/v1/policies",
        json={
            "name": name,
            "policy_type": "PASSWORD",
            "spec": {"min_length": 6},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _assign_device(client: TestClient, policy_id: str, device_id: str) -> str:
    response = client.post(
        "/api/v1/assignments",
        json={
            "policy_id": policy_id,
            "scope": "device",
            "target_id": device_id,
            "rank": 1,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _remove(client: TestClient, device_id: str, assignment_id: str):
    return client.post(
        f"/devices/{device_id}/assignments/{assignment_id}/remove",
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )


# --------------------------------------------------------------------------- #
# The happy path
# --------------------------------------------------------------------------- #


def test_a_device_assignment_can_be_removed(client: TestClient, db, enrolled):
    result = enrolled()
    assignment_id = _assign_device(client, _policy(client), result["device_id"])

    response = _remove(client, result["device_id"], assignment_id)

    assert response.status_code in (302, 303)
    assert db.get(Assignment, uuid.UUID(assignment_id)) is None


def test_removing_it_changes_what_reaches_the_device(
    client: TestClient, db, enrolled, mtls_headers
):
    """⚠️ The point of the button. A row disappearing from a table is not the
    same as the policy stopping — this asserts the desired state actually
    changes."""
    from tests.test_checkin import checkin

    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    assignment_id = _assign_device(client, _policy(client), result["device_id"])

    before = checkin(client, headers, force_full=True)["desired_state"]
    assert before["policy"].get("PASSWORD")

    _remove(client, result["device_id"], assignment_id)

    after = checkin(client, headers, force_full=True)["desired_state"]
    assert not after["policy"].get("PASSWORD")


def test_the_page_offers_the_button_for_a_device_assignment(
    client: TestClient, db, enrolled
):
    result = enrolled()
    assignment_id = _assign_device(client, _policy(client), result["device_id"])

    body = client.get(f"/devices/{result['device_id']}", headers=ADMIN_HEADERS).text

    assert f"/assignments/{assignment_id}/remove" in body


# --------------------------------------------------------------------------- #
# ⚠️ The refusals
# --------------------------------------------------------------------------- #


def test_a_group_assignment_is_refused_even_when_posted_directly(
    client: TestClient, db, enrolled
):
    """⚠️ The one that matters.

    The template hides the button, but a hidden button is not a control. Deleting
    a group assignment from here would unassign the policy from **every device in
    that group** — a fleet-wide change behind a per-device button.
    """
    result = enrolled()
    device = db.get(Device, uuid.UUID(result["device_id"]))
    group = DeviceGroup(name="Field Tablets")
    db.add(group)
    db.flush()
    device.groups.append(group)
    db.commit()

    created = client.post(
        "/api/v1/assignments",
        json={
            "policy_id": _policy(client, "group-wide"),
            "scope": "group",
            "target_id": str(group.id),
            "rank": 1,
        },
    )
    assignment_id = created.json()["id"]

    response = _remove(client, result["device_id"], assignment_id)

    assert response.status_code in (302, 303)
    assert "error=" in response.headers["location"]
    # ⚠️ Still there. The refusal has to be real, not just a message.
    assert db.get(Assignment, uuid.UUID(assignment_id)) is not None


def test_the_page_shows_where_an_inherited_policy_comes_from(
    client: TestClient, db, enrolled
):
    """An operator who cannot remove it here needs to know where to go."""
    result = enrolled()
    device = db.get(Device, uuid.UUID(result["device_id"]))
    group = DeviceGroup(name="Field Tablets")
    db.add(group)
    db.flush()
    device.groups.append(group)
    db.commit()
    client.post(
        "/api/v1/assignments",
        json={
            "policy_id": _policy(client, "group-wide"),
            "scope": "group",
            "target_id": str(group.id),
            "rank": 1,
        },
    )

    body = client.get(f"/devices/{result['device_id']}", headers=ADMIN_HEADERS).text

    assert "via group Field Tablets" in body


def test_a_profile_section_id_is_refused(client: TestClient, db, enrolled):
    """⚠️ Not an Assignment row at all — its id is the synthetic
    `profile:{pa.id}:{section.id}`, so there is nothing to delete and the route
    must not try to parse it as one."""
    result = enrolled()

    response = _remove(
        client, result["device_id"], f"profile:{uuid.uuid4()}:{uuid.uuid4()}"
    )

    assert response.status_code in (302, 303)
    assert "error=" in response.headers["location"]


def test_another_devices_assignment_is_refused(client: TestClient, db, enrolled):
    """⚠️ The id is a real device-scoped assignment — just not this device's.
    Without the target check, one device's page could unassign another's."""
    first = enrolled()
    second = enrolled(serial="OTHERDEVICE123")
    assignment_id = _assign_device(client, _policy(client), second["device_id"])

    response = _remove(client, first["device_id"], assignment_id)

    assert response.status_code in (302, 303)
    assert "error=" in response.headers["location"]
    assert db.get(Assignment, uuid.UUID(assignment_id)) is not None


def test_an_unknown_assignment_says_so_rather_than_500ing(
    client: TestClient, db, enrolled
):
    result = enrolled()

    response = _remove(client, result["device_id"], str(uuid.uuid4()))

    assert response.status_code in (302, 303)
    assert "error=" in response.headers["location"]
