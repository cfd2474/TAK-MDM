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

"""Storefronts — a version of the ATLAS store that a policy assigns (W140).

The store used to be one server-wide shelf: a boolean per package, seen by every
enrolled device, taking no policy values at all. A storefront is a named shelf a
policy hands to a device, and each entry names a build rather than tracking
whichever is newest — the same rule required apps follow since W139.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import AppPackage, Device
from app.services import effective_policy as eff
from app.services import packages as package_service
from app.services import storefronts
from tests.apk_fixtures import build_apk, make_signing_certificate
from tests.conftest import ADMIN_HEADERS


def _build(db, artifact_storage, package: str, code: int, cert=None):
    result = package_service.ingest(
        db, artifact_storage, build_apk(package, code, certificate_der=cert)
    )
    db.flush()
    return result.version


def _store_of(db, device) -> list[dict]:
    from app.services import desired_state

    return desired_state.build(db, device)["store"]


# --------------------------------------------------------------------------- #
# The shelf itself
# --------------------------------------------------------------------------- #


def test_a_storefront_holds_the_builds_it_was_given(db, artifact_storage):
    cert = make_signing_certificate()
    old = _build(db, artifact_storage, "com.probe", 100, cert)
    _build(db, artifact_storage, "com.probe", 200, cert)

    shelf = storefronts.create(db, name="Field")
    storefronts.set_items(db, shelf, [old.id])

    assert [i.version.version_code for i in shelf.items] == [100]


def test_an_older_build_can_be_the_one_offered(db, artifact_storage):
    """⚠️ The reason a storefront names builds instead of packages.

    An `AppGroup` — a named set of *packages* — already existed and would have
    been the quick answer. A shelf built on it could only ever offer whichever
    build was newest, which is the automatic selection W139 removed, on the one
    surface nobody would think to check.
    """
    cert = make_signing_certificate()
    old = _build(db, artifact_storage, "com.probe", 100, cert)
    newest = _build(db, artifact_storage, "com.probe", 900, cert)

    shelf = storefronts.create(db, name="Field")
    storefronts.set_items(db, shelf, [old.id])

    offered = [i.version.version_code for i in shelf.items]
    assert offered == [100]
    assert newest.version_code not in offered


def test_one_entry_per_package_is_refused(db, artifact_storage):
    """A device installs one build of an app, so two entries are not a choice
    between builds — they are the same slot filled twice."""
    cert = make_signing_certificate()
    first = _build(db, artifact_storage, "com.probe", 100, cert)
    second = _build(db, artifact_storage, "com.probe", 200, cert)

    shelf = storefronts.create(db, name="Field")

    with pytest.raises(storefronts.StorefrontError) as raised:
        storefronts.set_items(db, shelf, [first.id, second.id])

    assert "only one build" in str(raised.value)


def test_a_name_is_required_and_unique(db):
    storefronts.create(db, name="Field")

    with pytest.raises(storefronts.StorefrontError):
        storefronts.create(db, name="Field")
    with pytest.raises(storefronts.StorefrontError):
        storefronts.create(db, name="   ")


def test_deleting_a_build_takes_its_shelf_entry(db, artifact_storage):
    """⚠️ An entry pointing at nothing would either vanish from the shelf
    silently or be resolved to some other build of the same app. A shelf that
    changes what it offers without anyone deciding to is what this prevents."""
    version = _build(db, artifact_storage, "com.probe", 100)
    shelf = storefronts.create(db, name="Field")
    storefronts.set_items(db, shelf, [version.id])
    db.commit()

    db.delete(version)
    db.commit()
    db.expire_all()

    assert storefronts.get(db, shelf.id).items == []


# --------------------------------------------------------------------------- #
# ⚠️ What happens when two policies disagree — the operator's question
# --------------------------------------------------------------------------- #


def test_two_policies_naming_different_storefronts_is_a_conflict(
    client: TestClient, db, artifact_storage, make_device, make_policy, assign
):
    """⚠️ Reported as a **conflict**, not an override, and the distinction is the
    whole of the operator's ask.

    `strategies.py` draws it: an override is a value lost to a strategy with
    deterministic, intended semantics (MAX picked the larger number) and is
    informational. A conflict is a value discarded by a strategy with no natural
    ordering — the operator probably did not intend it and must be told. Two
    shelves have no ordering; the higher-ranked policy wins arbitrarily.
    """
    device = make_device()
    a = storefronts.create(db, name="Field kit")
    b = storefronts.create(db, name="Warehouse kit")
    db.commit()

    high = make_policy("Field", "APP_CATALOG", {"storefront_id": str(a.id)})
    low = make_policy("Warehouse", "APP_CATALOG", {"storefront_id": str(b.id)})
    assign(high["id"], device["id"], rank=50)
    assign(low["id"], device["id"], rank=10)

    body = client.get(
        f"/api/v1/devices/{device['id']}/effective-policy", headers=ADMIN_HEADERS
    ).json()

    assert body["values"]["APP_CATALOG"]["storefront_id"] == str(a.id)
    conflicts = [c for c in body["conflicts"] if c["field"] == "storefront_id"]
    assert len(conflicts) == 1, body["conflicts"]


def test_two_policies_naming_the_same_storefront_is_no_conflict(
    client: TestClient, db, make_device, make_policy, assign
):
    """Agreement is not a conflict. Without this the warning fires on every fleet
    that assigns one shelf through two policies, and an operator who is warned
    constantly is not warned at all."""
    device = make_device()
    shelf = storefronts.create(db, name="Field kit")
    db.commit()

    a = make_policy("Field", "APP_CATALOG", {"storefront_id": str(shelf.id)})
    b = make_policy("Also field", "APP_CATALOG", {"storefront_id": str(shelf.id)})
    assign(a["id"], device["id"], rank=50)
    assign(b["id"], device["id"], rank=10)

    body = client.get(
        f"/api/v1/devices/{device['id']}/effective-policy", headers=ADMIN_HEADERS
    ).json()

    assert [c for c in body["conflicts"] if c["field"] == "storefront_id"] == []


def test_the_losing_shelfs_apps_are_simply_not_offered(
    db, artifact_storage, make_device, make_policy, assign
):
    """⚠️ The consequence the operator wants people warned about, made concrete.

    The losing storefront does not merge, and it is not a fallback: an app on it
    and not on the winner is offered on no device. Where both list the same app
    at different builds, only the winner's build is reachable.
    """
    cert = make_signing_certificate()
    winner_build = _build(db, artifact_storage, "com.probe", 100, cert)
    loser_only = _build(db, artifact_storage, "com.other", 1)

    a = storefronts.create(db, name="Field kit")
    storefronts.set_items(db, a, [winner_build.id])
    b = storefronts.create(db, name="Warehouse kit")
    storefronts.set_items(db, b, [loser_only.id])
    db.commit()

    device = make_device()
    high = make_policy("Field", "APP_CATALOG", {"storefront_id": str(a.id)})
    low = make_policy("Warehouse", "APP_CATALOG", {"storefront_id": str(b.id)})
    assign(high["id"], device["id"], rank=50)
    assign(low["id"], device["id"], rank=10)

    db.expire_all()
    offered = {e["package_name"] for e in _store_of(db, db.scalar(select(Device)))}

    assert offered == {"com.probe"}
    assert "com.other" not in offered


# --------------------------------------------------------------------------- #
# Deleting a shelf a policy still names
# --------------------------------------------------------------------------- #


def test_a_deleted_storefront_leaves_an_empty_shelf_not_an_error(
    db, artifact_storage, make_device, make_policy, assign
):
    """The device loses an offer, not a configuration, and nothing it has already
    installed is touched — so there is nothing to report as broken."""
    version = _build(db, artifact_storage, "com.probe", 100)
    shelf = storefronts.create(db, name="Field")
    storefronts.set_items(db, shelf, [version.id])
    db.commit()

    device = make_device()
    policy = make_policy("Store", "APP_CATALOG", {"storefront_id": str(shelf.id)})
    assign(policy["id"], device["id"])
    db.expire_all()
    assert _store_of(db, db.scalar(select(Device)))

    storefronts.delete(db, storefronts.get(db, shelf.id))
    db.commit()
    db.expire_all()

    assert _store_of(db, db.scalar(select(Device))) == []


def test_an_app_on_no_shelf_reaches_nobody(db, artifact_storage, make_device):
    """⚠️ The behaviour change. Uploading an app used to put it one tick away
    from every device; it now reaches none until a shelf names it and a policy
    hands that shelf out."""
    _build(db, artifact_storage, "com.probe", 100)
    db.commit()
    make_device()
    db.expire_all()

    assert _store_of(db, db.scalar(select(Device))) == []


def test_the_package_row_no_longer_knows_about_the_store(db):
    """`store_listed` is gone: several shelves may name one package, at
    different builds, so the question has no single answer to store."""
    assert not hasattr(AppPackage, "store_listed")


# --------------------------------------------------------------------------- #
# The console (W140 chunk 2)
# --------------------------------------------------------------------------- #


def _create(client: TestClient, name: str = "Field kit") -> str:
    """Create through the console and return the id from its redirect."""
    response = client.post(
        "/storefronts",
        data={"name": name, "description": ""},
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )
    assert response.status_code in (302, 303), response.text
    return response.headers["location"].rsplit("/", 1)[-1]


def test_creating_one_lands_on_its_page(client: TestClient, db):
    """A shelf arrives empty, so the next thing anyone needs is the page where
    its apps are chosen."""
    storefront_id = _create(client)

    page = client.get(f"/storefronts/{storefront_id}", headers=ADMIN_HEADERS)

    assert page.status_code == 200
    assert "Field kit" in page.text
    assert "Apps on this shelf" in page.text


def test_a_duplicate_name_is_refused_legibly(client: TestClient, db):
    _create(client, "Field kit")

    response = client.post(
        "/storefronts",
        data={"name": "Field kit"},
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )

    location = response.headers["location"]
    assert "error=" in location
    assert "already" in location and "exists" in location


def test_ticking_an_app_puts_its_chosen_build_on_the_shelf(
    client: TestClient, db, artifact_storage
):
    """⚠️ End to end through the real form, because every other test here builds
    the shelf by calling the service directly."""
    cert = make_signing_certificate()
    old = _build(db, artifact_storage, "com.probe", 100, cert)
    _build(db, artifact_storage, "com.probe", 900, cert)
    db.commit()
    package = db.scalar(select(AppPackage).where(AppPackage.package_name == "com.probe"))

    storefront_id = _create(client)
    client.post(
        f"/storefronts/{storefront_id}/items",
        data={"include": str(package.id), f"version__{package.id}": str(old.id)},
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )

    db.expire_all()
    shelf = storefronts.get(db, uuid.UUID(storefront_id))
    assert [i.version.version_code for i in shelf.items] == [100]


def test_an_unticked_app_is_off_the_shelf_whatever_its_select_says(
    client: TestClient, db, artifact_storage
):
    """⚠️ Someone who changes a build and then unticks the app has said "not
    this one at all". Reading the select regardless would put it back."""
    version = _build(db, artifact_storage, "com.probe", 100)
    db.commit()
    package = db.scalar(select(AppPackage).where(AppPackage.package_name == "com.probe"))

    storefront_id = _create(client)
    client.post(
        f"/storefronts/{storefront_id}/items",
        data={f"version__{package.id}": str(version.id)},  # no `include`
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )

    db.expire_all()
    assert storefronts.get(db, uuid.UUID(storefront_id)).items == []


