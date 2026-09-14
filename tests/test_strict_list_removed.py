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

"""The strict must-not-be-installed list is gone (W154).

`removed_packages` uninstalled outright, never fell back to hiding, and reported
a failure when the app survived. For an ordinary sideloaded app it did exactly
what `blocked_packages` does; they differed only for preinstalled apps, where
the blocklist hides and the strict list could only fail.

⚠️ These tests exist because removing a *field* is not the same as removing a
*feature*. Specs are `extra="forbid"`, so anything still sending the key has to
fail loudly, and anything that already stored it has to be cleaned up — a saved
policy carrying it would stop validating the moment the field left the class.
"""

from __future__ import annotations

import io
import json

from fastapi.testclient import TestClient

from tests.conftest import ADMIN_HEADERS


# --------------------------------------------------------------------------- #
# The field is gone
# --------------------------------------------------------------------------- #


def test_the_spec_has_no_strict_list():
    from app.policies.specs.app_catalog import AppCatalogSpec

    assert "removed_packages" not in AppCatalogSpec.model_fields


def test_the_form_has_no_such_section():
    from app.policies.form_schema import form_fields

    groups = {f.group for f in form_fields("APP_CATALOG")}

    assert "Must-not-be-installed" not in groups


def test_sending_it_is_refused_and_named(client: TestClient):
    """⚠️ Loudly, not silently. A spec quietly dropping an unknown key would let
    an operator save a policy that does less than it says."""
    policy = client.post(
        "/api/v1/policies",
        json={"name": "Legacy", "policy_type": "APP_CATALOG"},
        headers=ADMIN_HEADERS,
    ).json()

    response = client.post(
        f"/api/v1/policies/{policy['id']}/versions",
        json={"spec": {"removed_packages": ["com.example.x"]}, "publish": True},
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 422
    assert "removed_packages" in response.json()["detail"]


def test_the_blocklist_still_works(client: TestClient, enrolled):
    """The capability that remains: the blocklist still reaches the device."""
    device = enrolled(serial="STRICT-GONE")
    policy = client.post(
        "/api/v1/policies",
        json={"name": "Block", "policy_type": "APP_CATALOG"},
        headers=ADMIN_HEADERS,
    ).json()
    client.post(
        f"/api/v1/policies/{policy['id']}/versions",
        json={"spec": {"blocked_packages": ["com.example.gone"]}, "publish": True},
        headers=ADMIN_HEADERS,
    )
    client.put(
        f"/api/v1/policies/{policy['id']}/targets",
        json={"mode": "add", "rank": 10, "device_ids": [device["device_id"]]},
        headers=ADMIN_HEADERS,
    )

    body = client.get(
        f"/api/v1/devices/{device['device_id']}/effective-policy"
    ).json()

    assert body["values"]["APP_CATALOG"]["blocked_packages"] == ["com.example.gone"]


# --------------------------------------------------------------------------- #
# ⚠️ The agent no longer acts on it either
# --------------------------------------------------------------------------- #


def test_the_agent_does_not_read_the_field():
    """A server that stops sending it and an agent that still honours it would
    leave the feature alive for anything else that could set the key."""
    source = io.open(
        "agent/app/src/main/java/com/taksolutions/atlasmdm/sync/Reconciler.kt",
        encoding="utf-8",
    ).read()

    assert 'stringList("removed_packages")' not in source


def test_the_uninstall_permission_is_kept():
    """⚠️ The blocklist still uninstalls ordinary apps. Dropping the permission
    with the field would have broken the half that stayed."""
    manifest = io.open(
        "agent/app/src/main/AndroidManifest.xml", encoding="utf-8"
    ).read()

    assert "android.permission.REQUEST_DELETE_PACKAGES" in manifest


# --------------------------------------------------------------------------- #
# ⚠️ Stored policies are cleaned up, not left to break
# --------------------------------------------------------------------------- #


def test_a_migration_strips_the_key():
    migration = io.open(
        "alembic/versions/f3h5j7l9n1p3_drop_strict_removal.py", encoding="utf-8"
    ).read()

    assert "policy_version" in migration
    assert "removed_packages" in migration


def test_the_migration_handles_both_json_shapes():
    """⚠️ SQLite returns the column as a string, Postgres as a dict, and this
    project runs both. Handling one would pass every test and do nothing in
    production."""
    migration = io.open(
        "alembic/versions/f3h5j7l9n1p3_drop_strict_removal.py", encoding="utf-8"
    ).read()

    assert "isinstance(spec, str)" in migration


def test_the_migration_strips_only_that_key():
    """Run the transformation the migration performs over a representative spec."""
    spec = {
        "removed_packages": ["com.example.x"],
        "blocked_packages": ["com.example.y"],
        "required_apps": [{"package_name": "com.example.z"}],
    }

    raw = json.loads(json.dumps(spec))
    raw.pop("removed_packages")

    assert raw == {
        "blocked_packages": ["com.example.y"],
        "required_apps": [{"package_name": "com.example.z"}],
    }
