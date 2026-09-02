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

"""API-level tests for policy stacking end to end."""

from __future__ import annotations

from fastapi.testclient import TestClient


def effective(client: TestClient, device_id: str) -> dict:
    response = client.get(f"/api/v1/devices/{device_id}/effective-policy")
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# Policy type registry
# --------------------------------------------------------------------------- #


def test_policy_types_publish_their_merge_contract(client: TestClient):
    body = client.get("/api/v1/policy-types").json()
    by_name = {t["name"]: t for t in body}

    assert {"PASSWORD", "RESTRICTIONS", "APP_CATALOG", "FILES", "PERIODIC_SYNC"} <= set(by_name)
    assert by_name["PASSWORD"]["merge_rules"]["min_length"]["strategy"] == "max"
    assert by_name["APP_CATALOG"]["merge_rules"]["required_apps"]["key"] == "package_name"
    assert by_name["PERIODIC_SYNC"]["merge_rules"]["sync_behavior"]["strategy"] == "highest_rank"


# --------------------------------------------------------------------------- #
# Policy lifecycle
# --------------------------------------------------------------------------- #


def test_create_policy_starts_at_version_one(make_policy):
    policy = make_policy("Baseline Password", "PASSWORD", {"min_length": 6})

    assert [v["version"] for v in policy["versions"]] == [1]
    assert policy["versions"][0]["spec"] == {"min_length": 6}


def test_spec_stores_only_fields_that_were_set(make_policy):
    """Presence semantics: unset must stay distinguishable from defaulted."""
    policy = make_policy("Sparse", "PASSWORD", {"min_length": 8})

    assert policy["versions"][0]["spec"] == {"min_length": 8}


def test_invalid_spec_is_rejected(client: TestClient):
    response = client.post(
        "/api/v1/policies",
        json={"name": "Bad", "policy_type": "PASSWORD", "spec": {"min_length": 999}},
    )
    assert response.status_code == 422


def test_unknown_field_is_rejected(client: TestClient):
    response = client.post(
        "/api/v1/policies",
        json={"name": "Typo", "policy_type": "PASSWORD", "spec": {"min_lenght": 8}},
    )
    assert response.status_code == 422


def test_unknown_policy_type_is_rejected(client: TestClient):
    response = client.post(
        "/api/v1/policies", json={"name": "X", "policy_type": "NOPE", "spec": {}}
    )
    assert response.status_code == 422


def test_duplicate_policy_name_conflicts(client: TestClient, make_policy):
    make_policy("Baseline", "PASSWORD", {"min_length": 6})
    response = client.post(
        "/api/v1/policies",
        json={"name": "Baseline", "policy_type": "PASSWORD", "spec": {"min_length": 8}},
    )
    assert response.status_code == 409


def test_publishing_a_version_leaves_the_previous_one_untouched(
    client: TestClient, make_policy
):
    policy = make_policy("Baseline", "PASSWORD", {"min_length": 6})

    client.post(
        f"/api/v1/policies/{policy['id']}/versions",
        json={"spec": {"min_length": 10}, "notes": "hardened"},
    )
    versions = client.get(f"/api/v1/policies/{policy['id']}").json()["versions"]

    assert [v["version"] for v in versions] == [1, 2]
    assert versions[0]["spec"] == {"min_length": 6}  # immutable (D2)


# --------------------------------------------------------------------------- #
# Stacking
# --------------------------------------------------------------------------- #


