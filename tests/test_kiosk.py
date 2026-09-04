"""Kiosk / lock task policy (F6).

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

KIOSK = "com.taksolutions.testapp"


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


def test_kiosk_is_absent_unless_a_policy_asks(client: TestClient, enrolled):
    device = enrolled(serial="KIOSK-OFF")
    assign(
        client,
        policy_with(client, "No kiosk", {"required_apps": [{"package_name": KIOSK}]}),
        device["device_id"],
    )

    # F6: kiosk is opt-in and never the default. A device with no kiosk_package
    # must receive nothing that could lock it down.
    assert "kiosk_package" not in catalog_for(client, device["device_id"])


def test_kiosk_package_reaches_the_device(client: TestClient, enrolled):
    device = enrolled(serial="KIOSK-ON")
    assign(
        client,
        policy_with(client, "Kiosk", {"kiosk_package": KIOSK}),
        device["device_id"],
    )

    assert catalog_for(client, device["device_id"])["kiosk_package"] == KIOSK


def test_removing_kiosk_releases_the_device(client: TestClient, enrolled):
    device = enrolled(serial="KIOSK-RELEASE")
    policy = policy_with(client, "Temporary kiosk", {"kiosk_package": KIOSK})
    assign(client, policy, device["device_id"])
    assert catalog_for(client, device["device_id"])["kiosk_package"] == KIOSK

    client.post(
        f"/api/v1/policies/{policy}/versions",
        json={"spec": {}, "publish": True},
        headers=ADMIN_HEADERS,
    )

    # The primary escape route. A policy that can lock a device and never unlock it
    # is a latch, and on this feature a latch strands a tablet.
    assert "kiosk_package" not in catalog_for(client, device["device_id"])


def test_the_highest_ranked_policy_wins_the_kiosk(client: TestClient, enrolled):
    device = enrolled(serial="KIOSK-RANK")
    assign(
        client,
        policy_with(client, "Fleet kiosk", {"kiosk_package": "com.example.fleet"}),
        device["device_id"],
        rank=10,
    )
    assign(
        client,
        policy_with(client, "Site kiosk", {"kiosk_package": KIOSK}),
        device["device_id"],
        rank=99,
    )

    # HIGHEST_RANK, because two kiosk apps have no natural merge: a device can only
    # be locked to one, so someone has to lose and it must be predictable which.
    assert catalog_for(client, device["device_id"])["kiosk_package"] == KIOSK


def test_a_kiosk_conflict_is_reported(client: TestClient, enrolled):
    device = enrolled(serial="KIOSK-CONFLICT")
    assign(
        client,
        policy_with(client, "A", {"kiosk_package": "com.example.a"}),
        device["device_id"],
        rank=10,
    )
    assign(
        client,
        policy_with(client, "B", {"kiosk_package": "com.example.b"}),
        device["device_id"],
        rank=20,
    )

    body = client.get(
        f"/api/v1/devices/{device['device_id']}/effective-policy"
    ).json()
    # Losing a kiosk app silently would leave an operator wondering why the tablet
    # locked to the wrong thing.
    assert any(c["field"] == "kiosk_package" for c in body["conflicts"])
