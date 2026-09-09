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

"""Find my device, and lock the screen (W107).

Buttons on the device page that queue a one-shot command. The interesting part is
not that they queue one — it is *which* ones they can queue, and how long each
stays worth delivering.
"""

from __future__ import annotations

from sqlalchemy import select

from fastapi.testclient import TestClient

from app.db.models import CommandType, Device, DeviceCommand
from app.services.commands import DEFAULT_TTL_HOURS
from tests.conftest import ADMIN_HEADERS


def _device(db) -> Device:
    return db.scalar(select(Device))


def _commands(db) -> list[DeviceCommand]:
    return list(db.scalars(select(DeviceCommand)))


def _press(client: TestClient, device_id: str, action: str):
    return client.post(
        f"/devices/{device_id}/action/{action}",
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )


# --------------------------------------------------------------------------- #
# The buttons
# --------------------------------------------------------------------------- #


def test_play_sound_queues_a_ping(client: TestClient, db, enrolled):
    result = enrolled()

    response = _press(client, result["device_id"], "ping")

    assert response.status_code in (302, 303)
    assert [c.command_type for c in _commands(db)] == [CommandType.PING]


def test_lock_screen_queues_a_lock(client: TestClient, db, enrolled):
    result = enrolled()

    _press(client, result["device_id"], "lock")

    assert [c.command_type for c in _commands(db)] == [CommandType.LOCK]


def test_locate_queues_a_locate(client: TestClient, db, enrolled):
    """Already existed as a command; it had no button until now."""
    result = enrolled()

    _press(client, result["device_id"], "locate")

    assert [c.command_type for c in _commands(db)] == [CommandType.LOCATE]


# --------------------------------------------------------------------------- #
# ⚠️ What the URL may and may not reach
# --------------------------------------------------------------------------- #


def test_the_action_is_an_allowlist_not_the_whole_enum(client: TestClient, db, enrolled):
    """⚠️ The path segment must not select any command that exists.

    These routes are a form post from a page an admin is already on. If the
    segment simply named a `CommandType`, then `wipe` would be one crafted URL
    away from a button captioned "Play sound" — and the request would look
    identical to a legitimate one in every log.
    """
    result = enrolled()

    for forbidden in ("wipe", "reboot", "clear_app_data", "screenshot", "collect_logs"):
        response = _press(client, result["device_id"], forbidden)
        assert response.status_code == 404, forbidden

    assert _commands(db) == [], "nothing was queued"


def test_an_invented_action_is_refused(client: TestClient, db, enrolled):
    result = enrolled()

    assert _press(client, result["device_id"], "self_destruct").status_code == 404
    assert _commands(db) == []


def test_an_action_on_an_unknown_device_is_a_404(client: TestClient, db):
    import uuid as _uuid

    assert _press(client, str(_uuid.uuid4()), "ping").status_code == 404


# --------------------------------------------------------------------------- #
# ⚠️ How long a ping stays worth delivering
# --------------------------------------------------------------------------- #


def test_a_ping_expires_faster_than_anything_else(client: TestClient, db, enrolled):
    """⚠️ A ping answers "where is this thing while I am standing in the room".

    Delivered an hour later it is a tablet shrieking in a bag with nobody nearby
    who knows why, answering a question the operator has already settled. Every
    other command here is worth doing late; this one is not.
    """
    assert DEFAULT_TTL_HOURS[CommandType.PING] == 1
    assert DEFAULT_TTL_HOURS[CommandType.PING] < min(
        hours
        for command_type, hours in DEFAULT_TTL_HOURS.items()
        if command_type is not CommandType.PING
    )


def test_the_queued_ping_carries_that_short_expiry(client: TestClient, db, enrolled):
    result = enrolled()

    _press(client, result["device_id"], "ping")

    command = _commands(db)[0]
    lifetime = command.expires_at - command.created_at
    assert lifetime.total_seconds() <= 3600 + 5


def test_a_ping_reaches_the_device_on_checkin(
    client: TestClient, db, enrolled, mtls_headers
):
    from tests.test_checkin import checkin

    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    _press(client, result["device_id"], "ping")

    delivered = checkin(client, headers)["commands"]

    assert [c["command_type"] for c in delivered] == ["ping"]


# --------------------------------------------------------------------------- #
# The page
# --------------------------------------------------------------------------- #


def test_the_device_page_offers_both_buttons(client: TestClient, db, enrolled):
    result = enrolled()

    body = client.get(f"/devices/{result['device_id']}", headers=ADMIN_HEADERS).text

    assert "Play sound" in body
    assert "Lock screen" in body
    assert f"/devices/{result['device_id']}/action/ping" in body
    assert f"/devices/{result['device_id']}/action/lock" in body


def test_the_page_does_not_pretend_a_lock_secures_an_unprotected_device(
    client: TestClient, db, enrolled
):
    """⚠️ `lockNow()` on a device with no password drops to a lock screen a swipe
    dismisses. Saying "locked" without saying that would have an operator believe
    a lost tablet was secured when it was not."""
    result = enrolled()

    body = client.get(f"/devices/{result['device_id']}", headers=ADMIN_HEADERS).text

    assert "only a swipe" in body


def test_the_page_says_the_sound_beats_silent_mode(client: TestClient, db, enrolled):
    """The whole reason it uses the alarm channel — and the thing an operator
    would otherwise doubt when they press it on a silenced tablet."""
    result = enrolled()

    body = client.get(f"/devices/{result['device_id']}", headers=ADMIN_HEADERS).text

    assert "even when the device is silenced" in body


def test_pressing_a_button_reports_back(client: TestClient, db, enrolled):
    result = enrolled()

    response = _press(client, result["device_id"], "ping")
    body = client.get(response.headers["location"], headers=ADMIN_HEADERS).text

    assert "Sounding the device" in body
