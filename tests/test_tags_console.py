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

"""Tags in the console (W122).

Tags, tag membership and tag-scoped assignments have existed in the model and
the API since early on with **no console surface at all**. The Manage page's
Tags tab is the first, and it shares its implementation with groups — so the
tests worth having are the ones that prove the shared path really does drive
the *tag* column, not just that a page renders.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from fastapi.testclient import TestClient

from app.db.models import Assignment, Device, Tag
from tests.conftest import ADMIN_HEADERS
from tests.test_checkin import checkin


def _create(client: TestClient, name: str = "field"):
    return client.post(
        "/tags", data={"name": name}, headers=ADMIN_HEADERS, follow_redirects=False
    )


def _tag(db, name: str = "field") -> Tag:
    return db.scalar(select(Tag).where(Tag.name == name))


def _set_members(client: TestClient, tag_id, device_ids: list[str]):
    return client.post(
        f"/tags/{tag_id}/devices",
        data={"device_ids": device_ids},
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )


def _policy(client: TestClient, name: str = "tag pw") -> str:
    return client.post(
        "/api/v1/policies",
        json={"name": name, "policy_type": "PASSWORD", "spec": {"min_length": 7}},
    ).json()["id"]


def _assign(client: TestClient, tag_id, policy_id: str, rank: int = 0):
    return client.post(
        f"/tags/{tag_id}/assignments",
        data={"policy_id": policy_id, "rank": rank},
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )


# --------------------------------------------------------------------------- #
# The tab
# --------------------------------------------------------------------------- #


def test_the_manage_page_has_all_three_tabs(client: TestClient):
    body = client.get("/fleet", headers=ADMIN_HEADERS).text

    for key in ("devices", "groups", "tags"):
        assert f'data-tab="{key}"' in body, key
        assert f'data-tab-panel="{key}"' in body, key


def test_a_tag_can_be_created_and_is_listed(client: TestClient, db):
    _create(client, "field")

    tag = _tag(db)
    assert tag is not None
    assert f"/tags/{tag.id}" in client.get("/fleet", headers=ADMIN_HEADERS).text


def test_a_duplicate_tag_name_is_refused_rather_than_500ing(client: TestClient, db):
    _create(client, "field")

    response = _create(client, "field")

    assert "error=" in response.headers["location"]


# --------------------------------------------------------------------------- #
# ⚠️ The shared path really drives the tag column
# --------------------------------------------------------------------------- #


def test_a_tag_policy_reaches_a_member_device(
    client: TestClient, db, enrolled, mtls_headers
):
    """⚠️ The test that proves the parameterisation.

    Everything here shares its code with groups, so the risk is a tag page that
    quietly writes `group_id`. Asserting the device's desired state catches
    that; asserting a row exists would not.
    """
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    _create(client, "field")
    tag = _tag(db)
    _set_members(client, tag.id, [result["device_id"]])

    _assign(client, tag.id, _policy(client))

    state = checkin(client, headers, force_full=True)["desired_state"]
    assert state["policy"].get("PASSWORD") == {"min_length": 7}


def test_the_assignment_is_scoped_to_the_tag_not_a_group(client: TestClient, db):
    """The column the shared code could most plausibly get wrong."""
    _create(client, "field")
    tag = _tag(db)

    _assign(client, tag.id, _policy(client))

    assignment = db.scalar(select(Assignment))
    assert assignment.tag_id == tag.id
    assert assignment.group_id is None


def test_removing_a_tag_assignment_stops_it_reaching(
    client: TestClient, db, enrolled, mtls_headers
):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    _create(client, "field")
    tag = _tag(db)
    _set_members(client, tag.id, [result["device_id"]])
    _assign(client, tag.id, _policy(client))
    assignment = db.scalar(select(Assignment))

    client.post(
        f"/tags/{tag.id}/assignments/{assignment.id}/remove",
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )

    state = checkin(client, headers, force_full=True)["desired_state"]
    assert not state["policy"].get("PASSWORD")


def test_membership_replaces_rather_than_appends(client: TestClient, db, enrolled):
    first = enrolled()
    second = enrolled(serial="TAGSECOND001")
    _create(client, "field")
    tag = _tag(db)

    _set_members(client, tag.id, [first["device_id"], second["device_id"]])
    db.expire_all()
    assert len(_tag(db).devices) == 2

    _set_members(client, tag.id, [second["device_id"]])
    db.expire_all()

    assert [str(d.id) for d in _tag(db).devices] == [second["device_id"]]


# --------------------------------------------------------------------------- #
# Deleting
# --------------------------------------------------------------------------- #


def test_deleting_a_tag_needs_the_name_typed(client: TestClient, db):
    _create(client, "field")
    tag = _tag(db)

    response = client.post(
        f"/tags/{tag.id}/delete",
        data={"confirm": "Field"},
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )

    assert "error=" in response.headers["location"]
    assert _tag(db) is not None


def test_deleting_a_tag_strips_its_policies_from_members(
    client: TestClient, db, enrolled, mtls_headers
):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    _create(client, "field")
    tag = _tag(db)
    _set_members(client, tag.id, [result["device_id"]])
    _assign(client, tag.id, _policy(client))
    assert checkin(client, headers, force_full=True)["desired_state"]["policy"].get("PASSWORD")

    client.post(
        f"/tags/{tag.id}/delete",
        data={"confirm": "field"},
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )

    state = checkin(client, headers, force_full=True)["desired_state"]
    assert not state["policy"].get("PASSWORD")
    assert db.get(Device, uuid.UUID(result["device_id"])) is not None


def test_the_tag_page_has_no_enrollment_token_warning(client: TestClient, db):
    """⚠️ Only groups can scope an enrollment token, so that warning must not
    appear on a tag page — a caution that is never true is noise that trains
    the reader to skip the ones that are."""
    _create(client, "field")
    tag = _tag(db)

    body = client.get(f"/tags/{tag.id}", headers=ADMIN_HEADERS).text

    assert "enrollment token" not in body


def test_the_tag_page_does_not_offer_a_description(client: TestClient, db):
    """`Tag` has no description column; the shared template must not assume the
    richer shape."""
    _create(client, "field")
    tag = _tag(db)

    body = client.get(f"/tags/{tag.id}", headers=ADMIN_HEADERS).text

    assert body.count('name="description"') == 0
