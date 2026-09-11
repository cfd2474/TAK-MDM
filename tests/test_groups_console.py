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


# --------------------------------------------------------------------------- #
# Assignments, from the group's own page (W120)
# --------------------------------------------------------------------------- #


def _make_policy(client: TestClient, name: str = "group pw") -> str:
    return client.post(
        "/api/v1/policies",
        json={"name": name, "policy_type": "PASSWORD", "spec": {"min_length": 8}},
    ).json()["id"]


def _assign(client: TestClient, group_id, policy_id: str, rank: int = 0):
    return client.post(
        f"/groups/{group_id}/assignments",
        data={"policy_id": policy_id, "rank": rank},
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )


def test_assigning_from_the_group_page_reaches_its_members(
    client: TestClient, db, enrolled, mtls_headers
):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    _create(client, "Field Tablets")
    group = _group(db, "Field Tablets")
    _set_members(client, group.id, [result["device_id"]])

    _assign(client, group.id, _make_policy(client))

    after = checkin(client, headers, force_full=True)["desired_state"]
    assert after["policy"].get("PASSWORD") == {"min_length": 8}


def test_removing_an_assignment_here_is_allowed_and_takes_effect(
    client: TestClient, db, enrolled, mtls_headers
):
    """⚠️ Refused on the device page (W118), correct here.

    The click changes every member either way; the difference is whether the
    page the operator is looking at makes that obvious.
    """
    from app.db.models import Assignment

    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    _create(client, "Field Tablets")
    group = _group(db, "Field Tablets")
    _set_members(client, group.id, [result["device_id"]])
    _assign(client, group.id, _make_policy(client))
    assignment = db.scalar(select(Assignment).where(Assignment.group_id == group.id))

    client.post(
        f"/groups/{group.id}/assignments/{assignment.id}/remove",
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )

    after = checkin(client, headers, force_full=True)["desired_state"]
    assert not after["policy"].get("PASSWORD")


def test_an_assignment_from_another_group_is_refused(client: TestClient, db, enrolled):
    """⚠️ A hand-edited URL must not reach another group's row from here."""
    from app.db.models import Assignment

    _create(client, "Field Tablets")
    _create(client, "Depot")
    mine = _group(db, "Field Tablets")
    theirs = _group(db, "Depot")
    _assign(client, theirs.id, _make_policy(client))
    assignment = db.scalar(select(Assignment).where(Assignment.group_id == theirs.id))

    response = client.post(
        f"/groups/{mine.id}/assignments/{assignment.id}/remove",
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )

    assert "error=" in response.headers["location"]
    assert db.get(Assignment, assignment.id) is not None


# --------------------------------------------------------------------------- #
# ⚠️ Deleting a group
# --------------------------------------------------------------------------- #


def _delete(client: TestClient, group_id, confirm: str):
    return client.post(
        f"/groups/{group_id}/delete",
        data={"confirm": confirm},
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )


def test_deleting_needs_the_name_typed(client: TestClient, db):
    _create(client, "Field Tablets")
    group = _group(db, "Field Tablets")

    response = _delete(client, group.id, "field tablets")

    assert "error=" in response.headers["location"]
    assert _group(db, "Field Tablets") is not None


def test_deleting_strips_its_policies_from_members(
    client: TestClient, db, enrolled, mtls_headers
):
    """⚠️ The cascade that matters, and the reason members are captured before
    the delete: afterwards `device_group_member` is gone and there is no way to
    learn whose effective policy just changed."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    _create(client, "Field Tablets")
    group = _group(db, "Field Tablets")
    _set_members(client, group.id, [result["device_id"]])
    _assign(client, group.id, _make_policy(client))
    assert checkin(client, headers, force_full=True)["desired_state"]["policy"].get("PASSWORD")

    _delete(client, group.id, "Field Tablets")

    after = checkin(client, headers, force_full=True)["desired_state"]
    assert not after["policy"].get("PASSWORD")


def test_deleting_leaves_the_devices_enrolled(client: TestClient, db, enrolled):
    """It removes a grouping, not a fleet."""
    result = enrolled()
    _create(client, "Field Tablets")
    group = _group(db, "Field Tablets")
    _set_members(client, group.id, [result["device_id"]])

    _delete(client, group.id, "Field Tablets")

    assert db.get(Device, uuid.UUID(result["device_id"])) is not None


def test_the_page_warns_that_scoped_tokens_survive(client: TestClient, db):
    """⚠️ The silent cascade. A token scoped to this group keeps working and
    simply stops placing devices in it, so a tablet enrolled afterwards arrives
    without the policy stack and nothing on the device says why."""
    _create(client, "Field Tablets")
    group = _group(db, "Field Tablets")
    client.post(
        "/api/v1/enrollment-tokens",
        json={"name": "field", "group_ids": [str(group.id)]},
        headers=ADMIN_HEADERS,
    )

    body = client.get(f"/groups/{group.id}", headers=ADMIN_HEADERS).text

    assert "enrollment token" in body
    assert "does <strong>not</strong> revoke" in body


def test_no_token_warning_when_none_reference_the_group(client: TestClient, db):
    """The warning has to mean something when it appears."""
    _create(client, "Field Tablets")
    group = _group(db, "Field Tablets")

    body = client.get(f"/groups/{group.id}", headers=ADMIN_HEADERS).text

    assert "does <strong>not</strong> revoke" not in body