def test_policies_stack_across_device_group_and_tag(client: TestClient, make_policy, make_device, assign):
    device = make_device()
    group = client.post("/api/v1/groups", json={"name": "Field Teams"}).json()
    tag = client.post("/api/v1/tags", json={"name": "quarantine"}).json()

    client.put(
        f"/api/v1/groups/{group['id']}/devices", json={"device_ids": [device["id"]]}
    )
    client.put(f"/api/v1/tags/{tag['id']}/devices", json={"device_ids": [device["id"]]})

    baseline = make_policy("Baseline Password", "PASSWORD", {"min_length": 6})
    field = make_policy("Field Apps", "APP_CATALOG", {"blocked_packages": ["com.game"]})
    lockdown = make_policy("Quarantine", "RESTRICTIONS", {"allow_camera": False})

    assign(baseline["id"], device["id"], scope="device", rank=10)
    assign(field["id"], group["id"], scope="group", rank=20)
    assign(lockdown["id"], tag["id"], scope="tag", rank=100)

    values = effective(client, device["id"])["values"]

    assert values["PASSWORD"]["min_length"] == 6
    assert values["APP_CATALOG"]["blocked_packages"] == ["com.game"]
    assert values["RESTRICTIONS"]["allow_camera"] is False


def test_stacking_does_not_clobber_unrelated_fields(
    client: TestClient, make_policy, make_device, assign
):
    """The whole point: pick the policies that pertain, without rebuilding them."""
    device = make_device()
    broad = make_policy("Baseline", "PASSWORD", {"min_length": 6, "history_length": 5})
    narrow = make_policy("Complexity", "PASSWORD", {"min_digits": 2})

    assign(broad["id"], device["id"], rank=10)
    assign(narrow["id"], device["id"], rank=20)

    assert effective(client, device["id"])["values"]["PASSWORD"] == {
        "min_length": 6,
        "history_length": 5,
        "min_digits": 2,
    }


def test_effective_policy_carries_provenance(
    client: TestClient, make_policy, make_device, assign
):
    device = make_device()
    weak = make_policy("Convenience", "PASSWORD", {"min_length": 4})
    strong = make_policy("Hardened", "PASSWORD", {"min_length": 12})

    assign(weak["id"], device["id"], rank=99)
    assign(strong["id"], device["id"], rank=1)

    record = effective(client, device["id"])["provenance"]["PASSWORD"]["min_length"]

    assert record["value"] == 12
    assert record["source"]["policy_name"] == "Hardened"
    assert record["overridden"][0]["source"]["policy_name"] == "Convenience"


def test_explain_endpoint_answers_why(client: TestClient, make_policy, make_device, assign):
    device = make_device()
    policy = make_policy("Hardened", "PASSWORD", {"min_length": 12})
    assign(policy["id"], device["id"], rank=1)

    response = client.get(
        f"/api/v1/devices/{device['id']}/effective-policy/explain/PASSWORD/min_length"
    )

    assert response.status_code == 200
    assert response.json()["source"]["policy_name"] == "Hardened"


def test_explain_unknown_field_is_404(client: TestClient, make_device):
    device = make_device()
    response = client.get(
        f"/api/v1/devices/{device['id']}/effective-policy/explain/PASSWORD/min_length"
    )
    assert response.status_code == 404


def test_conflicts_are_reported(client: TestClient, make_policy, make_device, assign):
    device = make_device()
    a = make_policy("Field Kiosk", "APP_CATALOG", {"kiosk_package": "com.atak"})
    b = make_policy("Warehouse", "APP_CATALOG", {"kiosk_package": "com.scanner"})

    assign(a["id"], device["id"], rank=50)
    assign(b["id"], device["id"], rank=10)

    body = effective(client, device["id"])

    assert body["values"]["APP_CATALOG"]["kiosk_package"] == "com.atak"
    assert len(body["conflicts"]) == 1
    assert body["conflicts"][0]["field"] == "kiosk_package"


def test_pinned_version_ignores_later_publishes(
    client: TestClient, make_policy, make_device, assign
):
    device = make_device()
    policy = make_policy("Baseline", "PASSWORD", {"min_length": 6})
    assign(policy["id"], device["id"], rank=1, pinned_version=1)

    client.post(
        f"/api/v1/policies/{policy['id']}/versions", json={"spec": {"min_length": 14}}
    )

    assert effective(client, device["id"])["values"]["PASSWORD"]["min_length"] == 6