def test_the_detail_page_names_the_policies_handing_it_out(
    client: TestClient, db, make_device, make_policy, assign
):
    """Deleting a shelf should be an informed act."""
    storefront_id = _create(client)
    make_policy("Field", "APP_CATALOG", {"storefront_id": storefront_id})

    page = client.get(f"/storefronts/{storefront_id}", headers=ADMIN_HEADERS).text

    assert "Handed out by" in page
    assert "Field" in page


def test_deleting_from_the_console_removes_it(client: TestClient, db):
    storefront_id = _create(client)

    client.post(
        f"/storefronts/{storefront_id}/delete",
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )

    assert storefronts.get(db, uuid.UUID(storefront_id)) is None


# --------------------------------------------------------------------------- #
# The policy form
# --------------------------------------------------------------------------- #


def test_the_policy_form_offers_the_storefronts_and_the_warning(client: TestClient, db):
    """⚠️ The warning belongs next to the control that creates the problem. The
    device page reports the conflict once it exists; this is what stops it."""
    _create(client, "Field kit")

    page = client.get(
        "/policies/new?policy_type=APP_CATALOG", headers=ADMIN_HEADERS
    ).text

    assert 'name="storefront_id"' in page
    assert "Field kit" in page
    assert "One store per device" in page
    assert "only the winner" in page


