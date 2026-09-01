"""Removing installed apps by policy.

Copyright 2026 TAK-Solutions LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import ADMIN_HEADERS

VICTIM = "com.butterflynetinc.helios"


def policy_with(client: TestClient, name: str, spec: dict) -> str:
    policy = client.post(
        "/api/v1/policies",
        json={"name": name, "policy_type": "APP_CATALOG"},
        headers=ADMIN_HEADERS,
    ).json()
    client.post(
        f"/api/v1/policies/{policy['id']}/versions",
        json={"spec": spec, "publish": True},
        headers=ADMIN_HEADERS,
    )
    return policy["id"]


def assign(client: TestClient, policy_id: str, device_id: str, rank: int = 10):
    client.put(
        f"/api/v1/policies/{policy_id}/targets",
        json={"mode": "add", "rank": rank, "device_ids": [device_id]},
        headers=ADMIN_HEADERS,
    )


def catalog_for(client: TestClient, device_id: str) -> dict:
    body = client.get(f"/api/v1/devices/{device_id}/effective-policy").json()
    return body["values"].get("APP_CATALOG", {})


# --------------------------------------------------------------------------- #
# Removal is distinct from blocking, and from being un-required
# --------------------------------------------------------------------------- #


def test_removed_packages_reaches_the_device(client: TestClient, enrolled):
    device = enrolled(serial="RM-BASIC")
    assign(
        client,
        policy_with(client, "Remove", {"removed_packages": [VICTIM]}),
        device["device_id"],
    )

    assert catalog_for(client, device["device_id"])["removed_packages"] == [VICTIM]


def test_blocking_and_removing_are_separate_fields(client: TestClient, enrolled):
    device = enrolled(serial="RM-DISTINCT")
    assign(
        client,
        policy_with(
            client,
            "Both",
            {"blocked_packages": ["com.example.hidden"], "removed_packages": [VICTIM]},
        ),
        device["device_id"],
    )

    catalog = catalog_for(client, device["device_id"])
    # Blocking hides and is instantly reversible; removing destroys data and
    # reclaims storage. Collapsing them into one field would mean an operator who
    # wanted a temporary restriction silently wiped the app instead.
    assert catalog["blocked_packages"] == ["com.example.hidden"]
    assert catalog["removed_packages"] == [VICTIM]


def test_dropping_an_app_from_required_does_not_remove_it(client: TestClient, enrolled):
    device = enrolled(serial="RM-UNREQUIRED")
    policy = policy_with(
        client, "Required", {"required_apps": [{"package_name": VICTIM}]}
    )
    assign(client, policy, device["device_id"])

    client.post(
        f"/api/v1/policies/{policy}/versions",
        json={"spec": {"required_apps": []}, "publish": True},
        headers=ADMIN_HEADERS,
    )

    # "No longer required" and "must be gone" are different claims. Conflating them
    # would delete apps from the fleet every time a policy was tidied up.
    assert "removed_packages" not in catalog_for(client, device["device_id"])


# --------------------------------------------------------------------------- #
# Stacking
# --------------------------------------------------------------------------- #


def test_removals_union_across_stacked_policies(client: TestClient, enrolled):
    device = enrolled(serial="RM-UNION")
    assign(
        client,
        policy_with(client, "Fleet-wide", {"removed_packages": ["com.example.one"]}),
        device["device_id"],
        rank=10,
    )
    assign(
        client,
        policy_with(client, "Site", {"removed_packages": ["com.example.two"]}),
        device["device_id"],
        rank=20,
    )

    removals = set(catalog_for(client, device["device_id"])["removed_packages"])
    # UNION, so any one policy saying "not this" survives the merge. A strategy
    # that let a stacked policy drop the instruction would be a removal that
    # silently never happens.
    assert removals == {"com.example.one", "com.example.two"}


def test_a_duplicate_removal_appears_once(client: TestClient, enrolled):
    device = enrolled(serial="RM-DEDUPE")
    for name, rank in (("A", 10), ("B", 20)):
        assign(
            client,
            policy_with(client, f"Dup-{name}", {"removed_packages": [VICTIM]}),
            device["device_id"],
            rank=rank,
        )

    assert catalog_for(client, device["device_id"])["removed_packages"] == [VICTIM]


def test_removal_bumps_the_state_version(client: TestClient, enrolled, mtls_headers):
    device = enrolled(serial="RM-VERSION")
    headers = mtls_headers(device["certificate_pem"])
    before = client.post(
        "/api/v1/device/checkin", json={}, headers=headers
    ).json()["state_version"]

    assign(
        client,
        policy_with(client, "Late removal", {"removed_packages": [VICTIM]}),
        device["device_id"],
    )
    after = client.post(
        "/api/v1/device/checkin", json={}, headers=headers
    ).json()["state_version"]

    # Without a bump a dark device would never learn it must remove the app.
    assert after > before


# --------------------------------------------------------------------------- #
# The blacklist
# --------------------------------------------------------------------------- #


def test_blocklist_and_strict_removal_coexist(client: TestClient, enrolled):
    """Two intents, deliberately not merged into one field.

    The blacklist makes an app unusable by whatever means works, and unblocking
    reverses it. Strict removal reclaims the storage and reports failure rather
    than quietly hiding instead — asking for removal and silently getting
    suppression would be the same lie in a different place.
    """
    device = enrolled(serial="BL-BOTH")
    assign(
        client,
        policy_with(
            client,
            "Blacklist",
            {
                "blocked_packages": ["com.google.android.gm"],
                "removed_packages": [VICTIM],
            },
        ),
        device["device_id"],
    )

    catalog = catalog_for(client, device["device_id"])
    assert catalog["blocked_packages"] == ["com.google.android.gm"]
    assert catalog["removed_packages"] == [VICTIM]


def test_blocklist_unions_across_policies(client: TestClient, enrolled):
    device = enrolled(serial="BL-UNION")
    assign(
        client,
        policy_with(client, "Corp", {"blocked_packages": ["com.google.android.gm"]}),
        device["device_id"],
        rank=10,
    )
    assign(
        client,
        policy_with(client, "Site", {"blocked_packages": ["com.example.other"]}),
        device["device_id"],
        rank=20,
    )

    blocked = set(catalog_for(client, device["device_id"])["blocked_packages"])
    assert blocked == {"com.google.android.gm", "com.example.other"}


def test_unblocking_removes_it_from_the_desired_state(client: TestClient, enrolled):
    """The agent can only unhide what the desired state stops asking for."""
    device = enrolled(serial="BL-REVERSIBLE")
    policy = policy_with(
        client, "Temp block", {"blocked_packages": ["com.google.android.gm"]}
    )
    assign(client, policy, device["device_id"])
    assert catalog_for(client, device["device_id"])["blocked_packages"]

    client.post(
        f"/api/v1/policies/{policy}/versions",
        json={"spec": {}, "publish": True},
        headers=ADMIN_HEADERS,
    )

    # Blocking is reversible; the policy going quiet is what triggers the unhide.
    assert not catalog_for(client, device["device_id"]).get("blocked_packages")
