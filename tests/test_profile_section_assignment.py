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

"""A profile section is assigned through its profile, by every door (W156).

⚠️ There were two doors and only one lock. `PUT /api/v1/policies/{id}/targets`
refused a profile section; the web form at `POST /policies/{id}/targets` did
not. So a section assigned from its own page was written to the database and
shown there as assigned, while the group's page refused to manage it —
"assigned" and "not assignable" at the same time, about the same row.

The group's picker made it worse by *offering* sections, so the only way to
discover the rule was to pick one and read the error.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from fastapi.testclient import TestClient

from app.db.models import Assignment
from tests.conftest import ADMIN_HEADERS


def _section_and_group(client: TestClient) -> tuple[str, str]:
    profile = client.post(
        "/api/v1/profiles", json={"name": "ATAK Test"}, headers=ADMIN_HEADERS
    ).json()
    body = client.put(
        f"/api/v1/profiles/{profile['id']}/sections/app_management",
        json={"spec": {"blocked_packages": ["com.example.x"]}},
        headers=ADMIN_HEADERS,
    ).json()
    group = client.post(
        "/api/v1/groups", json={"name": "G1"}, headers=ADMIN_HEADERS
    ).json()
    return body["sections"][0]["id"], group["id"]


# --------------------------------------------------------------------------- #
# ⚠️ Both doors, one rule
# --------------------------------------------------------------------------- #


def test_the_web_form_refuses_a_section(client: TestClient, db):
    """The door that had no lock."""
    section, group = _section_and_group(client)

    client.post(
        f"/policies/{section}/targets",
        data={"rank": "0", "group_ids": group},
        follow_redirects=False,
    )

    assert db.scalars(select(Assignment)).all() == []


def test_the_refusal_is_visible_to_the_operator(client: TestClient):
    """⚠️ A silent redirect would read as the button not working."""
    section, group = _section_and_group(client)

    response = client.post(
        f"/policies/{section}/targets",
        data={"rank": "0", "group_ids": group},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "error=" in response.headers["location"]
    assert "section+of+a+profile" in response.headers["location"].replace("%20", "+")


def test_the_policy_page_renders_an_error(client: TestClient):
    """⚠️ Asserted on an ordinary policy, deliberately. A *section's* page 303s
    to its profile, so a section's error never reaches a banner — which is why
    the refusal is also kept out of the picker rather than relying on the
    message alone."""
    policy = client.post(
        "/api/v1/policies",
        json={"name": "Normal", "policy_type": "APP_CATALOG"},
        headers=ADMIN_HEADERS,
    ).json()

    body = client.get(f"/policies/{policy['id']}?error=nope").text

    assert "nope" in body


def test_the_api_still_refuses(client: TestClient):
    section, group = _section_and_group(client)

    response = client.put(
        f"/api/v1/policies/{section}/targets",
        json={"mode": "add", "rank": 10, "group_ids": [group]},
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 409
    assert "assign the profile instead" in response.json()["detail"]


def test_both_doors_use_the_same_rule():
    """⚠️ Restating it is how they drifted. One function, imported."""
    import io

    web = io.open("app/web/routes.py", encoding="utf-8").read()

    assert "from app.api.routers.assignments import reject_unassignable" in web
    assert "reject_unassignable(policy)" in web


# --------------------------------------------------------------------------- #
# The picker stops offering what the server will refuse
# --------------------------------------------------------------------------- #


def test_the_group_picker_omits_sections(client: TestClient):
    """⚠️ Checked by id, not by name. The profile itself is now offered and
    shares the name, so matching on text would pass while the section was still
    listed — or fail once the profile appeared, which is what it did."""
    section, group = _section_and_group(client)

    body = client.get(f"/groups/{group}").text
    values = re.findall(r'<option value="([^"]+)"', body)

    assert section not in values
    assert f"policy:{section}" not in values


def test_an_ordinary_policy_is_still_offered_and_assignable(client: TestClient, db):
    """⚠️ The fix must not take the working case with it."""
    _, group = _section_and_group(client)
    policy = client.post(
        "/api/v1/policies",
        json={"name": "Normal", "policy_type": "APP_CATALOG"},
        headers=ADMIN_HEADERS,
    ).json()

    response = client.post(
        f"/policies/{policy['id']}/targets",
        data={"rank": "0", "group_ids": group},
        follow_redirects=False,
    )

    assert "assigned=1" in response.headers["location"]
    assert len(db.scalars(select(Assignment)).all()) == 1
    assert "Normal" in client.get(f"/groups/{group}").text


def test_a_template_is_refused_too(client: TestClient, db):
    """The other half of the shared rule, which the web form also skipped."""
    policy = client.post(
        "/api/v1/policies",
        json={"name": "Tmpl", "policy_type": "APP_CATALOG", "is_template": True},
        headers=ADMIN_HEADERS,
    ).json()
    group = client.post(
        "/api/v1/groups", json={"name": "G2"}, headers=ADMIN_HEADERS
    ).json()

    client.post(
        f"/policies/{policy['id']}/targets",
        data={"rank": "0", "group_ids": group["id"]},
        follow_redirects=False,
    )

    assert db.scalars(select(Assignment)).all() == []


# --------------------------------------------------------------------------- #
# ⚠️ A profile assigned to a group is visible on the group (W156)
# --------------------------------------------------------------------------- #


def _profile_on_group(client: TestClient) -> tuple[str, str]:
    profile = client.post(
        "/api/v1/profiles", json={"name": "ATAK Test"}, headers=ADMIN_HEADERS
    ).json()
    client.put(
        f"/api/v1/profiles/{profile['id']}/sections/app_management",
        json={"spec": {"blocked_packages": ["com.example.x"]}},
        headers=ADMIN_HEADERS,
    )
    group = client.post(
        "/api/v1/groups", json={"name": "G1"}, headers=ADMIN_HEADERS
    ).json()
    client.put(
        f"/api/v1/profiles/{profile['id']}/targets",
        json={"mode": "replace", "group_ids": [group["id"]]},
        headers=ADMIN_HEADERS,
    )
    return profile["id"], group["id"]


def test_the_group_counts_an_assigned_profile(client: TestClient):
    """⚠️ The reported symptom. A profile binds through `profile_assignment`,
    a different table, and the count read only `assignment` — so a group that
    had just been given a profile showed 0 while the profile said otherwise."""
    _, group = _profile_on_group(client)

    row = re.search(r"G1.{0,200}", client.get("/groups").text, re.S).group(0)
    numbers = re.findall(r">(\d+)<", row)

    assert numbers[:2] == ["0", "1"], f"devices/policies read {numbers[:2]}"


def test_the_group_page_names_the_profile(client: TestClient):
    _, group = _profile_on_group(client)

    body = client.get(f"/groups/{group}").text

    assert "ATAK Test" in body
    assert "Nothing assigned to this" not in body


def test_an_empty_group_still_says_nothing_is_assigned(client: TestClient):
    """⚠️ The fix must not leave a bare table on a group with nothing on it."""
    group = client.post(
        "/api/v1/groups", json={"name": "Empty"}, headers=ADMIN_HEADERS
    ).json()

    assert "Nothing assigned to this" in client.get(f"/groups/{group['id']}").text


# --------------------------------------------------------------------------- #
# ⚠️ The operator's actual journey (W157)
#
# "i made a policy. i then made a group. i went into the group to add the
# policy and got that error. i went into the policy and assigned it to the
# group." — /policies/new is the guided *profile* creator, so the thing they
# made was a profile. Its sections are not assignable, which is right; what was
# wrong is that the group had nothing else to offer them.
# --------------------------------------------------------------------------- #


def test_a_group_can_be_given_the_thing_the_creator_makes(client: TestClient):
    """End to end, by the route the operator took."""
    profile, group = _profile_only(client)

    body = client.get(f"/groups/{group}").text
    options = re.findall(r'<option value="([^"]+)"[^>]*>\s*([^<]*?)\s*</option>', body)

    assert options, "the group offered nothing to assign"
    assert any(o[0] == f"profile:{profile}" for o in options)

    response = client.post(
        f"/groups/{group}/assignments",
        data={"policy_id": f"profile:{profile}", "rank": "0"},
        follow_redirects=False,
    )

    assert "assigned=1" in response.headers["location"]
    assert "ATAK Test" in client.get(f"/groups/{group}").text


def _profile_only(client: TestClient) -> tuple[str, str]:
    """A deployment whose only policy work is one profile — the usual case."""
    profile = client.post(
        "/api/v1/profiles", json={"name": "ATAK Test"}, headers=ADMIN_HEADERS
    ).json()
    client.put(
        f"/api/v1/profiles/{profile['id']}/sections/app_management",
        json={"spec": {"blocked_packages": ["com.example.x"]}},
        headers=ADMIN_HEADERS,
    )
    group = client.post(
        "/api/v1/groups", json={"name": "G1"}, headers=ADMIN_HEADERS
    ).json()
    return profile["id"], group["id"]


def test_the_form_is_not_hidden_when_only_profiles_exist(client: TestClient):
    """⚠️ The regression my own section-exclusion would have caused. The form
    was gated on standalone policies existing, so removing sections from the
    list left "No policies exist yet" and no form at all."""
    _profile_only(client)
    group = client.post(
        "/api/v1/groups", json={"name": "G2"}, headers=ADMIN_HEADERS
    ).json()

    body = client.get(f"/groups/{group['id']}").text

    assert 'id="assign-policy"' in body
    assert "Nothing to assign yet" not in body


def test_an_already_assigned_profile_is_not_offered_again(client: TestClient):
    profile, group = _profile_only(client)
    client.post(
        f"/groups/{group}/assignments",
        data={"policy_id": f"profile:{profile}", "rank": "0"},
        follow_redirects=False,
    )

    body = client.get(f"/groups/{group}").text
    options = re.findall(r'<option value="([^"]+)"', body)

    assert f"profile:{profile}" not in options


def test_assigning_a_profile_here_keeps_its_other_targets(client: TestClient):
    """⚠️ The profile targets endpoint defaults to *replace*. Using that from a
    page whose only visible action is "add one group" would silently unassign
    every other group and device the profile reached."""
    profile, group = _profile_only(client)
    other = client.post(
        "/api/v1/groups", json={"name": "Other"}, headers=ADMIN_HEADERS
    ).json()
    client.put(
        f"/api/v1/profiles/{profile}/targets",
        json={"mode": "replace", "group_ids": [other["id"]]},
        headers=ADMIN_HEADERS,
    )

    client.post(
        f"/groups/{group}/assignments",
        data={"policy_id": f"profile:{profile}", "rank": "0"},
        follow_redirects=False,
    )

    assert "ATAK Test" in client.get(f"/groups/{other['id']}").text
    assert "ATAK Test" in client.get(f"/groups/{group}").text


def test_a_bare_uuid_is_still_read_as_a_policy(client: TestClient, db):
    """Anything posting the old field shape keeps working."""
    policy = client.post(
        "/api/v1/policies",
        json={"name": "Normal", "policy_type": "APP_CATALOG"},
        headers=ADMIN_HEADERS,
    ).json()
    group = client.post(
        "/api/v1/groups", json={"name": "G3"}, headers=ADMIN_HEADERS
    ).json()

    response = client.post(
        f"/groups/{group['id']}/assignments",
        data={"policy_id": policy["id"], "rank": "0"},
        follow_redirects=False,
    )

    assert "assigned=1" in response.headers["location"]
    assert len(db.scalars(select(Assignment)).all()) == 1