def test_saving_the_form_writes_the_chosen_storefront(client: TestClient, db):
    storefront_id = _create(client)

    response = client.post(
        "/policies",
        data={
            "name": "With a store",
            "policy_type": "APP_CATALOG",
            "storefront_id": storefront_id,
        },
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )
    assert response.status_code in (302, 303), response.text

    from app.db.models import Policy

    policy = db.scalar(select(Policy).where(Policy.name == "With a store"))
    assert policy.latest_version.spec["storefront_id"] == storefront_id


def test_choosing_no_store_leaves_the_field_out(client: TestClient, db):
    """⚠️ Absent, not empty. A policy with no opinion about the store must not
    assert an empty shelf — under HIGHEST_RANK that would beat a lower-ranked
    policy that did name one."""
    response = client.post(
        "/policies",
        data={"name": "No store", "policy_type": "APP_CATALOG", "storefront_id": ""},
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )
    assert response.status_code in (302, 303), response.text

    from app.db.models import Policy

    policy = db.scalar(select(Policy).where(Policy.name == "No store"))
    assert "storefront_id" not in (policy.latest_version.spec or {})


# --------------------------------------------------------------------------- #
# The conflict, where an operator meets it
# --------------------------------------------------------------------------- #


def test_the_device_page_names_the_storefronts_in_the_conflict(
    client: TestClient, db, make_device, make_policy, assign
):
    """⚠️ Otherwise the one conflict the operator asked to be warned about is the
    least readable thing on the page: the generic renderer prints values
    verbatim, and for this field that is a pair of uuids."""
    device = make_device()
    a = storefronts.create(db, name="Field kit")
    b = storefronts.create(db, name="Warehouse kit")
    db.commit()

    high = make_policy("Field", "APP_CATALOG", {"storefront_id": str(a.id)})
    low = make_policy("Warehouse", "APP_CATALOG", {"storefront_id": str(b.id)})
    assign(high["id"], device["id"], rank=50)
    assign(low["id"], device["id"], rank=10)

    page = client.get(f"/devices/{device['id']}", headers=ADMIN_HEADERS).text

    # ⚠️ Scoped to the conflict banner. The ids appear legitimately further down,
    # in the resolved-values table — asserting their absence from the whole page
    # would fail for a reason that has nothing to do with what this checks.
    start = page.index("conflict(s)")
    banner = page[start:page.index("</div>", start)]

    assert "Field kit" in banner
    assert "Warehouse kit" in banner
    assert str(a.id) not in banner, "the raw uuid was rendered instead of the name"
    assert str(b.id) not in banner
