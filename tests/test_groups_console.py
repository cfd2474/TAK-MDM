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

"""Creating device groups and editing membership from the console (W119).

The model and API for groups predate this by a long way; what was missing was
any way to reach them without curl. The tests that matter here are the ones
about **membership being a replace** and about a group assignment actually
reaching a device once it joins — a checkbox that ticks but changes nothing on
the tablet is the failure worth catching.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from fastapi.testclient import TestClient

from app.db.models import Device, DeviceGroup
from tests.conftest import ADMIN_HEADERS
from tests.test_checkin import checkin


def _create(client: TestClient, name: str, description: str = ""):
    return client.post(
        "/groups",
        data={"name": name, "description": description},
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )


def _set_members(client: TestClient, group_id, device_ids: list[str]):
    return client.post(
        f"/groups/{group_id}/devices",
        data={"device_ids": device_ids},
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )


def _group(db, name: str) -> DeviceGroup:
    return db.scalar(select(DeviceGroup).where(DeviceGroup.name == name))


# --------------------------------------------------------------------------- #
# Creating
# --------------------------------------------------------------------------- #


def test_a_group_can_be_created_from_the_console(client: TestClient, db):
    response = _create(client, "Field Tablets", "Everything that leaves the building")

    assert response.status_code in (302, 303)
    group = _group(db, "Field Tablets")
    assert group is not None
    assert group.description == "Everything that leaves the building"


def test_creating_lands_on_the_group_page(client: TestClient, db):
    """The operator's next step is adding devices, so send them there."""
    response = _create(client, "Field Tablets")

    group = _group(db, "Field Tablets")
    assert response.headers["location"] == f"/groups/{group.id}"


def test_a_duplicate_name_is_refused_rather_than_500ing(client: TestClient, db):
    """⚠️ `DeviceGroup.name` is unique, so without this check the second attempt
    is an IntegrityError and a 500 rather than a message."""
    _create(client, "Field Tablets")

    response = _create(client, "Field Tablets")

    assert response.status_code in (302, 303)
    assert "error=" in response.headers["location"]


def test_a_blank_name_is_refused(client: TestClient, db):
    response = _create(client, "   ")

    assert "error=" in response.headers["location"]
    assert db.scalar(select(DeviceGroup)) is None


def test_the_groups_page_lists_it_with_counts(client: TestClient, db, enrolled):
    result = enrolled()
    _create(client, "Field Tablets")
    group = _group(db, "Field Tablets")
    _set_members(client, group.id, [result["device_id"]])

    body = client.get("/groups", headers=ADMIN_HEADERS).text

    assert "Field Tablets" in body
    assert f"/groups/{group.id}" in body


def test_the_fleet_page_links_to_groups(client: TestClient):
    body = client.get("/fleet", headers=ADMIN_HEADERS).text

    assert 'href="/groups"' in body


# --------------------------------------------------------------------------- #
# ⚠️ Membership
# --------------------------------------------------------------------------- #


def test_membership_replaces_rather_than_appends(client: TestClient, db, enrolled):
    """⚠️ The endpoint sets the whole list, and the form is built to match.

    If this ever became append-only, unticking a device would silently do
    nothing and the page would keep showing it as a member.
    """
    first = enrolled()
    second = enrolled(serial="SECONDDEVICE1")
    _create(client, "Field Tablets")
    group = _group(db, "Field Tablets")

    _set_members(client, group.id, [first["device_id"], second["device_id"]])
    db.expire_all()
    assert len(_group(db, "Field Tablets").devices) == 2

    _set_members(client, group.id, [second["device_id"]])
    db.expire_all()

    members = _group(db, "Field Tablets").devices
    assert [str(d.id) for d in members] == [second["device_id"]]


