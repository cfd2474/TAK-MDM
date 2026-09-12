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

"""ATAK Core and Plugins as their own section (W141).

ATAK and its plugins were ordinary entries in required apps, which gave the
compatibility check no fixed point: it had to guess which row was ATAK. They now
live in a section that names the core build first, so every plugin is compared
against a version the operator chose rather than one inferred.

⚠️ **Nothing about how they install changes.** The resolver folds `atak_core`,
`atak_plugins` and `required_apps` into one list, so the agent is told exactly
what it was told before.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import AppPackage, Device
from app.policies.registry import PolicyTypeError, registry
from app.services import atak_compat
from app.services import packages as package_service
from tests.apk_fixtures import build_apk, make_signing_certificate
from tests.conftest import ADMIN_HEADERS, base_sha


def _build(db, artifact_storage, package: str, code: int, *, version_name="1.0",
           plugin_api=None, cert=None):
    result = package_service.ingest(
        db,
        artifact_storage,
        build_apk(package, code, version_name, certificate_der=cert,
                  plugin_api=plugin_api),
    )
    db.flush()
    return result.version


def _sha(version) -> str:
    from app.db.models import PartRole

    return next(f.artifact_sha256 for f in version.files if f.role is PartRole.BASE)


def _apps_of(db, device) -> list[dict]:
    from app.services import desired_state

    return desired_state.build(db, device)["apps"]


# --------------------------------------------------------------------------- #
# ⚠️ The section installs exactly what required apps used to
# --------------------------------------------------------------------------- #


def test_atak_core_and_plugins_reach_the_device(
    db, artifact_storage, make_device, make_policy, assign
):
    """The whole point of folding the three fields back together: a device sees
    one list of apps and cannot tell which section each came from."""
    core = _build(db, artifact_storage, "com.atakmap.app.civ", 52800,
                  version_name="5.8.0.4 (174b425)[playstore]")
    plugin = _build(db, artifact_storage, "com.plugin.one", 1,
                    plugin_api="com.atakmap.app@5.8.0.CIV")
    ordinary = _build(db, artifact_storage, "com.example.notes", 7)
    db.commit()

    device = make_device()
    policy = make_policy(
        "Field",
        "APP_CATALOG",
        {
            "atak_core": {"package_name": "com.atakmap.app.civ",
                          "artifact_sha256": _sha(core)},
            "atak_plugins": [{"package_name": "com.plugin.one",
                              "artifact_sha256": _sha(plugin)}],
            "required_apps": [{"package_name": "com.example.notes",
                               "artifact_sha256": _sha(ordinary)}],
        },
    )
    assign(policy["id"], device["id"])
    db.expire_all()

    apps = _apps_of(db, db.scalar(select(Device)))
    assert {a["package_name"] for a in apps} == {
        "com.atakmap.app.civ", "com.plugin.one", "com.example.notes"
    }
    assert all(a["available"] for a in apps)
    # ATAK first: nothing depends on it, but a desired state read by a human
    # should lead with the thing everything else is built against.
    assert apps[0]["package_name"] == "com.atakmap.app.civ"


def test_a_section_with_nothing_in_it_adds_nothing(
    db, artifact_storage, make_device, make_policy, assign
):
    ordinary = _build(db, artifact_storage, "com.example.notes", 7)
    db.commit()

    device = make_device()
    policy = make_policy(
        "Field",
        "APP_CATALOG",
        {"required_apps": [{"package_name": "com.example.notes",
                            "artifact_sha256": _sha(ordinary)}]},
    )
    assign(policy["id"], device["id"])
    db.expire_all()

    apps = _apps_of(db, db.scalar(select(Device)))
    assert [a["package_name"] for a in apps] == ["com.example.notes"]


# --------------------------------------------------------------------------- #
# ⚠️ The two refusals, and why only one of them is airtight
# --------------------------------------------------------------------------- #


def test_atak_is_refused_in_required_apps_by_the_spec_itself():
    """⚠️ A package-name test, so it holds on every path into a policy — the
    console form, the API, a restored template — without a database."""
    with pytest.raises(PolicyTypeError) as raised:
        registry.validate_spec(
            "APP_CATALOG",
            {"required_apps": [{"package_name": "com.atakmap.app.civ"}]},
        )

    assert "ATAK Core and Plugins" in str(raised.value)


def test_atak_is_refused_in_the_allowlist_too():
    with pytest.raises(PolicyTypeError) as raised:
        registry.validate_spec(
            "APP_CATALOG", {"allowed_packages": ["com.atakmap.app.civ"]}
        )

    assert "ATAK Core and Plugins" in str(raised.value)


def test_atak_is_accepted_in_its_own_section():
    spec = registry.validate_spec(
        "APP_CATALOG", {"atak_core": {"package_name": "com.atakmap.app.civ"}}
    )

    assert spec["atak_core"]["package_name"] == "com.atakmap.app.civ"


def test_a_plugin_in_required_apps_is_refused_by_the_api(
    client: TestClient, db, artifact_storage
):
    """⚠️ The half that needs the library. "Is a plugin" means this app declares
    a `plugin-api`, which is a column — a spec validator cannot see it, so the
    rule lives at every write path that holds a session."""
    _build(db, artifact_storage, "com.plugin.one", 1,
           plugin_api="com.atakmap.app@5.8.0.CIV")
    db.commit()

    response = client.post(
        "/api/v1/policies",
        json={
            "name": "Misplaced",
            "policy_type": "APP_CATALOG",
            "spec": {"required_apps": [{"package_name": "com.plugin.one"}]},
        },
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 422
    assert "ATAK Core and Plugins" in response.text


def test_a_plugin_in_required_apps_is_refused_by_the_console(
    client: TestClient, db, artifact_storage
):
    _build(db, artifact_storage, "com.plugin.one", 1,
           plugin_api="com.atakmap.app@5.8.0.CIV")
    db.commit()

    response = client.post(
        "/policies",
        data={
            "name": "Misplaced",
            "policy_type": "APP_CATALOG",
            "required_apps__package_name": ["com.plugin.one"],
            "required_apps__version_choice": [""],
        },
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )

    assert "error=" in response.headers["location"]
    assert "ATAK" in response.headers["location"]


def test_an_ordinary_app_is_not_mistaken_for_a_plugin(
    client: TestClient, db, artifact_storage
):
    """⚠️ The rule has to be quiet on everything else, or the section becomes a
    place operators route around."""
    _build(db, artifact_storage, "com.example.notes", 7)
    db.commit()

    response = client.post(
        "/api/v1/policies",
        json={
            "name": "Ordinary",
            "policy_type": "APP_CATALOG",
            "spec": {"required_apps": [{"package_name": "com.example.notes"}]},
        },
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 201, response.text


def test_a_plugin_whose_api_was_never_scanned_is_still_caught(
    db, artifact_storage
):
    """⚠️ Asks *any* build, not the newest. `plugin_api` is NULL on anything
    uploaded before the column existed, so a plugin whose latest upload predates
    the scan would otherwise pass as an ordinary app."""
    cert = make_signing_certificate()
    _build(db, artifact_storage, "com.plugin.one", 1,
           plugin_api="com.atakmap.app@5.8.0.CIV", cert=cert)
    newer = _build(db, artifact_storage, "com.plugin.one", 2, cert=cert)
    newer.plugin_api = None
    db.commit()

    assert "com.plugin.one" in atak_compat.plugin_packages(db)


# --------------------------------------------------------------------------- #
# One slot per package, now across three fields
# --------------------------------------------------------------------------- #


def test_the_same_app_cannot_be_a_plugin_and_a_required_app():
    """A package named twice is the same Android slot filled twice, however it is
    spelled. Checking each field alone would let two sections disagree."""
    with pytest.raises(PolicyTypeError) as raised:
        registry.validate_spec(
            "APP_CATALOG",
            {
                "required_apps": [{"package_name": "com.plugin.one"}],
                "atak_plugins": [{"package_name": "com.plugin.one"}],
            },
        )

    assert "more than once" in str(raised.value)


def test_atak_core_cannot_also_be_a_plugin_row():
    with pytest.raises(PolicyTypeError):
        registry.validate_spec(
            "APP_CATALOG",
            {
                "atak_core": {"package_name": "com.atakmap.app.civ"},
                "atak_plugins": [{"package_name": "com.atakmap.app.civ"}],
            },
        )


# --------------------------------------------------------------------------- #
# Two policies, two ATAKs
# --------------------------------------------------------------------------- #


def test_two_policies_naming_different_atak_cores_is_a_conflict(
    client: TestClient, db, artifact_storage, make_device, make_policy, assign
):
    """One ATAK per device. Two policies naming different builds have no natural
    ordering, so the higher rank wins and the operator is told."""
    cert = make_signing_certificate()
    old = _build(db, artifact_storage, "com.atakmap.app.civ", 52500,
                 version_name="5.5.0.1", cert=cert)
    new = _build(db, artifact_storage, "com.atakmap.app.civ", 52800,
                 version_name="5.8.0.4", cert=cert)
    db.commit()

    device = make_device()
    high = make_policy("Field", "APP_CATALOG", {
        "atak_core": {"package_name": "com.atakmap.app.civ",
                      "artifact_sha256": _sha(new)}})
    low = make_policy("Depot", "APP_CATALOG", {
        "atak_core": {"package_name": "com.atakmap.app.civ",
                      "artifact_sha256": _sha(old)}})
    assign(high["id"], device["id"], rank=50)
    assign(low["id"], device["id"], rank=10)

    body = client.get(
        f"/api/v1/devices/{device['id']}/effective-policy", headers=ADMIN_HEADERS
    ).json()

    conflicts = [c for c in body["conflicts"] if c["field"] == "atak_core"]
    assert len(conflicts) == 1, body["conflicts"]
    assert body["values"]["APP_CATALOG"]["atak_core"]["artifact_sha256"] == _sha(new)


# --------------------------------------------------------------------------- #
# The comparison rules themselves, unchanged
# --------------------------------------------------------------------------- #


def test_the_line_comparison_is_unchanged():
    """⚠️ Pinned because the section changes *what* is compared, not *how*.
    ATAK's own versionName carries a fourth component and build metadata, and
    comparing raw strings would call every pairing a mismatch."""
    assert atak_compat.atak_line("5.8.0.4 (174b425)[playstore]") == "5.8.0"
    assert atak_compat.plugin_target("com.atakmap.app@5.8.0.CIV") == "5.8.0"
    assert atak_compat.atak_line("5.8.0.4") == atak_compat.plugin_target(
        "com.atakmap.app@5.8.0.CIV"
    )


def test_an_unscanned_plugin_is_unknown_not_a_mismatch():
    """Silence when unknown. A section that flagged every unscanned build is one
    nobody reads."""
    assert atak_compat.plugin_target(None) is None
