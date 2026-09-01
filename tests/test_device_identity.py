"""Multi-identifier device matching (R13).

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

from tests.conftest import ADMIN_HEADERS, generate_csr

FALLBACK = "SM-X520-6e5d7b239e5d39c3"
REAL_SERIAL = "R5GL40MMHRN"


def enroll(client: TestClient, *, serial: str, identifiers=None, model="SM-X520"):
    secret = client.post(
        "/api/v1/enrollment-tokens",
        json={"name": "ident", "max_uses": 10},
        headers=ADMIN_HEADERS,
    ).json()["secret"]

    body = {
        "token": secret,
        "csr_pem": generate_csr(),
        "serial_number": serial,
        "model": model,
        "os_version": "16",
    }
    if identifiers is not None:
        body["identifiers"] = identifiers
    return client.post("/api/v1/enroll", json=body)


def ident(kind: str, value: str) -> dict:
    return {"kind": kind, "value": value}


# --------------------------------------------------------------------------- #
# The case R13 exists for
# --------------------------------------------------------------------------- #


def test_a_device_moving_off_the_fallback_readopts_its_record(client: TestClient):
    """The whole point. This is what forked a record on real hardware."""
    first = enroll(client, serial=FALLBACK).json()

    # Later the agent gains READ_PHONE_STATE, so it can report the real serial —
    # and still reports the fallback it originally enrolled under.
    second = enroll(
        client,
        serial=REAL_SERIAL,
        identifiers=[ident("serial", REAL_SERIAL), ident("android_id", FALLBACK)],
    ).json()

    assert second["device_id"] == first["device_id"], (
        "a device that changed identity source must re-adopt its own record, "
        "not orphan its history and group membership"
    )


def test_the_display_serial_is_promoted_to_the_real_one(client: TestClient):
    first = enroll(client, serial=FALLBACK).json()

    enroll(
        client,
        serial=REAL_SERIAL,
        identifiers=[ident("serial", REAL_SERIAL), ident("android_id", FALLBACK)],
    )

    device = client.get(f"/api/v1/devices/{first['device_id']}").json()
    # A record named after an ANDROID_ID is wrong on the asset register and means
    # nothing to whoever is holding the tablet.
    assert device["serial_number"] == REAL_SERIAL


def test_the_policy_stack_survives_the_identity_change(client: TestClient):
    """The damage a forked record does, tested directly.

    A duplicate row is only how the fault shows up; what actually hurts is the
    device silently dropping the group membership that drives its policy stack.
    """
    group = client.post(
        "/api/v1/groups", json={"name": "Field"}, headers=ADMIN_HEADERS
    ).json()
    policy = client.post(
        "/api/v1/policies",
        json={"name": "Field PW", "policy_type": "PASSWORD"},
        headers=ADMIN_HEADERS,
    ).json()
    client.post(
        f"/api/v1/policies/{policy['id']}/versions",
        json={"spec": {"min_length": 11}, "publish": True},
        headers=ADMIN_HEADERS,
    )
    client.post(
        "/api/v1/assignments",
        json={
            "policy_id": policy["id"],
            "scope": "group",
            "target_id": group["id"],
            "rank": 10,
        },
        headers=ADMIN_HEADERS,
    )

    secret = client.post(
        "/api/v1/enrollment-tokens",
        json={"name": "scoped", "group_ids": [group["id"]], "max_uses": 5},
        headers=ADMIN_HEADERS,
    ).json()["secret"]
    first = client.post(
        "/api/v1/enroll",
        json={
            "token": secret,
            "csr_pem": generate_csr(),
            "serial_number": FALLBACK,
            "model": "SM-X520",
        },
    ).json()

    enroll(
        client,
        serial=REAL_SERIAL,
        identifiers=[ident("serial", REAL_SERIAL), ident("android_id", FALLBACK)],
    )

    effective = client.get(
        f"/api/v1/devices/{first['device_id']}/effective-policy"
    ).json()
    assert effective["values"]["PASSWORD"]["min_length"] == 11


# --------------------------------------------------------------------------- #
# Matching rules
# --------------------------------------------------------------------------- #


def test_matching_is_by_kind_priority_not_list_order(client: TestClient):
    strong = enroll(client, serial=REAL_SERIAL).json()
    weak = enroll(client, serial=FALLBACK).json()
    assert strong["device_id"] != weak["device_id"]

    # Both known, listed weakest first. The serial must still decide.
    again = enroll(
        client,
        serial=REAL_SERIAL,
        identifiers=[ident("android_id", FALLBACK), ident("serial", REAL_SERIAL)],
    ).json()

    assert again["device_id"] == strong["device_id"]


def test_an_ambiguous_match_is_reported_and_never_merged(client: TestClient):
    strong = enroll(client, serial=REAL_SERIAL).json()
    weak = enroll(client, serial=FALLBACK).json()

    enroll(
        client,
        serial=REAL_SERIAL,
        identifiers=[ident("serial", REAL_SERIAL), ident("android_id", FALLBACK)],
    )

    survivor = client.get(f"/api/v1/devices/{strong['device_id']}").json()
    other = client.get(f"/api/v1/devices/{weak['device_id']}")

    # Both records still exist. Merging two device histories on a guess is not a
    # thing to do as a side effect of a check-in, and it cannot be undone.
    assert other.status_code == 200
    assert weak["device_id"] in (survivor["compliance_detail"] or "")


def test_an_identifier_held_by_another_device_is_not_stolen(client: TestClient):
    owner = enroll(client, serial=FALLBACK).json()
    other = enroll(client, serial="SM-X520-other").json()

    # The second device wrongly claims the first's identifier.
    enroll(
        client,
        serial="SM-X520-other",
        identifiers=[
            ident("android_id", "SM-X520-other"),
            ident("android_id", FALLBACK),
        ],
    )

    # Reassigning it would silently change which record a third device resolves to.
    readopt = enroll(client, serial=FALLBACK).json()
    assert readopt["device_id"] == owner["device_id"]
    assert other["device_id"] != owner["device_id"]


# --------------------------------------------------------------------------- #
# Back-compatibility
# --------------------------------------------------------------------------- #


def test_an_agent_that_sends_no_identifiers_still_enrols(client: TestClient):
    first = enroll(client, serial=FALLBACK, identifiers=None).json()
    again = enroll(client, serial=FALLBACK, identifiers=None).json()

    # A fleet whose devices go dark for weeks cannot be upgraded before it can
    # enrol. The old shape has to keep working untouched.
    assert again["device_id"] == first["device_id"]


def test_an_unknown_identifier_kind_is_kept_not_discarded(client: TestClient):
    first = enroll(
        client, serial=FALLBACK, identifiers=[ident("imei", "353918090000001")]
    ).json()

    again = enroll(
        client, serial="something-else", identifiers=[ident("imei", "353918090000001")]
    ).json()

    # A newer agent reporting a source this server does not know about is still
    # giving us usable identity; refusing it would fork the record.
    assert again["device_id"] == first["device_id"]


def test_identifiers_are_listed_for_a_device(client: TestClient):
    first = enroll(
        client,
        serial=REAL_SERIAL,
        identifiers=[ident("serial", REAL_SERIAL), ident("android_id", FALLBACK)],
    ).json()

    identifiers = client.get(
        f"/api/v1/devices/{first['device_id']}/identifiers"
    ).json()

    assert {i["value"] for i in identifiers} == {REAL_SERIAL, FALLBACK}
    assert {i["kind"] for i in identifiers} == {"serial", "android_id"}


# --------------------------------------------------------------------------- #
# Deletion (housekeeping)
# --------------------------------------------------------------------------- #


def test_deleting_a_live_device_is_refused(client: TestClient):
    device = enroll(client, serial="DEL-LIVE").json()

    response = client.delete(f"/api/v1/devices/{device['device_id']}")

    # One misplaced click must not remove a working tablet. Deletion is two
    # deliberate acts, and retirement has already killed the certificates by the
    # time the second one is possible.
    assert response.status_code == 409
    assert "retire" in response.json()["detail"]
    assert client.get(f"/api/v1/devices/{device['device_id']}").status_code == 200


def test_a_retired_device_can_be_deleted(client: TestClient):
    device = enroll(client, serial="DEL-RETIRED").json()
    client.post(f"/api/v1/devices/{device['device_id']}/retire")

    assert client.delete(f"/api/v1/devices/{device['device_id']}").status_code == 204
    assert client.get(f"/api/v1/devices/{device['device_id']}").status_code == 404


def test_deletion_takes_everything_hanging_off_the_device(
    client: TestClient, mtls_headers
):
    device = enroll(
        client,
        serial="DEL-CASCADE",
        identifiers=[ident("serial", "DEL-CASCADE"), ident("android_id", "SM-del")],
    ).json()
    headers = mtls_headers(device["certificate_pem"])
    client.post(
        "/api/v1/device/logs", json={"content": "noise\n"}, headers=headers
    )
    client.post(
        f"/api/v1/devices/{device['device_id']}/commands",
        json={"command_type": "lock"},
    )

    client.post(f"/api/v1/devices/{device['device_id']}/retire")
    client.delete(f"/api/v1/devices/{device['device_id']}")

    # Left behind, these are rows pointing at a device that no longer exists —
    # and an identifier still claimed would block the serial being reused.
    for path in ("logs", "commands", "identifiers"):
        assert (
            client.get(f"/api/v1/devices/{device['device_id']}/{path}").status_code
            == 404
        )


def test_a_deleted_serial_can_be_enrolled_again(client: TestClient):
    first = enroll(client, serial="DEL-REUSE").json()
    client.post(f"/api/v1/devices/{first['device_id']}/retire")
    client.delete(f"/api/v1/devices/{first['device_id']}")

    again = enroll(client, serial="DEL-REUSE").json()

    # The point of deleting a junk record: the identity it was squatting on has to
    # come free, or the cleanup achieved nothing.
    assert again["device_id"] != first["device_id"]


def test_a_deleted_device_can_no_longer_authenticate(client: TestClient, mtls_headers):
    device = enroll(client, serial="DEL-AUTH").json()
    headers = mtls_headers(device["certificate_pem"])
    assert client.post("/api/v1/device/checkin", json={}, headers=headers).status_code == 200

    client.post(f"/api/v1/devices/{device['device_id']}/retire")
    client.delete(f"/api/v1/devices/{device['device_id']}")

    # Fails closed. The certificate is still cryptographically valid and chains to
    # our CA — what stops it is that it resolves to no device.
    assert client.post("/api/v1/device/checkin", json={}, headers=headers).status_code == 401
