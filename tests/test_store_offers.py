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

"""The ATLAS store reaches the device as an offer, not an order (W56).

Moving a package into the store is **server-wide curation, not policy**: every
enrolled device may offer it, and a device with no policy at all still sees the
shelf. That is the whole point of the operator's request, and it is also what
makes the change easy to get wrong — nothing in the policy path runs when the
store changes, so a store edit can silently reach nobody.
"""

from __future__ import annotations

import pathlib

import pytest
from sqlalchemy import select

from app.db.models import AppPackage, Device
from app.services import desired_state, effective_policy as eff
from tests.conftest import ADMIN_HEADERS

SURVEY123 = pathlib.Path("Test Files/ArcGIS+Survey123_3.25.32_APKPure.apk")
ATAK = pathlib.Path("Test Files/ATAK-5.8.0.4-174b425-civSmall-release.apk")

needs_survey = pytest.mark.skipif(
    not SURVEY123.exists(), reason="the Survey123 APK is not in this checkout"
)
needs_atak = pytest.mark.skipif(
    not ATAK.exists(), reason="the ATAK APK is not in this checkout"
)


def _upload(client, path: pathlib.Path) -> str:
    response = client.post(
        "/api/v1/packages",
        files={"file": (path.name, path.read_bytes(), "application/octet-stream")},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 201, response.text
    return response.json()["package"]["package_name"]


def _list_in_store(client, db, package_name: str, listed: bool = True) -> None:
    package = db.scalar(select(AppPackage).where(AppPackage.package_name == package_name))
    response = client.patch(
        f"/api/v1/packages/{package.id}",
        json={"store_listed": listed},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 200, response.text


@needs_survey
def test_a_store_app_is_offered_to_a_device_with_no_policy(client, db, make_device):
    """The operator's ask, at its plainest: put it in the store, the device sees it.

    A device with no policy assigned is the strongest form of the test — nothing in
    the policy path can be doing the work.
    """
    make_device()
    package_name = _upload(client, SURVEY123)
    _list_in_store(client, db, package_name)

    device = db.scalar(select(Device))
    state = desired_state.build(db, device)

    offered = [entry["package_name"] for entry in state["store"]]
    assert package_name in offered
    assert state["apps"] == [], "nothing was required, so nothing should be"


@needs_survey
def test_an_offer_carries_what_the_device_needs_to_install_it(client, db, make_device):
    make_device()
    package_name = _upload(client, SURVEY123)
    _list_in_store(client, db, package_name)

    device = db.scalar(select(Device))
    entry = next(
        e for e in desired_state.build(db, device)["store"] if e["package_name"] == package_name
    )

    assert entry["available"] is True
    assert entry["version_code"] > 0
    assert entry["files"], "an offer with no files is not installable"
    for part in entry["files"]:
        assert part["sha256"]
        assert part["url"].startswith("/api/v1/device/artifacts/")


@needs_survey
def test_removing_from_the_store_withdraws_the_offer(client, db, make_device):
    make_device()
    package_name = _upload(client, SURVEY123)
    _list_in_store(client, db, package_name)
    device = db.scalar(select(Device))
    assert any(e["package_name"] == package_name for e in desired_state.build(db, device)["store"])

    _list_in_store(client, db, package_name, listed=False)

    db.expire_all()
    device = db.scalar(select(Device))
    assert not any(
        e["package_name"] == package_name for e in desired_state.build(db, device)["store"]
    )


@needs_survey
def test_listing_in_the_store_wakes_devices(client, db, make_device):
    """⚠️ The trap this whole feature turns on.

    Store membership is not a policy edit, so no policy write path runs — nothing
    recomputes any device unless the toggle says so explicitly. Without that, the
    shelf changes in the console and the fleet is never told.
    """
    make_device()
    package_name = _upload(client, SURVEY123)

    device = db.scalar(select(Device))
    # Through the cache-aware path, not `refresh` directly. `refresh` recomputes
    # unconditionally, so a test built on it bumps `state_version` whether or not
    # anything invalidated the cache — it passes with the invalidation deleted,
    # which is exactly the kind of test that proves nothing.
    eff.get_effective(db, device)
    db.commit()
    before = device.state_version

    _list_in_store(client, db, package_name)

    db.expire_all()
    device = db.scalar(select(Device))
    state = eff.get_effective(db, device)

    assert any(e["package_name"] == package_name for e in state.get("store", [])), (
        "the cached state was never recomputed, so the store change reached nobody"
    )
    assert device.state_version > before, "the device was never told the store changed"


@needs_survey
def test_a_package_not_in_the_store_is_not_offered(client, db, make_device):
    make_device()
    package_name = _upload(client, SURVEY123)

    device = db.scalar(select(Device))
    state = desired_state.build(db, device)

    assert not any(e["package_name"] == package_name for e in state["store"])


@needs_survey
@needs_atak
def test_an_app_that_is_required_is_not_also_offered(client, db, make_device, make_policy, assign):
    """Required and offered are contradictory instructions.

    Policy is installing it whether the user likes it or not; presenting a choice
    beside that is a decision the console cannot honour.
    """
    created = make_device()
    required_name = _upload(client, ATAK)
    _list_in_store(client, db, required_name)

    policy = make_policy(
        "Requires ATAK", "APP_CATALOG", {"required_apps": [{"package_name": required_name}]}
    )
    assign(policy["id"], created["id"])

    db.expire_all()
    device = db.scalar(select(Device))
    state = desired_state.build(db, device)

    assert any(e["package_name"] == required_name for e in state["apps"])
    assert not any(e["package_name"] == required_name for e in state["store"]), (
        "an app being installed by policy was also offered as an optional install"
    )
