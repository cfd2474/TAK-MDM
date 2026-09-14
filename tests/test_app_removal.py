"""Removing installed apps by policy.

⚠️ There is one list now. `removed_packages` — a stricter second blacklist that
uninstalled outright, never fell back to hiding, and reported a failure when the
app survived — was removed in W154. For an ordinary sideloaded app it did what
the blocklist already does; they differed only for preinstalled apps, and two
lists behaving identically in the common case cost more in confusion than the
distinction was worth.

What went with it is the ability to *demand* real removal and be told when it
did not happen. The blocklist uninstalls what it can and hides what it cannot,
so on a preinstalled app the data and the storage stay.

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

    # "No longer required" and "must be gone" are different claims. Conflating
    # them would delete apps from the fleet every time a policy was tidied up —
    # so dropping an app from `required_apps` must not put it on the blocklist.
    catalog = catalog_for(client, device["device_id"])
    assert VICTIM not in catalog.get("blocked_packages", [])


# --------------------------------------------------------------------------- #
# Stacking
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# The blacklist
# --------------------------------------------------------------------------- #


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
