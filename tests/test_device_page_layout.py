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

"""Renaming happens in one place, and the device page opens with what it is for
(W160).

⚠️ The fleet table carried a rename box on every row. That turned a list meant
for scanning a fleet into a wall of inputs and put an edit one stray keystroke
away from every device on the page — a mis-click renames the wrong tablet, and
nothing about the page says which one you touched.
"""

from __future__ import annotations

import io
import re

from fastapi.testclient import TestClient

from tests.conftest import ADMIN_HEADERS


# --------------------------------------------------------------------------- #
# One place to rename
# --------------------------------------------------------------------------- #


def test_the_fleet_table_has_no_rename(client: TestClient, enrolled):
    enrolled(serial="FLEET-1")

    body = client.get("/fleet").text

    assert "/rename" not in body


def test_the_device_page_still_renames(client: TestClient, enrolled):
    device = enrolled(serial="DEV-1")

    body = client.get(f"/devices/{device['device_id']}").text

    assert f"/devices/{device['device_id']}/rename" in body
    assert "rename-row" in body


def test_renaming_still_works(client: TestClient, enrolled):
    """⚠️ Moving a control must not quietly remove the capability."""
    device = enrolled(serial="DEV-2")

    client.post(
        f"/devices/{device['device_id']}/rename",
        data={"name": "Tower 3"},
        follow_redirects=True,
    )

    assert "Tower 3" in client.get(f"/devices/{device['device_id']}").text


def test_the_dead_stylesheet_rules_went_too():
    """A rule for markup nothing emits is a trap for the next reader."""
    css = io.open("app/web/static/atlas.css", encoding="utf-8").read()

    assert ".inline-rename" not in css


# --------------------------------------------------------------------------- #
# The page opens with what it is for
# --------------------------------------------------------------------------- #


def test_actions_come_before_the_policy_detail(client: TestClient, enrolled):
    """⚠️ Sound it, locate it, lock it — the reasons someone opens this page —
    used to sit below four sections of policy explanation."""
    device = enrolled(serial="DEV-3")

    body = client.get(f"/devices/{device['device_id']}").text

    assert body.index('id="actions"') < body.index("Policies reaching this device")


def test_device_info_and_location_are_one_row(client: TestClient, enrolled):
    """They answer one question together: which device, and where."""
    device = enrolled(serial="DEV-4")

    body = client.get(f"/devices/{device['device_id']}").text

    assert 'class="row device-cards"' in body
    assert 'id="hardware">Device info' in body
    assert 'id="location">Location' in body


def test_the_status_pills_lead(client: TestClient, enrolled):
    device = enrolled(serial="DEV-5")

    body = client.get(f"/devices/{device['device_id']}").text

    assert "device-pills" in body
    assert body.index("device-pills") < body.index('id="actions"')


def test_convergence_is_stated_rather_than_implied(client: TestClient, enrolled):
    """⚠️ Whether the page describes the device or what it is about to become."""
    device = enrolled(serial="DEV-6")

    body = client.get(f"/devices/{device['device_id']}").text

    assert "Converged" in body or "Behind" in body


def test_the_compliance_pill_uses_the_real_field(client: TestClient, enrolled):
    """⚠️ `compliance_status`, not `compliance_state`. A name that does not exist
    renders as empty in Jinja rather than raising, so the pill would simply have
    been blank forever."""
    device = enrolled(serial="DEV-7")

    body = client.get(f"/devices/{device['device_id']}").text
    template = io.open(
        "app/web/templates/device_detail.html", encoding="utf-8"
    ).read()

    from app.db.models import ComplianceStatus

    assert "compliance_status.value" in template
    assert "compliance_state" not in template
    # A freshly enrolled device is `unknown`, not `compliant` — asserting the
    # happy state would have passed only by accident on a device that had
    # reported in.
    assert any(state.value in body for state in ComplianceStatus)


# --------------------------------------------------------------------------- #
# "Policies reaching this device" goes somewhere (W167)
#
# The table answers "why is the device doing that", and the next question is
# always "let me change it". The names were plain text, so the answer was: read
# the name, go to Policies, find it again by eye.
# --------------------------------------------------------------------------- #


def _assign(client: TestClient, policy_id: str, device_id: str, rank: int = 1):
    response = client.post(
        "/api/v1/assignments",
        json={
            "policy_id": policy_id,
            "scope": "device",
            "target_id": device_id,
            "rank": rank,
        },
    )
    assert response.status_code in (200, 201), response.text


def test_the_policy_name_links_to_its_editor(client: TestClient, enrolled, make_policy):
    device = enrolled(serial="LINK-1")
    policy = make_policy("Baseline", "PASSWORD", {"min_length": 8})
    _assign(client, policy["id"], device["device_id"])

    page = client.get(f"/devices/{device['device_id']}", headers=ADMIN_HEADERS).text

    assert f'<a href="/policies/{policy["id"]}">Baseline</a>' in page


def test_the_link_actually_opens_the_editor(client: TestClient, enrolled, make_policy):
    """⚠️ Asserting the href alone would pass for a link to a 404.

    The point of the change is arriving at the editor, so the test follows it.
    """
    device = enrolled(serial="LINK-2")
    policy = make_policy("Baseline", "PASSWORD", {"min_length": 8})
    _assign(client, policy["id"], device["device_id"])

    page = client.get(f"/devices/{device['device_id']}", headers=ADMIN_HEADERS).text
    href = re.search(r'<a href="(/policies/[^"]+)">Baseline</a>', page)
    assert href, "no link to follow"

    editor = client.get(href.group(1), headers=ADMIN_HEADERS, follow_redirects=True)

    assert editor.status_code == 200
    assert "Baseline" in editor.text


def test_a_profile_section_lands_on_the_profile_editor(
    client: TestClient, db, enrolled
):
    """⚠️ A section is only editable through the composite that owns it (W21).

    Linking one to somewhere it cannot be edited would be worse than not linking
    it at all. `/policies/{id}` redirects when the policy has a `profile_id`, and
    that redirect is what lets a single link be correct for both kinds of row.
    """
    from app.services import profiles as profile_service

    device = enrolled(serial="LINK-3")
    profile = profile_service.create_profile(
        db,
        name="ATAK Test",
        description=None,
        sections={"password": {"quality": 4, "min_length": 6}},
    )
    db.commit()

    client.post(
        f"/profiles/{profile.id}/targets",
        data={"rank": "5", "device_ids": [device["device_id"]]},
        follow_redirects=True,
    )

    page = client.get(f"/devices/{device['device_id']}", headers=ADMIN_HEADERS).text
    href = re.search(r'<a href="(/policies/[^"]+)">ATAK Test[^<]*</a>', page)
    assert href, f"the section row is not linked:\n{page[:200]}"

    hop = client.get(href.group(1), headers=ADMIN_HEADERS, follow_redirects=False)
    assert hop.status_code in (302, 303, 307)
    assert hop.headers["location"] == f"/profiles/{profile.id}"

    editor = client.get(href.group(1), headers=ADMIN_HEADERS, follow_redirects=True)
    assert editor.status_code == 200


def test_the_remove_button_is_unaffected(client: TestClient, enrolled, make_policy):
    """The row still does what it did. A link in the first cell must not have
    turned the last one into part of it."""
    device = enrolled(serial="LINK-4")
    policy = make_policy("Baseline", "PASSWORD", {"min_length": 8})
    _assign(client, policy["id"], device["device_id"])

    page = client.get(f"/devices/{device['device_id']}", headers=ADMIN_HEADERS).text

    assert "/assignments/" in page and "Remove" in page
