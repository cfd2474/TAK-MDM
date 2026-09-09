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


# --------------------------------------------------------------------------- #
# Battery, IMEI and phone number (W108)
# --------------------------------------------------------------------------- #


def _page(client: TestClient, device_id: str) -> str:
    return client.get(f"/devices/{device_id}", headers=ADMIN_HEADERS).text


def test_a_device_reports_its_battery_and_imeis(
    client: TestClient, db, enrolled, mtls_headers
):
    from tests.test_checkin import checkin

    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])

    checkin(
        client,
        headers,
        has_telephony=True,
        imei="356938035643809",
        imei2="356938035643817",
        phone_number="+15551234567",
        battery_level=82,
        battery_charging=True,
    )

    body = _page(client, result["device_id"])
    assert "82%" in body
    assert "charging" in body
    assert "356938035643809" in body
    assert "356938035643817" in body
    assert "+15551234567" in body


def test_a_flat_battery_is_shown_not_hidden(
    client: TestClient, db, enrolled, mtls_headers
):
    """⚠️ 0 is a real reading, and the one worth seeing.

    Rendered with a truthiness check it would read as "not reported" — the page
    would go quiet about a dead device exactly when someone is asking why it
    stopped checking in.
    """
    from tests.test_checkin import checkin

    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])

    checkin(client, headers, battery_level=0, battery_charging=False)

    body = _page(client, result["device_id"])
    assert "0%" in body
    assert "Not reported" not in body.split('<dt>IMEI')[0].split('<dt>Battery')[-1]


def test_battery_is_shown_against_a_time_not_as_a_bare_number(
    client: TestClient, db, enrolled, mtls_headers
):
    """4% a minute ago and 4% yesterday are different situations."""
    from tests.test_checkin import checkin

    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    checkin(client, headers, battery_level=4)

    body = _page(client, result["device_id"])

    assert "as of" in body


# --------------------------------------------------------------------------- #
# ⚠️ Three different silences
# --------------------------------------------------------------------------- #


def test_a_wifi_only_device_says_it_has_no_radio(
    client: TestClient, db, enrolled, mtls_headers
):
    """⚠️ Definitive, and the reason `has_telephony` is reported at all.

    `SM-X520` is Wi-Fi-only. Left as a blank IMEI, an operator would go hunting
    for a permission problem on a device that has no modem to read one from.
    """
    from tests.test_checkin import checkin

    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    checkin(client, headers, has_telephony=False)

    body = _page(client, result["device_id"])

    assert "No cellular radio" in body
    assert "Not readable" not in body


def test_a_cellular_device_with_no_readable_imei_says_so(
    client: TestClient, db, enrolled, mtls_headers
):
    """A different problem from the one above, and a real one."""
    from tests.test_checkin import checkin

    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    checkin(client, headers, has_telephony=True)

    body = _page(client, result["device_id"])

    assert "Not readable" in body
    assert "No cellular radio" not in body


def test_an_agent_too_old_to_say_is_a_third_answer(client: TestClient, db, enrolled):
    """Neither "no radio" nor "unreadable" — an agent version problem."""
    result = enrolled()

    body = _page(client, result["device_id"])

    # Short enough not to span the template's own line wrapping, which is the
    # second time that has broken an assertion in this session.
    assert "older than IMEI" in body
    assert "No cellular radio" not in body
    assert "Not readable" not in body


def test_a_missing_phone_number_explains_that_this_is_normal(
    client: TestClient, db, enrolled, mtls_headers
):
    """⚠️ The number is on the SIM only if the carrier put it there, and many
    never do. Saying "not available" without saying why sends someone to fix
    nothing."""
    from tests.test_checkin import checkin

    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    checkin(client, headers, has_telephony=True, imei="356938035643809")

    body = _page(client, result["device_id"])

    assert "Not provisioned" in body
    assert "often blank on a working device" in body


# --------------------------------------------------------------------------- #
# ⚠️ Absent still means "said nothing"
# --------------------------------------------------------------------------- #


def test_a_later_silent_checkin_does_not_erase_what_was_reported(
    client: TestClient, db, enrolled, mtls_headers
):
    """⚠️ The W32 rule, which `atak_version` and `supported_abis` already follow.

    An agent that stops sending a field — a downgrade, a permission lost — must
    not blank a record the operator can act on.
    """
    from tests.test_checkin import checkin

    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    checkin(client, headers, has_telephony=True, imei="356938035643809", battery_level=50)

    checkin(client, headers)  # says nothing about any of it

    db.expire_all()
    device = _device(db)
    assert device.imei == "356938035643809"
    assert device.battery_level == 50
    assert device.has_telephony is True


def test_a_newer_battery_reading_replaces_the_old_one(
    client: TestClient, db, enrolled, mtls_headers
):
    """Battery is volatile: the newest report wins, including a fall to 0."""
    from tests.test_checkin import checkin

    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    checkin(client, headers, battery_level=90)
    checkin(client, headers, battery_level=0)

    db.expire_all()
    assert _device(db).battery_level == 0


def test_an_impossible_battery_level_is_refused(
    client: TestClient, db, enrolled, mtls_headers
):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])

    response = client.post(
        "/api/v1/device/checkin", json={"battery_level": 140}, headers=headers
    )

    assert response.status_code == 422