def test_latest_tracking_assignment_follows_new_versions(
    client: TestClient, make_policy, make_device, assign
):
    device = make_device()
    policy = make_policy("Baseline", "PASSWORD", {"min_length": 6})
    assign(policy["id"], device["id"], rank=1)

    client.post(
        f"/api/v1/policies/{policy['id']}/versions", json={"spec": {"min_length": 14}}
    )

    assert effective(client, device["id"])["values"]["PASSWORD"]["min_length"] == 14


def test_archived_policy_stops_applying(client: TestClient, make_policy, make_device, assign):
    device = make_device()
    policy = make_policy("Temporary", "PASSWORD", {"min_length": 6})
    assign(policy["id"], device["id"], rank=1)
    assert effective(client, device["id"])["values"]

    client.post(f"/api/v1/policies/{policy['id']}/archive")

    assert effective(client, device["id"])["values"] == {}


def test_disabled_assignment_stops_applying(
    client: TestClient, make_policy, make_device, assign
):
    device = make_device()
    policy = make_policy("Baseline", "PASSWORD", {"min_length": 6})
    assignment = assign(policy["id"], device["id"], rank=1)

    client.patch(f"/api/v1/assignments/{assignment['id']}", json={"enabled": False})

    assert effective(client, device["id"])["values"] == {}


def test_deleting_an_assignment_updates_the_device(
    client: TestClient, make_policy, make_device, assign
):
    device = make_device()
    policy = make_policy("Baseline", "PASSWORD", {"min_length": 6})
    assignment = assign(policy["id"], device["id"], rank=1)
    effective(client, device["id"])

    client.delete(f"/api/v1/assignments/{assignment['id']}")

    assert effective(client, device["id"])["values"] == {}


def test_removing_a_device_from_a_group_drops_the_group_policy(
    client: TestClient, make_policy, make_device, assign
):
    device = make_device()
    group = client.post("/api/v1/groups", json={"name": "Field Teams"}).json()
    client.put(f"/api/v1/groups/{group['id']}/devices", json={"device_ids": [device["id"]]})

    policy = make_policy("Group Password", "PASSWORD", {"min_length": 8})
    assign(policy["id"], group["id"], scope="group", rank=1)
    assert effective(client, device["id"])["values"]["PASSWORD"]["min_length"] == 8

    client.put(f"/api/v1/groups/{group['id']}/devices", json={"device_ids": []})

    assert effective(client, device["id"])["values"] == {}


# --------------------------------------------------------------------------- #
# state_version and caching
# --------------------------------------------------------------------------- #


def test_state_version_bumps_when_values_change(
    client: TestClient, make_policy, make_device, assign
):
    device = make_device()
    assert effective(client, device["id"])["state_version"] == 0

    policy = make_policy("Baseline", "PASSWORD", {"min_length": 6})
    assign(policy["id"], device["id"], rank=1)

    assert effective(client, device["id"])["state_version"] == 1


def test_state_version_holds_when_a_change_is_cosmetic(
    client: TestClient, make_policy, make_device, assign
):
    """A no-op republish must not wake the fleet over a metered link."""
    device = make_device()
    policy = make_policy("Baseline", "PASSWORD", {"min_length": 6})
    assign(policy["id"], device["id"], rank=1)
    before = effective(client, device["id"])["state_version"]

    # New version, identical resolved values.
    client.post(
        f"/api/v1/policies/{policy['id']}/versions",
        json={"spec": {"min_length": 6}, "notes": "re-published"},
    )

    assert effective(client, device["id"])["state_version"] == before


def test_repeated_reads_are_stable(client: TestClient, make_policy, make_device, assign):
    device = make_device()
    policy = make_policy("Baseline", "PASSWORD", {"min_length": 6})
    assign(policy["id"], device["id"], rank=1)

    first = effective(client, device["id"])
    second = effective(client, device["id"])

    assert first == second


# --------------------------------------------------------------------------- #
# Preview
# --------------------------------------------------------------------------- #


