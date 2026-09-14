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

from fastapi.testclient import TestClient


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
