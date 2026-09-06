"""Kiosk / lock task policy (F6), its own policy type since W59.

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

#: Imported rather than retyped: a typo here would pass while the device never locks.
from app.services.effective_policy import ATLAS_LAUNCHER_PACKAGE  # noqa: E402


def policy_with(
    client: TestClient, name: str, spec: dict, policy_type: str = "KIOSK"
) -> str:
    policy = client.post(
        "/api/v1/policies",
        json={"name": name, "policy_type": policy_type},
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
    """The KIOSK section of the device's effective policy.

    Kiosk moved out of APP_CATALOG in W59: "which apps are installed" and "what
    this device is allowed to be" are different questions that merely both name
    an app.
    """
    body = client.get(f"/api/v1/devices/{device_id}/effective-policy").json()
    return body["values"].get("KIOSK", {})


def test_kiosk_is_absent_unless_a_policy_asks(client: TestClient, enrolled):
    device = enrolled(serial="KIOSK-OFF")
    assign(
        client,
        policy_with(
            client,
            "No kiosk",
            {"required_apps": [{"package_name": KIOSK}]},
            policy_type="APP_CATALOG",
        ),
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


# --------------------------------------------------------------------------- #
# Multi-app kiosk — the ATLAS launcher (W68)
# --------------------------------------------------------------------------- #


def required_for(client: TestClient, device_id: str) -> list[str]:
    """The packages the device is told to install, in order."""
    body = client.get(
        f"/api/v1/devices/{device_id}/effective-policy", headers=ADMIN_HEADERS
    ).json()
    apps = body.get("apps") or body["values"].get("APP_CATALOG", {}).get("required_apps", [])
    return [a.get("package_name") for a in apps]


def test_a_multi_app_kiosk_requires_the_launcher_and_every_app(
    client: TestClient, enrolled
):
    """⚠️ Three things have to be installed, and missing any of them reads as a
    broken launcher rather than a missing install:

    * the ATLAS launcher, or there is nothing to lock the device to;
    * every app on the home screen, or its tile is silently dropped;
    * and nothing else, because this list is also what lock task permits.
    """
    device = enrolled(serial="KIOSK-MULTI")
    assign(
        client,
        policy_with(
            client,
            "Multi-app kiosk",
            {
                "multi_app_packages": [
                    {"package_name": KIOSK, "favorite": True},
                    {"package_name": "com.example.second"},
                ]
            },
        ),
        device["device_id"],
    )

    required = required_for(client, device["device_id"])
    assert ATLAS_LAUNCHER_PACKAGE in required
    assert KIOSK in required
    assert "com.example.second" in required


def test_a_single_app_kiosk_does_not_drag_the_launcher_in(client: TestClient, enrolled):
    """The other half: a device that asked for one app must not be handed a
    launcher it will never show. Installing an unused home-screen app on every
    kiosk would be a change to what those devices *are*."""
    device = enrolled(serial="KIOSK-SINGLE-NO-LAUNCHER")
    assign(
        client,
        policy_with(client, "Single app kiosk", {"kiosk_package": KIOSK}),
        device["device_id"],
    )

    assert ATLAS_LAUNCHER_PACKAGE not in required_for(client, device["device_id"])


def test_the_multi_app_list_reaches_the_device_in_order(client: TestClient, enrolled):
    """Order is the operator's arrangement of the home screen, and the launcher
    draws it as given — so it has to survive the effective policy unchanged."""
    device = enrolled(serial="KIOSK-ORDER")
    assign(
        client,
        policy_with(
            client,
            "Ordered kiosk",
            {
                "multi_app_packages": [
                    {"package_name": "com.c"},
                    {"package_name": "com.a"},
                    {"package_name": "com.b"},
                ]
            },
        ),
        device["device_id"],
    )

    kiosk = catalog_for(client, device["device_id"])
    assert [a["package_name"] for a in kiosk["multi_app_packages"]] == [
        "com.c",
        "com.a",
        "com.b",
    ]
