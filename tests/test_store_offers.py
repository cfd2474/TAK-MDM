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
from tests.conftest import ADMIN_HEADERS, base_sha

SURVEY123 = pathlib.Path("Test Files/ArcGIS+Survey123_3.25.32_APKPure.apk")
ATAK = pathlib.Path("Test Files/ATAK-5.8.0.4-174b425-civSmall-release.apk")

needs_survey = pytest.mark.skipif(
    not SURVEY123.exists(), reason="the Survey123 APK is not in this checkout"
)
needs_atak = pytest.mark.skipif(
    not ATAK.exists(), reason="the ATAK APK is not in this checkout"
)


def _upload(client, path: pathlib.Path) -> str:
    return _upload_full(client, path)["package"]["package_name"]


def _upload_full(client, path: pathlib.Path) -> dict:
    response = client.post(
        "/api/v1/packages",
        files={"file": (path.name, path.read_bytes(), "application/octet-stream")},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _shelve(client, db, package_name: str, *, make_policy, assign, device_id) -> object:
    """Put an app on a storefront and assign that storefront to a device (W140).

    ⚠️ Three steps where there used to be one boolean, and that is the feature:
    a shelf is a thing you build, and a policy decides which device sees it.
    """
    from app.services import storefronts

    package = db.scalar(select(AppPackage).where(AppPackage.package_name == package_name))
    version = max(package.versions, key=lambda v: v.version_code)

    storefront = storefronts.create(db, name=f"Shelf for {package_name}")
    storefronts.set_items(db, storefront, [version.id])
    db.commit()

    policy = make_policy(
        f"Store for {package_name}",
        "APP_CATALOG",
        {"storefront_id": str(storefront.id)},
    )
    assign(policy["id"], device_id)
    db.expire_all()
    return storefront


def _unshelve(client, db, storefront_id) -> None:
    from app.services import storefronts

    storefront = storefronts.get(db, storefront_id)
    storefronts.set_items(db, storefront, [])
    db.commit()
    db.expire_all()


@needs_survey
def test_a_storefront_reaches_the_device_its_policy_names(
    client, db, make_device, make_policy, assign
):
    """The operator's ask: build a shelf, assign it, the device sees it.

    ⚠️ This used to be `test_a_store_app_is_offered_to_a_device_with_no_policy`,
    and the inversion is the whole change (W140). A device with no policy was
    once the *strongest* form of the test, because the shelf was server-wide and
    nothing in the policy path could be doing the work. Now the policy path is
    the only thing that does the work.
    """
    created = make_device()
    package_name = _upload(client, SURVEY123)
    _shelve(client, db, package_name, make_policy=make_policy, assign=assign,
            device_id=created["id"])

    device = db.scalar(select(Device))
    state = desired_state.build(db, device)

    offered = [entry["package_name"] for entry in state["store"]]
    assert package_name in offered
    assert state["apps"] == [], "nothing was required, so nothing should be"


@needs_survey
def test_a_device_whose_policies_name_no_storefront_is_offered_nothing(
    client, db, make_device
):
    """⚠️ The behaviour change, pinned. An app sitting in the library used to
    reach every device the moment someone ticked a box; it now reaches none
    until a policy hands out a shelf holding it."""
    make_device()
    _upload(client, SURVEY123)

    device = db.scalar(select(Device))

    assert desired_state.build(db, device)["store"] == []


@needs_survey
def test_an_offer_carries_what_the_device_needs_to_install_it(
    client, db, make_device, make_policy, assign
):
    created = make_device()
    package_name = _upload(client, SURVEY123)
    _shelve(client, db, package_name, make_policy=make_policy, assign=assign,
            device_id=created["id"])

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
def test_taking_an_app_off_the_shelf_withdraws_the_offer(
    client, db, make_device, make_policy, assign
):
    created = make_device()
    package_name = _upload(client, SURVEY123)
    storefront = _shelve(client, db, package_name, make_policy=make_policy,
                         assign=assign, device_id=created["id"])
    device = db.scalar(select(Device))
    assert any(e["package_name"] == package_name for e in desired_state.build(db, device)["store"])

    _unshelve(client, db, storefront.id)

    device = db.scalar(select(Device))
    assert not any(
        e["package_name"] == package_name for e in desired_state.build(db, device)["store"]
    )


@needs_survey
def test_editing_a_shelf_wakes_devices(client, db, make_device, make_policy, assign):
    """⚠️ The trap this whole feature turns on, inherited from the boolean.

    Editing a storefront is not a policy edit, so no policy write path runs —
    nothing recomputes any device unless the storefront service says so. Without
    that, the shelf changes in the console and the fleet is never told.
    """
    from app.services import storefronts

    created = make_device()
    package_name = _upload(client, SURVEY123)
    package = db.scalar(select(AppPackage).where(AppPackage.package_name == package_name))
    version = max(package.versions, key=lambda v: v.version_code)

    storefront = storefronts.create(db, name="Shelf")
    db.commit()
    policy = make_policy("Store", "APP_CATALOG", {"storefront_id": str(storefront.id)})
    assign(policy["id"], created["id"])

    db.expire_all()
    device = db.scalar(select(Device))
    # Through the cache-aware path, not `refresh` directly. `refresh` recomputes
    # unconditionally, so a test built on it bumps `state_version` whether or not
    # anything invalidated the cache — it passes with the invalidation deleted,
    # which is exactly the kind of test that proves nothing.
    eff.get_effective(db, device)
    db.commit()
    before = device.state_version

    storefronts.set_items(db, storefronts.get(db, storefront.id), [version.id])
    db.commit()

    db.expire_all()
    device = db.scalar(select(Device))
    state = eff.get_effective(db, device)

    assert any(e["package_name"] == package_name for e in state.get("store", [])), (
        "the cached state was never recomputed, so the shelf change reached nobody"
    )
    assert device.state_version > before, "the device was never told the shelf changed"


@needs_survey
@needs_atak
def test_an_app_that_is_required_is_not_also_offered(client, db, make_device, make_policy, assign):
    """Required and offered are contradictory instructions.

    Policy is installing it whether the user likes it or not; presenting a choice
    beside that is a decision the console cannot honour.
    """
    from app.services import storefronts

    created = make_device()
    uploaded = _upload_full(client, ATAK)
    required_name = uploaded["package"]["package_name"]
    package = db.scalar(select(AppPackage).where(AppPackage.package_name == required_name))
    version = max(package.versions, key=lambda v: v.version_code)

    storefront = storefronts.create(db, name="Everything")
    storefronts.set_items(db, storefront, [version.id])
    db.commit()

    # One policy that both requires the app and hands out a shelf holding it —
    # the contradiction at its sharpest, and the merge cannot duck it.
    policy = make_policy(
        "Requires ATAK",
        "APP_CATALOG",
        {
            "required_apps": [
                {"package_name": required_name, "artifact_sha256": base_sha(uploaded)}
            ],
            "storefront_id": str(storefront.id),
        },
    )
    assign(policy["id"], created["id"])

    db.expire_all()
    device = db.scalar(select(Device))
    state = desired_state.build(db, device)

    assert any(e["package_name"] == required_name for e in state["apps"])
    assert not any(e["package_name"] == required_name for e in state["store"]), (
        "an app being installed by policy was also offered as an optional install"
    )


# --------------------------------------------------------------------------- #
# Name and icon travel with the offer (W57)
# --------------------------------------------------------------------------- #


@needs_survey
def test_an_offer_carries_the_apps_name_and_icon(
    client, db, make_device, make_policy, assign
):
    """⚠️ The device cannot look either of these up.

    `PackageManager` only knows *installed* apps, so for an app being offered —
    exactly when the screen needs a name and a picture — it has nothing. The
    reported symptom was a store entry titled `com.taksolutions.uasready`.
    """
    created = make_device()
    package_name = _upload(client, SURVEY123)
    _shelve(client, db, package_name, make_policy=make_policy, assign=assign,
            device_id=created["id"])

    device = db.scalar(select(Device))
    entry = next(
        e for e in desired_state.build(db, device)["store"] if e["package_name"] == package_name
    )

    assert entry["label"] == "Survey123", "the offer would show a package id"
    assert entry["icon_url"] == f"/api/v1/device/apps/{package_name}/icon"


@needs_survey
def test_a_required_app_carries_them_too(client, db, make_device, make_policy, assign):
    """Not a store-only nicety — the same screen lists both."""
    created = make_device()
    uploaded = _upload_full(client, SURVEY123)
    package_name = uploaded["package"]["package_name"]
    # Pinned: a required entry naming no build installs nothing (W139), so
    # without this the entry would carry a reason instead of a label.
    policy = make_policy(
        "Requires Survey123",
        "APP_CATALOG",
        {
            "required_apps": [
                {"package_name": package_name, "artifact_sha256": base_sha(uploaded)}
            ]
        },
    )
    assign(policy["id"], created["id"])

    db.expire_all()
    device = db.scalar(select(Device))
    entry = next(
        e for e in desired_state.build(db, device)["apps"] if e["package_name"] == package_name
    )

    assert entry["label"] == "Survey123"
    assert entry["icon_url"]


@needs_survey
def test_an_app_with_no_extractable_icon_offers_no_url(
    client, db, make_device, make_policy, assign
):
    """A vector-only icon yields nothing, and the entry must say so with None
    rather than a URL that 404s on every device that tries it."""
    from app.db.models import AppPackage as Pkg

    created = make_device()
    package_name = _upload(client, SURVEY123)
    _shelve(client, db, package_name, make_policy=make_policy, assign=assign,
            device_id=created["id"])

    package = db.scalar(select(Pkg).where(Pkg.package_name == package_name))
    package.icon_media_type = None
    package.icon_data = None
    db.commit()

    device = db.scalar(select(Device))
    entry = next(
        e for e in desired_state.build(db, device)["store"] if e["package_name"] == package_name
    )

    assert entry["icon_url"] is None


@needs_survey
def test_the_device_icon_endpoint_needs_a_device_certificate(client, db, make_device):
    """It sits under /api/v1/device/, which nginx gates on a client certificate —
    but the application must not depend on the proxy for that."""
    make_device()
    package_name = _upload(client, SURVEY123)

    response = client.get(f"/api/v1/device/apps/{package_name}/icon")

    assert response.status_code in (401, 403), response.status_code