def test_saving_with_nothing_ticked_empties_the_group(client: TestClient, db, enrolled):
    """The honest consequence of replace semantics, and worth pinning: an
    operator who unticks everything means it."""
    result = enrolled()
    _create(client, "Field Tablets")
    group = _group(db, "Field Tablets")
    _set_members(client, group.id, [result["device_id"]])

    _set_members(client, group.id, [])
    db.expire_all()

    assert _group(db, "Field Tablets").devices == []


def test_the_detail_page_ticks_current_members(client: TestClient, db, enrolled):
    result = enrolled()
    _create(client, "Field Tablets")
    group = _group(db, "Field Tablets")
    _set_members(client, group.id, [result["device_id"]])

    body = client.get(f"/groups/{group.id}", headers=ADMIN_HEADERS).text

    marker = f'value="{result["device_id"]}"'
    row = body[body.index(marker) : body.index(marker) + 200]
    assert "checked" in row


# --------------------------------------------------------------------------- #
# ⚠️ The point of a group
# --------------------------------------------------------------------------- #


def test_joining_a_group_brings_its_policies_to_the_device(
    client: TestClient, db, enrolled, mtls_headers
):
    """⚠️ The test that makes the feature real.

    A checkbox that ticks but changes nothing on the tablet is the failure worth
    catching — and it is exactly what W118 shipped an hour earlier by skipping
    cache invalidation. `_apply_membership` already invalidates both sides;
    this asserts it end to end rather than trusting that.
    """
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    _create(client, "Field Tablets")
    group = _group(db, "Field Tablets")

    policy = client.post(
        "/api/v1/policies",
        json={"name": "group pw", "policy_type": "PASSWORD", "spec": {"min_length": 8}},
    ).json()["id"]
    client.post(
        "/api/v1/assignments",
        json={"policy_id": policy, "scope": "group", "target_id": str(group.id), "rank": 1},
    )

    before = checkin(client, headers, force_full=True)["desired_state"]
    assert not before["policy"].get("PASSWORD")

    _set_members(client, group.id, [result["device_id"]])

    after = checkin(client, headers, force_full=True)["desired_state"]
    assert after["policy"].get("PASSWORD") == {"min_length": 8}


def test_leaving_a_group_takes_its_policies_away(
    client: TestClient, db, enrolled, mtls_headers
):
    """The other direction, which is the one that depends on invalidating the
    *previous* members rather than only the new ones."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    _create(client, "Field Tablets")
    group = _group(db, "Field Tablets")
    policy = client.post(
        "/api/v1/policies",
        json={"name": "group pw", "policy_type": "PASSWORD", "spec": {"min_length": 8}},
    ).json()["id"]
    client.post(
        "/api/v1/assignments",
        json={"policy_id": policy, "scope": "group", "target_id": str(group.id), "rank": 1},
    )
    _set_members(client, group.id, [result["device_id"]])
    assert checkin(client, headers, force_full=True)["desired_state"]["policy"].get("PASSWORD")

    _set_members(client, group.id, [])

    after = checkin(client, headers, force_full=True)["desired_state"]
    assert not after["policy"].get("PASSWORD")


def test_the_group_page_shows_what_it_assigns(client: TestClient, db, enrolled):
    """⚠️ Where W118 sends people. "via group Field Tablets" on a device page is
    only useful advice if the group has a page showing what it does."""
    _create(client, "Field Tablets")
    group = _group(db, "Field Tablets")
    client.post(
        "/api/v1/assignments",
        json={
            "policy_id": client.post(
                "/api/v1/policies",
                json={
                    "name": "group pw",
                    "policy_type": "PASSWORD",
                    "spec": {"min_length": 8},
                },
            ).json()["id"],
            "scope": "group",
            "target_id": str(group.id),
            "rank": 1,
        },
    )

    body = client.get(f"/groups/{group.id}", headers=ADMIN_HEADERS).text

    assert "group pw" in body
    assert "PASSWORD" in body


def test_an_unknown_group_is_a_404(client: TestClient):
    response = client.get(f"/groups/{uuid.uuid4()}", headers=ADMIN_HEADERS)

    assert response.status_code == 404
