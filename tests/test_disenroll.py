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

"""Handing a device back: factory reset, then forget it (W104).

⚠️ **The ordering is the whole feature.** The device acknowledges the reset while
it still exists, and the record goes at that moment — because the acknowledgement
is the last message it will ever send. Most of what is tested here is that the
removal happens on *that* signal and on no other.
"""

from __future__ import annotations

from urllib.parse import unquote

from sqlalchemy import select

from fastapi.testclient import TestClient

from app.db.models import CommandType, Device, DeviceCertificate
from tests.conftest import ADMIN_HEADERS
from tests.test_checkin import checkin, enqueue


def _device(db) -> Device | None:
    return db.scalar(select(Device))


def _disenroll(client: TestClient, device_id: str, confirm: str):
    return client.post(
        f"/devices/{device_id}/disenroll",
        data={"confirm": confirm},
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )


# --------------------------------------------------------------------------- #
# Asking for it
# --------------------------------------------------------------------------- #


def test_the_serial_must_be_typed_to_arm_it(client: TestClient, db, enrolled):
    """⚠️ A dialog dismissed by reflex is not proportionate to erasing a tablet.

    Naming the specific device cannot be done by accident on the wrong row.
    """
    result = enrolled()

    response = _disenroll(client, result["device_id"], "not-the-serial")

    # The reason travels percent-encoded in the redirect; the operator reads it
    # decoded, so the test does too.
    assert "type the serial" in unquote(response.headers["location"])
    stored = client.get(f"/api/v1/devices/{result['device_id']}/commands").json()
    assert stored == [], "nothing was queued"


def test_the_right_serial_queues_a_factory_reset(client: TestClient, db, enrolled):
    result = enrolled()
    device = _device(db)

    _disenroll(client, result["device_id"], device.serial_number)

    stored = client.get(f"/api/v1/devices/{result['device_id']}/commands").json()
    assert [c["command_type"] for c in stored] == ["wipe"]


def test_pressing_twice_does_not_queue_two_resets(client: TestClient, db, enrolled):
    """⚠️ The device would take the first and vanish, orphaning the second."""
    result = enrolled()
    serial = _device(db).serial_number

    _disenroll(client, result["device_id"], serial)
    _disenroll(client, result["device_id"], serial)

    stored = client.get(f"/api/v1/devices/{result['device_id']}/commands").json()
    assert len(stored) == 1


def test_the_page_says_a_reset_is_already_on_its_way(client: TestClient, db, enrolled):
    result = enrolled()
    serial = _device(db).serial_number
    _disenroll(client, result["device_id"], serial)

    body = client.get(f"/devices/{result['device_id']}", headers=ADMIN_HEADERS).text

    assert "Factory reset queued" in body
    assert "Disenroll and factory reset" not in body, "the button is not offered twice"


# --------------------------------------------------------------------------- #
# ⚠️ The acknowledgement, and only it, removes the record
# --------------------------------------------------------------------------- #


def test_the_acknowledgement_removes_the_device(
    client: TestClient, db, enrolled, mtls_headers
):
    """The device confirms it received the reset — the last thing it ever says —
    and the record goes at that moment."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    _disenroll(client, result["device_id"], _device(db).serial_number)

    delivered = checkin(client, headers)
    command = delivered["commands"][0]
    assert command["command_type"] == "wipe"
    assert command["params"]["disenroll"] is True

    checkin(client, headers, results=[{"command_id": command["id"], "succeeded": True}])

    db.expire_all()
    assert _device(db) is None, "the record is gone"


def test_the_certificates_are_revoked_with_it(
    client: TestClient, db, enrolled, mtls_headers
):
    """A wiped device must not be able to authenticate on the way out."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    _disenroll(client, result["device_id"], _device(db).serial_number)

    command = checkin(client, headers)["commands"][0]
    checkin(client, headers, results=[{"command_id": command["id"], "succeeded": True}])

    db.expire_all()
    assert all(c.revoked_at is not None for c in db.scalars(select(DeviceCertificate)))


def test_a_reset_that_failed_keeps_the_device(
    client: TestClient, db, enrolled, mtls_headers
):
    """⚠️ Removal follows the acknowledgement, not the attempt.

    A device that could not wipe — no Device Owner, a call in progress — is still
    out there and still managed, and the operator needs to see it.
    """
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    _disenroll(client, result["device_id"], _device(db).serial_number)

    command = checkin(client, headers)["commands"][0]
    checkin(
        client,
        headers,
        results=[
            {"command_id": command["id"], "succeeded": False, "error": "not device owner"}
        ],
    )

    db.expire_all()
    assert _device(db) is not None


def test_an_ordinary_wipe_does_not_delete_the_record(
    client: TestClient, db, enrolled, mtls_headers
):
    """⚠️ Wiping a *lost* device is a different act from handing one back.

    Only a wipe marked as a disenroll removes anything; otherwise an operator who
    remotely erased a stolen tablet would lose the record they still need.
    """
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    command = enqueue(client, result["device_id"], "wipe")

    checkin(client, headers)
    checkin(client, headers, results=[{"command_id": command["id"], "succeeded": True}])

    db.expire_all()
    assert _device(db) is not None


def test_the_response_to_the_acknowledgement_is_answerable(
    client: TestClient, db, enrolled, mtls_headers
):
    """⚠️ The record is deleted mid-request, so the reply must not be built from it.

    Everything after that point in the check-in reads a row that no longer exists;
    the answer is deliberately empty rather than computed.
    """
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    _disenroll(client, result["device_id"], _device(db).serial_number)
    command = checkin(client, headers)["commands"][0]

    body = checkin(
        client, headers, results=[{"command_id": command["id"], "succeeded": True}]
    )

    assert body["device_id"] == result["device_id"]
    assert body["commands"] == []
    assert body["desired_state"] is None
