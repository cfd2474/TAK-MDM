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

"""Permanently deleting a policy out of the archive (W47).

D20 says archived policies are never deleted, and that is still the default: the
weight here is on the refusals, and on what a delete must *not* take with it. The
one destructive path is gated on ``archived_at``, which is both what makes it two
deliberate acts and what makes it inert for the fleet — an archived policy is
already skipped by the resolver, so no device's state can move when it goes.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import Assignment, Policy, PolicyProfile, PolicyVersion
from tests.conftest import FLEET_DEFAULT

ADMIN = {"x-authentik-username": "a", "x-authentik-groups": "takmdm-admins"}


def text_of(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def make_policy(client: TestClient, name: str, spec: dict | None = None) -> str:
    response = client.post(
        "/api/v1/policies",
        json={"name": name, "policy_type": "PASSWORD", "spec": spec or {"min_length": 9}},
        headers=ADMIN,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def make_profile(client: TestClient, name: str, sections: dict | None = None) -> str:
    response = client.post(
        "/api/v1/profiles",
        json={"name": name, "sections": sections or {"password": {"min_length": 10}}},
        headers=ADMIN,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def archive(client: TestClient, policy_id: str) -> None:
    response = client.post(f"/api/v1/policies/{policy_id}/archive", headers=ADMIN)
    assert response.status_code == 200, response.text


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #


def test_a_live_policy_cannot_be_deleted(client: TestClient):
    """Archiving first is what makes deletion two acts instead of one click."""
    policy_id = make_policy(client, "Still in use")

    response = client.delete(f"/api/v1/policies/{policy_id}", headers=ADMIN)

    assert response.status_code == 409
    assert "archive the policy before deleting it" in response.text
    assert client.get(f"/api/v1/policies/{policy_id}", headers=ADMIN).status_code == 200


def test_the_refusal_says_why_it_is_two_steps(client: TestClient):
    policy_id = make_policy(client, "Explain yourself")

    detail = client.delete(f"/api/v1/policies/{policy_id}", headers=ADMIN).json()["detail"]

    assert "permanent" in detail and "history" in detail


def test_a_live_profile_cannot_be_deleted(client: TestClient):
    profile_id = make_profile(client, "Live Profile")

    response = client.delete(f"/api/v1/profiles/{profile_id}", headers=ADMIN)

    assert response.status_code == 409
    assert client.get(f"/api/v1/profiles/{profile_id}", headers=ADMIN).status_code == 200


def test_a_profile_section_cannot_be_deleted_on_its_own(client: TestClient, db):
    """It would leave the profile with a hole the editor has no way to show."""
    profile_id = make_profile(client, "Sectioned")
    section = client.get(f"/api/v1/profiles/{profile_id}", headers=ADMIN).json()["sections"][0]

    # Archived, so the only thing left refusing is the section check itself.
    db.get(Policy, uuid.UUID(section["id"])).archived_at = datetime.now(timezone.utc)
    db.commit()

    response = client.delete(f"/api/v1/policies/{section['id']}", headers=ADMIN)

    assert response.status_code == 409
    assert "delete the profile instead" in response.text


def test_deleting_something_that_was_never_there_is_a_404(client: TestClient):
    missing = "00000000-0000-0000-0000-000000000001"

    assert client.delete(f"/api/v1/policies/{missing}", headers=ADMIN).status_code == 404
    assert client.delete(f"/api/v1/profiles/{missing}", headers=ADMIN).status_code == 404


# --------------------------------------------------------------------------- #
# What a delete actually destroys
# --------------------------------------------------------------------------- #


def test_deleting_takes_the_whole_version_history(client: TestClient, db):
    policy_id = make_policy(client, "Doomed")
    client.post(
        f"/api/v1/policies/{policy_id}/versions",
        json={"spec": {"min_length": 12}},
        headers=ADMIN,
    )
    assert db.scalars(select(PolicyVersion)).all()

    archive(client, policy_id)
    assert client.delete(f"/api/v1/policies/{policy_id}", headers=ADMIN).status_code == 204

    db.expire_all()
    assert db.get(Policy, uuid.UUID(policy_id)) is None
    assert db.scalars(select(PolicyVersion)).all() == []


def test_deleting_a_policy_takes_its_assignments(client: TestClient, db, enrolled, assign):
    device = enrolled(serial="W47-ASSIGN")
    policy_id = make_policy(client, "Assigned then archived")
    assign(policy_id, device["device_id"], rank=5)

    archive(client, policy_id)
    assert client.delete(f"/api/v1/policies/{policy_id}", headers=ADMIN).status_code == 204

    db.expire_all()
    assert db.scalars(select(Assignment)).all() == []


def test_a_pinned_assignment_does_not_block_the_delete(client: TestClient, db, enrolled, assign):
    """The schema trap: ``Assignment.pinned_version_id`` is ON DELETE **RESTRICT**
    while the policy's versions cascade, so deleting the policy fans out into two
    tables in an order no database promises. Clearing the assignments first is
    what keeps this from raising."""
    device = enrolled(serial="W47-PINNED")
    policy_id = make_policy(client, "Pinned to v1")
    assign(policy_id, device["device_id"], pinned_version=1)
    client.post(
        f"/api/v1/policies/{policy_id}/versions",
        json={"spec": {"min_length": 14}},
        headers=ADMIN,
    )

    archive(client, policy_id)
    assert client.delete(f"/api/v1/policies/{policy_id}", headers=ADMIN).status_code == 204

    db.expire_all()
    assert db.scalars(select(Assignment)).all() == []
    assert db.scalars(select(PolicyVersion)).all() == []


def test_deleting_a_profile_takes_its_sections(client: TestClient, db):
    profile_id = make_profile(
        client,
        "Whole Profile",
        {"password": {"min_length": 11}, "app_management": {"blocked_packages": ["com.bad"]}},
    )
    assert len(db.scalars(select(Policy)).all()) == 2

    client.post(f"/api/v1/profiles/{profile_id}/archive", headers=ADMIN)
    assert client.delete(f"/api/v1/profiles/{profile_id}", headers=ADMIN).status_code == 204

    db.expire_all()
    assert db.scalars(select(PolicyProfile)).all() == []
    assert db.scalars(select(Policy)).all() == []
    assert db.scalars(select(PolicyVersion)).all() == []


def test_deleting_one_archived_policy_leaves_the_others_alone(client: TestClient, db):
    doomed = make_policy(client, "Doomed")
    spared = make_policy(client, "Spared", {"min_length": 13})
    for policy_id in (doomed, spared):
        archive(client, policy_id)

    client.delete(f"/api/v1/policies/{doomed}", headers=ADMIN)

    db.expire_all()
    surviving = db.scalars(select(Policy)).all()
    assert [p.name for p in surviving] == ["Spared"]
    assert surviving[0].latest_version.spec == {"min_length": 13}


def test_deleting_an_archived_policy_changes_no_device(client: TestClient, enrolled, assign):
    """The gate's second job: archiving already took it off the fleet, so the
    delete moves nothing. A device whose state *did* move would mean the gate had
    let a live policy through."""
    device = enrolled(serial="W47-INERT")
    keep = make_policy(client, "Keeper", {"min_length": 8})
    doomed = make_policy(client, "Doomed", {"min_length": 16})
    assign(keep, device["device_id"], rank=1)
    assign(doomed, device["device_id"], rank=2)
    archive(client, doomed)

    def effective() -> dict:
        return client.get(
            f"/api/v1/devices/{device['device_id']}/effective-policy"
        ).json()["values"]

    before = effective()
    client.delete(f"/api/v1/policies/{doomed}", headers=ADMIN)

    assert effective() == before == {"PASSWORD": {"min_length": 8}, **FLEET_DEFAULT}


# --------------------------------------------------------------------------- #
# The console
# --------------------------------------------------------------------------- #


def test_the_archived_tab_offers_delete_for_both_kinds(client: TestClient):
    policy_id = make_policy(client, "Old policy")
    archive(client, policy_id)
    profile_id = make_profile(client, "Old profile")
    client.post(f"/profiles/{profile_id}/archive", follow_redirects=False)

    tail = client.get("/policies").text.split('data-tab-panel="archived"')[1]

    assert f'action="/policies/{policy_id}/delete"' in tail
    assert f'action="/profiles/{profile_id}/delete"' in tail
    assert "cannot be undone" in tail
    assert "permanent" in text_of(tail)


def test_a_live_policy_is_offered_archive_not_delete(client: TestClient):
    policy_id = make_policy(client, "Working policy")

    body = client.get(f"/policies/{policy_id}").text

    assert f'action="/policies/{policy_id}/archive"' in body
    assert "/delete" not in body


def test_the_detail_page_offers_delete_once_archived(client: TestClient):
    policy_id = make_policy(client, "Retired policy")
    archive(client, policy_id)

    body = client.get(f"/policies/{policy_id}").text

    assert f'action="/policies/{policy_id}/delete"' in body
    assert "Delete permanently" in body
    assert "no undo" in text_of(body)


def test_the_profile_editor_offers_delete_once_archived(client: TestClient):
    profile_id = make_profile(client, "Retired profile")
    client.post(f"/profiles/{profile_id}/archive", follow_redirects=False)

    body = client.get(f"/profiles/{profile_id}").text

    assert f'action="/profiles/{profile_id}/delete"' in body
    assert "Delete permanently" in body


def test_deleting_from_the_console_removes_it_from_the_page(client: TestClient):
    policy_id = make_policy(client, "Console Doomed")
    archive(client, policy_id)

    response = client.post(f"/policies/{policy_id}/delete", follow_redirects=False)

    assert response.status_code in (302, 303)
    assert response.headers["location"] == "/policies#tab-archived"
    assert "Console Doomed" not in client.get("/policies").text
    assert client.get(f"/policies/{policy_id}").status_code == 404


def test_deleting_a_profile_from_the_console_removes_it_from_the_page(client: TestClient):
    profile_id = make_profile(client, "Console Profile")
    client.post(f"/profiles/{profile_id}/archive", follow_redirects=False)

    response = client.post(f"/profiles/{profile_id}/delete", follow_redirects=False)

    assert response.status_code in (302, 303)
    assert "Console Profile" not in client.get("/policies").text


def test_the_console_refuses_to_delete_a_live_policy(client: TestClient):
    """The button is not rendered for a live policy, but the route is what
    enforces it — a hand-made POST must be refused too."""
    policy_id = make_policy(client, "Not archived")

    response = client.post(f"/policies/{policy_id}/delete", follow_redirects=False)

    assert response.status_code == 409
    assert client.get(f"/policies/{policy_id}").status_code == 200