def test_preview_shows_the_diff_without_persisting(
    client: TestClient, make_policy, make_device, assign
):
    device = make_device()
    baseline = make_policy("Baseline", "PASSWORD", {"min_length": 6})
    assign(baseline["id"], device["id"], rank=1)

    hardened = make_policy("Hardened", "PASSWORD", {"min_length": 12})
    response = client.post(
        f"/api/v1/devices/{device['id']}/effective-policy/preview",
        json={"add": [{"policy_id": hardened["id"], "rank": 50}]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["proposed"]["values"]["PASSWORD"]["min_length"] == 12
    assert body["diff"] == [
        {
            "policy_type": "PASSWORD",
            "field": "min_length",
            "change": "changed",
            "before": 6,
            "after": 12,
        }
    ]
    # Nothing was written.
    assert effective(client, device["id"])["values"]["PASSWORD"]["min_length"] == 6


def test_preview_surfaces_new_conflicts_before_publish(
    client: TestClient, make_policy, make_device, assign
):
    device = make_device()
    current = make_policy("Field Kiosk", "APP_CATALOG", {"kiosk_package": "com.atak"})
    assign(current["id"], device["id"], rank=10)

    rival = make_policy("Warehouse", "APP_CATALOG", {"kiosk_package": "com.scanner"})
    body = client.post(
        f"/api/v1/devices/{device['id']}/effective-policy/preview",
        json={"add": [{"policy_id": rival["id"], "rank": 99}]},
    ).json()

    assert len(body["new_conflicts"]) == 1
    assert body["new_conflicts"][0]["field"] == "kiosk_package"


def test_preview_of_a_removal(client: TestClient, make_policy, make_device, assign):
    device = make_device()
    policy = make_policy("Baseline", "PASSWORD", {"min_length": 6})
    assignment = assign(policy["id"], device["id"], rank=1)

    body = client.post(
        f"/api/v1/devices/{device['id']}/effective-policy/preview",
        json={"remove_assignment_ids": [assignment["id"]]},
    ).json()

    assert body["diff"][0]["change"] == "removed"
    assert body["proposed"]["values"] == {}


def test_empty_preview_is_rejected(client: TestClient, make_device):
    device = make_device()
    response = client.post(
        f"/api/v1/devices/{device['id']}/effective-policy/preview", json={}
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Assignment validation
# --------------------------------------------------------------------------- #


def test_assignment_to_missing_target_is_404(client: TestClient, make_policy):
    policy = make_policy("Baseline", "PASSWORD", {"min_length": 6})
    response = client.post(
        "/api/v1/assignments",
        json={
            "policy_id": policy["id"],
            "scope": "device",
            "target_id": "00000000-0000-0000-0000-000000000000",
            "rank": 1,
        },
    )
    assert response.status_code == 404


def test_pinning_a_nonexistent_version_is_404(client: TestClient, make_policy, make_device):
    device = make_device()
    policy = make_policy("Baseline", "PASSWORD", {"min_length": 6})
    response = client.post(
        "/api/v1/assignments",
        json={
            "policy_id": policy["id"],
            "scope": "device",
            "target_id": device["id"],
            "pinned_version": 7,
        },
    )
    assert response.status_code == 404


def test_list_assignments_for_a_device_resolves_membership(
    client: TestClient, make_policy, make_device, assign
):
    device = make_device()
    group = client.post("/api/v1/groups", json={"name": "Field Teams"}).json()
    client.put(f"/api/v1/groups/{group['id']}/devices", json={"device_ids": [device["id"]]})

    direct = make_policy("Direct", "PASSWORD", {"min_length": 6})
    via_group = make_policy("Via Group", "RESTRICTIONS", {"allow_camera": False})
    unrelated = make_policy("Unrelated", "PASSWORD", {"min_length": 4})

    assign(direct["id"], device["id"], rank=1)
    assign(via_group["id"], group["id"], scope="group", rank=2)
    other_device = make_device(serial="R5CN00TAK02")
    assign(unrelated["id"], other_device["id"], rank=3)

    names = {
        a["policy_name"]
        for a in client.get(f"/api/v1/assignments?device_id={device['id']}").json()
    }

    assert names == {"Direct", "Via Group"}
