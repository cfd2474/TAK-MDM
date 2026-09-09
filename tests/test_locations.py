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

"""Where devices have been: storing it (W106 C1).

⚠️ **A location table is believed.** Nobody audits a track against reality — it
*is* the record — so a wrong point is not noticed, it is acted on. Most of what
is tested here is therefore what gets refused, and the rest is that the two
timestamps keep meaning different things.
"""

from __future__ import annotations

import math
import pathlib
from datetime import datetime, timedelta, timezone

from urllib.parse import unquote

from sqlalchemy import select

from fastapi.testclient import TestClient

from app.db.models import CommandType, Device, DeviceLocation, LocationSource
from app.services import locations as location_service
from tests.conftest import ADMIN_HEADERS
from tests.test_checkin import checkin, enqueue


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _device(db) -> Device:
    return db.scalar(select(Device))


def _points(db) -> list[DeviceLocation]:
    return list(
        db.scalars(select(DeviceLocation).order_by(DeviceLocation.recorded_at.desc()))
    )


def _report(minutes_ago: float = 0, **over):
    point = {
        "latitude": 39.7392,
        "longitude": -104.9903,
        "accuracy_m": 12.5,
        "provider": "gps",
        "recorded_at": (_now() - timedelta(minutes=minutes_ago)).isoformat(),
    }
    point.update(over)
    return point


# --------------------------------------------------------------------------- #
# The ordinary path
# --------------------------------------------------------------------------- #


def test_a_device_reports_a_batch_and_it_is_stored(
    client: TestClient, db, enrolled, mtls_headers
):
    """The device buffers at its interval and flushes on check-in — so the usual
    delivery is several points at once, not one."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])

    checkin(
        client,
        headers,
        locations=[_report(30), _report(15), _report(0)],
    )

    stored = _points(db)
    assert len(stored) == 3
    assert {p.source for p in stored} == {LocationSource.PERIODIC}
    assert stored[0].latitude == 39.7392


def test_the_two_timestamps_mean_different_things(
    client: TestClient, db, enrolled, mtls_headers
):
    """⚠️ The whole reason both columns exist.

    A point recorded six hours ago and delivered now is a *delayed delivery*, not
    a device that was here six hours ago and has since vanished. Keeping only one
    timestamp would make those two situations identical in the record.
    """
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])

    checkin(client, headers, locations=[_report(minutes_ago=360)])

    point = _points(db)[0]
    gap = point.received_at - point.recorded_at
    assert gap > timedelta(hours=5), "the fix is recorded as old"
    assert point.received_at <= _now() + timedelta(seconds=5), "receipt is our clock"


def test_an_agent_that_says_nothing_stores_nothing(
    client: TestClient, db, enrolled, mtls_headers
):
    """An older agent does not know the field. That is not an error, and it is
    not an instruction to erase anything either — history only appends."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])

    checkin(client, headers)

    assert _points(db) == []


# --------------------------------------------------------------------------- #
# ⚠️ What is refused
# --------------------------------------------------------------------------- #


def test_an_impossible_latitude_is_refused_at_the_schema(
    client: TestClient, db, enrolled, mtls_headers
):
    """A latitude of 91 is not a coordinate. Refused before the handler, so the
    device is told plainly rather than having the point quietly disappear."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])

    response = client.post(
        "/api/v1/device/checkin",
        json={"locations": [_report(latitude=91.0)]},
        headers=headers,
    )

    assert response.status_code == 422
    assert _points(db) == []


def test_a_nan_coordinate_never_reaches_the_table(db, enrolled):
    """⚠️ The one bad value with consequences long after it lands.

    NaN compares false against every bound, so a check written as "reject what is
    out of range" lets it through — and thereafter every bounding box computed
    from the table is NaN, including ones drawn months later by code that has no
    idea why. The range test is written so NaN fails it rather than passing.
    """
    assert location_service._plausible(float("nan"), 0.0, None) is False
    assert location_service._plausible(0.0, float("nan"), None) is False
    assert location_service._plausible(0.0, 0.0, float("nan")) is False
    assert math.isnan(float("nan"))  # the trap being guarded against


def test_a_point_from_the_future_is_dropped(
    client: TestClient, db, enrolled, mtls_headers
):
    """⚠️ A device whose clock is wrong is not a device that is wrong.

    Its coordinates may be perfectly good. But a fix stamped next year sits at the
    top of every history view for ever, and nothing in the console would explain
    why — so the point is dropped and the reason is logged.
    """
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])

    checkin(
        client,
        headers,
        locations=[
            _report(minutes_ago=-60 * 24 * 365),  # a year ahead
            _report(minutes_ago=5),  # and a good one alongside it
        ],
    )

    stored = _points(db)
    assert len(stored) == 1, "the good point survived, the impossible one did not"
    assert stored[0].recorded_at < _now()


def test_a_little_clock_drift_is_tolerated(
    client: TestClient, db, enrolled, mtls_headers
):
    """Devices drift, and NTP may not have run. Being strict here would discard
    good fixes from an otherwise healthy tablet."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])

    checkin(client, headers, locations=[_report(minutes_ago=-2)])

    assert len(_points(db)) == 1


def test_the_batch_cap_is_the_same_number_in_both_places():
    """⚠️ The schema's 422 and the service's warning describe one threshold.

    Two literals would eventually disagree, and the symptom would be points that
    are accepted by validation and then silently not read.
    """
    from app.api.schemas import CheckinRequest

    caps = [
        m.max_length
        for m in CheckinRequest.model_fields["locations"].metadata
        if hasattr(m, "max_length")
    ]
    assert caps == [location_service.MAX_BATCH]


# --------------------------------------------------------------------------- #
# ⚠️ Re-delivery, which happens exactly when the network is worst
# --------------------------------------------------------------------------- #


def test_the_same_points_delivered_twice_are_stored_once(
    client: TestClient, db, enrolled, mtls_headers
):
    """A flush whose response was lost is re-sent by a correct agent. Answering
    that with duplicates would corrupt the track precisely when coverage is bad."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    batch = [_report(30), _report(15)]

    checkin(client, headers, locations=batch)
    checkin(client, headers, locations=batch)

    assert len(_points(db)) == 2


def test_a_batch_repeating_itself_internally_is_stored_once(
    client: TestClient, db, enrolled, mtls_headers
):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    one = _report(20)

    checkin(client, headers, locations=[one, one, one])

    assert len(_points(db)) == 1


# --------------------------------------------------------------------------- #
# The `locate` command, which already existed
# --------------------------------------------------------------------------- #


def test_a_locate_answer_becomes_a_point(
    client: TestClient, db, enrolled, mtls_headers
):
    """An operator asking "where is this device" is also answering "where has it
    been" — so history fills for devices with no tracking policy at all."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    command = enqueue(client, result["device_id"], "locate")

    checkin(client, headers)
    checkin(
        client,
        headers,
        results=[
            {
                "command_id": command["id"],
                "succeeded": True,
                "result": {
                    "latitude": 39.7392,
                    "longitude": -104.9903,
                    "accuracy_metres": 8.0,
                    "provider": "gps",
                    "fixed_at_millis": int(_now().timestamp() * 1000),
                    "age_seconds": 4,
                },
            }
        ],
    )

    stored = _points(db)
    assert len(stored) == 1
    assert stored[0].source is LocationSource.COMMAND
    assert stored[0].accuracy_m == 8.0


def test_a_locate_that_found_nothing_stores_no_point(
    client: TestClient, db, enrolled, mtls_headers
):
    """`no last known location available` is a real outcome indoors. The command
    reports its own failure; there is simply no position to keep."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    command = enqueue(client, result["device_id"], "locate")

    checkin(client, headers)
    checkin(
        client,
        headers,
        results=[
            {
                "command_id": command["id"],
                "succeeded": False,
                "error": "no last known location available",
            }
        ],
    )

    assert _points(db) == []


def test_the_agent_field_names_are_translated_not_assumed():
    """⚠️ The handler says `accuracy_metres` / `fixed_at_millis`; the wire schema
    says `accuracy_m` / `recorded_at`. They were named independently, and one
    place knows both."""
    point = location_service.from_locate_result(
        {
            "latitude": 1.5,
            "longitude": 2.5,
            "accuracy_metres": 30.0,
            "provider": "network",
            "fixed_at_millis": 1_757_332_800_000,
        }
    )

    assert point is not None
    assert point.accuracy_m == 30.0
    assert point.recorded_at.tzinfo is timezone.utc
    assert point.recorded_at.year == 2025


def test_a_malformed_locate_result_is_ignored_rather_than_fatal():
    """It arrives inside a check-in. Failing the whole sync over a bonus point
    would cost the device its policy update as well."""
    for junk in (None, {}, {"latitude": 1}, {"latitude": "x", "longitude": 2, "fixed_at_millis": 0}):
        assert location_service.from_locate_result(junk) is None


# --------------------------------------------------------------------------- #
# Reading it back
# --------------------------------------------------------------------------- #


def test_history_bounds_read_newest_to_oldest(
    client: TestClient, db, enrolled, mtls_headers
):
    """⚠️ `newest` is the recent end and `oldest` is further back — the same way
    round as the console asks the question, so nothing translates between two
    conventions on the way through."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    checkin(client, headers, locations=[_report(180), _report(90), _report(5)])
    device = _device(db)

    window = location_service.history(
        db,
        device.id,
        newest=_now() - timedelta(minutes=30),
        oldest=_now() - timedelta(minutes=120),
    )

    assert len(window) == 1, "only the 90-minute-old point is inside the window"


def test_latest_is_the_newest_fix_not_the_newest_delivery(
    client: TestClient, db, enrolled, mtls_headers
):
    """A backlog delivered late must not make an old point look current."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])

    checkin(client, headers, locations=[_report(2)])
    checkin(client, headers, locations=[_report(240, latitude=1.0, longitude=1.0)])

    newest = location_service.latest(db, _device(db).id)
    assert newest.latitude == 39.7392, "the older fix delivered later did not win"


def test_points_go_when_the_device_does(
    client: TestClient, db, enrolled, mtls_headers
):
    """⚠️ Disenroll deletes the device (W104), and a track is the most personal
    thing here — it must not outlive the record it belongs to."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    checkin(client, headers, locations=[_report(5)])
    assert len(_points(db)) == 1

    device = _device(db)
    client.post(
        f"/devices/{device.id}/disenroll",
        data={"confirm": device.serial_number},
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )
    command = checkin(client, headers)["commands"][0]
    assert command["command_type"] == CommandType.WIPE.value
    checkin(client, headers, results=[{"command_id": command["id"], "succeeded": True}])

    db.expire_all()
    assert _points(db) == [], "the track went with the device"


# --------------------------------------------------------------------------- #
# The policy, in the console
# --------------------------------------------------------------------------- #


def test_tracking_and_fencing_is_a_working_category_now(client: TestClient):
    """It was a placeholder with two named sub-topics and no backend."""
    body = client.get("/policies/new").text

    assert 'data-page-panel="tracking_fencing:device-location-tracking"' in body
    assert "reporting_interval_minutes" in body


def test_geofencing_is_a_real_form_now(client: TestClient):
    """⚠️ It was a stub until C4, and the stub must be gone rather than beside it.

    A sub-topic listed twice — once working, once inert — offers the operator the
    same thing in two places and lets them configure the one that does nothing.
    That is the mistake the wallpaper placeholder records in the catalog.
    """
    body = client.get("/policies/new").text
    panel = body[body.index('data-page-panel="tracking_fencing:geofencing"'):]
    panel = panel[: panel.index("</section>")]

    assert "Not available yet." not in panel
    assert body.count('data-page-panel="tracking_fencing:geofencing"') == 1


def test_location_tracking_is_listed_above_geofencing(client: TestClient):
    """⚠️ Asked for in that order, and stubs otherwise sort first.

    The default put Geofencing on top, which is the reverse of what was asked
    for — so a stub now names the sub-page it follows, and this is the assertion
    that the default has not quietly come back.
    """
    body = client.get("/policies/new").text

    tracking = body.index('data-page-panel="tracking_fencing:device-location-tracking"')
    geofencing = body.index('data-page-panel="tracking_fencing:geofencing"')

    assert tracking < geofencing


def test_atak_configs_stub_still_leads_its_category(client: TestClient):
    """The same change must not have reordered the category that wanted the old
    behaviour — "Plugin behavior" is deliberately above the two working ones."""
    body = client.get("/policies/new").text

    stub = body.index('data-page-panel="atak_config:plugin-behavior"')
    real = body.index('data-page-panel="atak_config:atak-core-pref-config"')

    assert stub < real


def test_zero_means_off_and_is_a_legal_value(client: TestClient):
    """⚠️ 0 must be storable. A `ge=1` here would make "disabled" unexpressible
    and quietly turn the off switch into "as rarely as possible"."""
    response = client.post(
        "/api/v1/policies",
        json={
            "name": "tracking-off",
            "policy_type": "TRACKING_FENCING",
            "spec": {"reporting_interval_minutes": 0},
        },
    )

    assert response.status_code == 201, response.text
    stored = response.json()["versions"][0]["spec"]
    assert stored["reporting_interval_minutes"] == 0, "stored as 0, not dropped as falsey"


def test_an_absurd_interval_is_refused(client: TestClient):
    """Six hours of silence is indistinguishable from a broken agent."""
    response = client.post(
        "/api/v1/policies",
        json={
            "name": "tracking-absurd",
            "policy_type": "TRACKING_FENCING",
            "spec": {"reporting_interval_minutes": 10_080},
        },
    )

    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Reaching the device (C2 step 1)
# --------------------------------------------------------------------------- #


def test_the_interval_reaches_the_device_in_the_bundle(
    client: TestClient, db, enrolled, mtls_headers
):
    """⚠️ Nothing in C2 works if the policy does not arrive.

    The desired-state bundle passes `policy` through whole, so a new type should
    need no plumbing — "should" being the reason this is a test and not a note.
    """
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    policy = client.post(
        "/api/v1/policies",
        json={
            "name": "track-every-5",
            "policy_type": "TRACKING_FENCING",
            "spec": {"reporting_interval_minutes": 5},
        },
    ).json()
    client.post(
        "/api/v1/assignments",
        json={
            "policy_id": policy["id"],
            "scope": "device",
            "target_id": result["device_id"],
            "rank": 1,
        },
    )

    body = checkin(client, headers, force_full=True)

    section = body["desired_state"]["policy"]["TRACKING_FENCING"]
    assert section["reporting_interval_minutes"] == 5


def test_tracking_switched_off_reaches_the_device_as_zero(
    client: TestClient, db, enrolled, mtls_headers
):
    """⚠️ 0 must survive the whole path, not be dropped as falsey somewhere.

    An interval that vanishes between the console and the device leaves the agent
    on its previous setting — a device that an operator believes they have stopped
    tracking, still reporting.
    """
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    policy = client.post(
        "/api/v1/policies",
        json={
            "name": "track-off",
            "policy_type": "TRACKING_FENCING",
            "spec": {"reporting_interval_minutes": 0},
        },
    ).json()
    client.post(
        "/api/v1/assignments",
        json={
            "policy_id": policy["id"],
            "scope": "device",
            "target_id": result["device_id"],
            "rank": 1,
        },
    )

    body = checkin(client, headers, force_full=True)

    section = body["desired_state"]["policy"]["TRACKING_FENCING"]
    assert section["reporting_interval_minutes"] == 0


# --------------------------------------------------------------------------- #
# Thinning a track for display (C3)
# --------------------------------------------------------------------------- #


def test_the_tiers_match_the_reference_portal_exactly():
    """⚠️ Ported arithmetic, checked against the original at every boundary.

    `EUD_Remote_Assist_Portal`'s `locationHistoryBucketKey` is:

        ageMin <= 360   -> floor(ageMin / 15)
        ageMin <= 2880  -> 24 + floor((ageMin - 360) / 60)
        ageMin <= 5760  -> 66 + floor((ageMin - 2880) / 360)
        otherwise       -> 74 + floor((ageMin - 5760) / 1440)

    The operator asked for a duplication of how that portal displays locations, so
    a tier that is nearly right is a wrong answer rather than a near one.
    """
    now = _now()

    def key(minutes: float) -> int:
        return location_service.bucket_key(now - timedelta(minutes=minutes), now)

    for minutes in (0, 10, 119, 121, 200, 359, 360, 361, 1000, 2879, 2880, 2881,
                    5000, 5759, 5760, 5761, 10_000):
        if minutes <= 360:
            expected = int(minutes // 15)
        elif minutes <= 2880:
            expected = 24 + int((minutes - 360) // 60)
        elif minutes <= 5760:
            expected = 66 + int((minutes - 2880) // 360)
        else:
            expected = 74 + int((minutes - 5760) // 1440)
        assert key(minutes) == expected, f"{minutes} minutes"


def test_everything_in_the_last_two_hours_is_kept(
    client: TestClient, db, enrolled, mtls_headers
):
    """The recent end of a track is the part anyone is actually looking at."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    checkin(client, headers, locations=[_report(m) for m in range(0, 120, 10)])

    drawn = location_service.downsample(location_service.history(db, _device(db).id))

    assert len(drawn) == 12, "no thinning inside two hours"


def test_an_old_stretch_is_thinned_to_one_per_bucket(
    client: TestClient, db, enrolled, mtls_headers
):
    """⚠️ Thinning is a *display* decision; every point is still stored."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    checkin(
        client,
        headers,
        locations=[_report(minutes_ago=1440 + offset) for offset in (0, 10, 20, 30, 40)],
    )

    stored = location_service.history(db, _device(db).id)
    drawn = location_service.downsample(stored)

    assert len(stored) == 5, "all five are stored"
    assert len(drawn) == 1, "one drawn for that hour"


def test_the_newest_of_a_bucket_is_the_one_kept(
    client: TestClient, db, enrolled, mtls_headers
):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    checkin(
        client,
        headers,
        locations=[
            _report(1440 + 50, latitude=1.0),
            _report(1440 + 5, latitude=2.0),
            _report(1440 + 30, latitude=3.0),
        ],
    )

    drawn = location_service.downsample(location_service.history(db, _device(db).id))

    assert len(drawn) == 1
    assert drawn[0].latitude == 2.0


def test_numbering_starts_at_the_newest_point(
    client: TestClient, db, enrolled, mtls_headers
):
    """#1 is where the device is now and larger numbers walk back, matching the
    reference portal and the question people actually ask."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    checkin(client, headers, locations=[_report(60, latitude=1.0), _report(5, latitude=2.0)])

    drawn = location_service.downsample(location_service.history(db, _device(db).id))

    assert [p.number for p in drawn] == [1, 2]
    assert drawn[0].latitude == 2.0, "number 1 is the newest"


# --------------------------------------------------------------------------- #
# The pages
# --------------------------------------------------------------------------- #


def test_the_device_page_draws_the_last_position(
    client: TestClient, db, enrolled, mtls_headers
):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    checkin(client, headers, locations=[_report(3)])

    body = client.get(f"/devices/{result['device_id']}", headers=ADMIN_HEADERS).text

    assert "data-map-latest" in body
    assert "39.73920" in body, "coordinates to five places"
    assert "leaflet.js" in body


def test_a_device_with_no_position_says_which_silence_it_is(
    client: TestClient, db, enrolled
):
    """⚠️ Nothing-is-collecting sends an operator to the policy; collecting-but-
    nothing-arrived sends them to the device. One message would send them to
    neither."""
    result = enrolled()

    body = client.get(f"/devices/{result['device_id']}", headers=ADMIN_HEADERS).text

    assert "location tracking is not switched on" in body
    assert "data-map-latest" not in body


def test_an_unreported_accuracy_is_not_shown_as_zero(
    client: TestClient, db, enrolled, mtls_headers
):
    """The device not saying is not the device claiming zero metres."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    checkin(client, headers, locations=[_report(3, accuracy_m=None)])

    body = client.get(f"/devices/{result['device_id']}", headers=ADMIN_HEADERS).text

    assert "Not reported by device" in body
    assert "&plusmn;0 m" not in body


def test_a_stale_fix_is_called_out(client: TestClient, db, enrolled, mtls_headers):
    """⚠️ A position from yesterday drawn on a map looks exactly like one from a
    minute ago. The age is the only thing that separates them."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    checkin(client, headers, locations=[_report(minutes_ago=60 * 30)])

    body = client.get(f"/devices/{result['device_id']}", headers=ADMIN_HEADERS).text

    assert "this position may be out of date" in body
    # 30 hours reads as "30 hours ago", not "1 days ago" — the coarser unit is
    # less informative, not more, until the number gets unwieldy.
    assert "30 hours ago" in body


def test_the_history_page_lists_points_newest_first(
    client: TestClient, db, enrolled, mtls_headers
):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    checkin(client, headers, locations=[_report(90), _report(10)])

    body = client.get(
        f"/devices/{result['device_id']}/location-history", headers=ADMIN_HEADERS
    ).text

    assert "data-map-history" in body
    assert body.index('data-point="1"') < body.index('data-point="2"')


def test_a_range_the_wrong_way_round_is_refused_not_swapped(
    client: TestClient, db, enrolled
):
    """⚠️ Swapping would answer a question the operator did not ask, while the
    form went on showing the one they did."""
    result = enrolled()

    body = client.get(
        f"/devices/{result['device_id']}/location-history"
        "?from_mode=date&from_date=2026-01-01&to_date=2026-06-01",
        headers=ADMIN_HEADERS,
    ).text

    assert "must be on or before" in body


def test_an_empty_range_says_so_rather_than_drawing_nothing(
    client: TestClient, db, enrolled
):
    result = enrolled()

    body = client.get(
        f"/devices/{result['device_id']}/location-history", headers=ADMIN_HEADERS
    ).text

    assert "No location points in this range." in body
    assert "no records" in body


def test_the_export_ignores_the_range_and_the_thinning(
    client: TestClient, db, enrolled, mtls_headers
):
    """⚠️ The button says all history. An export that thinned, or honoured the
    window, would hand someone a file they believe is complete and is not."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    checkin(
        client,
        headers,
        locations=[_report(minutes_ago=1440 + off) for off in (0, 10, 20, 30, 40)],
    )

    response = client.get(
        f"/devices/{result['device_id']}/location-history.csv", headers=ADMIN_HEADERS
    )

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    rows = [line for line in response.text.strip().splitlines() if line]
    assert len(rows) == 6, "header plus all five points"
    assert rows[0].startswith("number,recorded_at_utc,received_at_utc")


def test_the_export_is_named_for_the_device(
    client: TestClient, db, enrolled, mtls_headers
):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    checkin(client, headers, locations=[_report(5)])
    serial = _device(db).serial_number

    response = client.get(
        f"/devices/{result['device_id']}/location-history.csv", headers=ADMIN_HEADERS
    )

    assert serial in response.headers["content-disposition"]


def test_tiles_default_to_openstreetmap_and_can_be_replaced(client: TestClient, db):
    """⚠️ A setting because it is a disclosure decision: every tile tells the tile
    server roughly where an operator is looking."""
    from app.services import settings_store

    assert location_service.tile_config(db)["tileUrl"] == location_service.DEFAULT_TILE_URL

    settings_store.put(db, "location.tile_url", "https://tiles.internal/{z}/{x}/{y}.png")
    db.commit()

    config = location_service.tile_config(db)
    assert config["tileUrl"] == "https://tiles.internal/{z}/{x}/{y}.png"
    assert config["tileAttribution"] == "", "no OSM credit on someone else's tiles"


# --------------------------------------------------------------------------- #
# ⚠️ Retention (C5) — the only thing here that destroys data
# --------------------------------------------------------------------------- #
#
# Everything else in W106 is additive. This deletes operator data unattended, on
# a timer, permanently, and nobody watches it do so. The tests are therefore
# weighted towards what must *not* happen rather than what must.


def _store(db, device, minutes_ago: float, **over):
    """Insert a point directly, so ages far past any check-in are reachable."""
    from app.db.models import DeviceLocation, LocationSource

    point = DeviceLocation(
        device_id=device.id,
        latitude=over.get("latitude", 39.7392),
        longitude=over.get("longitude", -104.9903),
        accuracy_m=5.0,
        provider="gps",
        recorded_at=_now() - timedelta(minutes=minutes_ago),
        received_at=_now(),
        source=LocationSource.PERIODIC,
    )
    db.add(point)
    db.flush()
    return point


def test_points_past_the_window_are_removed(client: TestClient, db, enrolled):
    enrolled()
    device = _device(db)
    _store(db, device, minutes_ago=60 * 24 * 40)  # 40 days
    _store(db, device, minutes_ago=60 * 24 * 10)  # 10 days

    removed = location_service.purge(db, days=30)
    db.commit()

    assert removed == 1
    assert len(_points(db)) == 1


def test_the_default_window_is_thirty_days(client: TestClient, db, enrolled):
    """What the operator asked for, and what applies when nobody sets anything."""
    enrolled()

    assert location_service.DEFAULT_RETENTION_DAYS == 30
    assert location_service.retention_days(db) == 30


def test_the_setting_overrides_the_default(client: TestClient, db, enrolled):
    from app.services import settings_store

    enrolled()
    device = _device(db)
    _store(db, device, minutes_ago=60 * 24 * 10)  # 10 days old
    settings_store.put(db, location_service.RETENTION_KEY, "7")
    db.commit()

    assert location_service.retention_days(db) == 7
    assert location_service.purge(db) == 1


def test_zero_keeps_everything_rather_than_deleting_everything(
    client: TestClient, db, enrolled
):
    """⚠️ The polarity trap, and the reason it is spelled this way.

    A tracking policy's `reporting_interval_minutes` uses 0 for *off*, so someone
    could read 0 here as "no retention" and mean "keep nothing". It means keep
    everything — and that is the reading chosen deliberately, because misread as
    "keep for ever" it costs disk, while misread the other way it would silently
    destroy a fleet's history with no way back.
    """
    from app.services import settings_store

    enrolled()
    device = _device(db)
    _store(db, device, minutes_ago=60 * 24 * 3650)  # ten years old
    settings_store.put(db, location_service.RETENTION_KEY, "0")
    db.commit()

    assert location_service.purge(db) == 0
    assert len(_points(db)) == 1, "nothing was deleted"


def test_a_nonsense_setting_falls_back_to_the_default_not_to_zero(
    client: TestClient, db, enrolled
):
    """⚠️ The settings row is a text column an operator types into.

    Reading "thirty" as 0 would compute a cutoff of *now* and take the whole
    table. It falls back to the documented default instead, and says so.
    """
    from app.services import settings_store

    enrolled()
    device = _device(db)
    _store(db, device, minutes_ago=60 * 24 * 5)  # 5 days: inside 30

    for junk in ("thirty", "", "  ", "-1", "12.5", "30 days"):
        settings_store.put(db, location_service.RETENTION_KEY, junk)
        db.commit()
        assert location_service.retention_days(db) == 30, junk
        assert location_service.purge(db) == 0, junk

    assert len(_points(db)) == 1, "a typo never emptied the table"


def test_recent_points_are_never_touched(client: TestClient, db, enrolled):
    enrolled()
    device = _device(db)
    for age_days in (0, 1, 5, 29):
        _store(db, device, minutes_ago=60 * 24 * age_days)

    assert location_service.purge(db, days=30) == 0
    assert len(_points(db)) == 4


def test_retention_reads_the_fix_time_not_the_delivery_time(
    client: TestClient, db, enrolled, mtls_headers
):
    """⚠️ A point delivered late is still as old as the console says it is.

    Deleting on `received_at` would keep a point the page shows as three months
    old, because it happened to arrive yesterday — a discrepancy nobody could
    account for from the page they are looking at.
    """
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    # Recorded 90 days ago, received just now.
    checkin(client, headers, locations=[_report(minutes_ago=60 * 24 * 90)])
    point = _points(db)[0]
    assert (point.received_at - point.recorded_at) > timedelta(days=89)

    assert location_service.purge(db, days=30) == 1


def test_the_purge_only_ever_touches_locations(
    client: TestClient, db, enrolled, mtls_headers
):
    """⚠️ A track is the most personal thing stored here, and also the only thing
    this job is allowed to remove."""
    from sqlalchemy import func, select as sa_select

    from app.db.models import Device, DeviceCommand

    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    enqueue(client, result["device_id"], "locate")
    checkin(client, headers)
    device = _device(db)
    _store(db, device, minutes_ago=60 * 24 * 90)

    devices_before = db.scalar(sa_select(func.count()).select_from(Device))
    commands_before = db.scalar(sa_select(func.count()).select_from(DeviceCommand))

    location_service.purge(db, days=30)
    db.commit()

    assert db.scalar(sa_select(func.count()).select_from(Device)) == devices_before
    assert db.scalar(sa_select(func.count()).select_from(DeviceCommand)) == commands_before
    assert _points(db) == []


def test_the_sweeper_does_not_run_in_tests():
    """⚠️ Not a nicety. A background thread reading the real settings during a
    test run would aim real DELETEs at a real table — the index warm-up already
    taught this lesson the cheaper way, by fetching 184 MB per run."""
    from app.config import Settings

    assert Settings().purge_location_history is True, "on by default in production"

    from tests.conftest import ADMIN_HEADERS  # noqa: F401  (import shape check)
    from app.main import _start_location_retention
    from fastapi import FastAPI
    from app.config import get_settings

    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: Settings(
        purge_location_history=False
    )

    assert _start_location_retention(app) is None, "gated off, no thread started"


# --------------------------------------------------------------------------- #
# Geofencing (C4)
# --------------------------------------------------------------------------- #


def _fence_form(rows: list[dict]) -> list[tuple[str, str]]:
    """The form encoding the geofence editor produces, checkbox pairing included.

    ⚠️ The screen lock is a **select**, not a checkbox, so it submits on every row. That is what keeps positional pairing honest: an unchecked checkbox
    submits nothing at all and would shift every later row's setting onto the
    wrong fence.
    """
    fields: list[tuple[str, str]] = []
    for row in rows:
        fields.append(("geofences__name", row.get("name", "")))
        fields.append(("geofences__latitude", str(row.get("latitude", ""))))
        fields.append(("geofences__longitude", str(row.get("longitude", ""))))
        fields.append(("geofences__radius_m", str(row.get("radius_m", 200))))
        fields.append(("geofences__trigger", row.get("trigger", "entry")))
        fields.append(("geofences__wifi", row.get("wifi", "unmanaged")))
        fields.append(("geofences__bluetooth", row.get("bluetooth", "unmanaged")))
        fields.append((
            "geofences__reporting_interval_override_minutes",
            str(row.get("override", 0)),
        ))
        fields.append(("geofences__password", row.get("password") or "none"))
    return fields


def _parse_fences(rows: list[dict]) -> list[dict]:
    from starlette.datastructures import FormData

    from app.policies import form_parse

    form = FormData(_fence_form(rows))
    spec = form_parse.parse_form("TRACKING_FENCING", form)
    return spec.get("geofences", [])


def test_a_geofence_round_trips_through_the_form(client: TestClient):
    parsed = _parse_fences([
        {"name": "Vault", "latitude": 33.6236, "longitude": -117.127,
         "radius_m": 150, "trigger": "entry", "wifi": "off",
         "bluetooth": "on", "override": 2, "password": "on"}
    ])

    assert len(parsed) == 1
    fence = parsed[0]
    assert fence["name"] == "Vault"
    assert fence["wifi"] == "off"
    assert fence["bluetooth"] == "on"
    assert fence["password"] == "on"
    assert str(fence["reporting_interval_override_minutes"]) == "2"


def test_a_lock_setting_does_not_shift_onto_the_next_fence(client: TestClient):
    """⚠️ The bug this shape of form invites, and why the control is a select.

    A checkbox submits nothing when unticked, so paired by position every fence
    after the first would inherit the next one's setting — a device demanding a
    lock because of a fence that never asked, or worse, *suspending* one because
    of a fence that did not say so. A select always submits, so positions align.
    """
    parsed = _parse_fences([
        {"name": "one", "latitude": 1.0, "longitude": 1.0, "password": "none"},
        {"name": "two", "latitude": 2.0, "longitude": 2.0, "password": "on"},
        {"name": "three", "latitude": 3.0, "longitude": 3.0, "password": "off"},
    ])

    assert [f["name"] for f in parsed] == ["one", "two", "three"]
    assert [f["password"] for f in parsed] == ["none", "on", "off"]


def test_a_half_typed_row_is_dropped_rather_than_refused(client: TestClient):
    """The row an operator added and did not fill in should not cost them the
    rest of the form."""
    parsed = _parse_fences([
        {"name": "real", "latitude": 33.6, "longitude": -117.1},
        {"name": "", "latitude": "", "longitude": ""},
    ])

    assert len(parsed) == 1
    assert parsed[0]["name"] == "real"


def test_two_fences_cannot_share_a_name(client: TestClient):
    """⚠️ The name is the merge key across stacked policies, so a duplicate would
    silently collapse two fences into one."""
    parsed = _parse_fences([
        {"name": "Zone", "latitude": 1.0, "longitude": 1.0},
        {"name": "Zone", "latitude": 2.0, "longitude": 2.0},
    ])

    assert len({f["name"] for f in parsed}) == 2


def test_a_geofence_policy_saves_and_reaches_the_device(
    client: TestClient, db, enrolled, mtls_headers
):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    policy = client.post(
        "/api/v1/policies",
        json={
            "name": "vault-fence",
            "policy_type": "TRACKING_FENCING",
            "spec": {
                "reporting_interval_minutes": 5,
                "geofences": [
                    {
                        "name": "Vault",
                        "latitude": 33.6236,
                        "longitude": -117.127,
                        "radius_m": 150,
                        "trigger": "entry",
                        "wifi": "off",
                    }
                ],
            },
        },
    )
    assert policy.status_code == 201, policy.text
    client.post(
        "/api/v1/assignments",
        json={
            "policy_id": policy.json()["id"],
            "scope": "device",
            "target_id": result["device_id"],
            "rank": 1,
        },
    )

    body = checkin(client, headers, force_full=True)
    section = body["desired_state"]["policy"]["TRACKING_FENCING"]

    assert section["geofences"][0]["name"] == "Vault"
    assert section["geofences"][0]["wifi"] == "off"


def test_a_fence_tighter_than_a_gps_fix_is_refused(client: TestClient):
    """⚠️ A 5 m fence would flap between inside and outside while the device sat
    still, applying and releasing its actions on every sample."""
    response = client.post(
        "/api/v1/policies",
        json={
            "name": "too-tight",
            "policy_type": "TRACKING_FENCING",
            "spec": {
                "geofences": [
                    {"name": "pin", "latitude": 1.0, "longitude": 1.0, "radius_m": 5}
                ]
            },
        },
    )

    assert response.status_code == 422


def test_an_impossible_fence_centre_is_refused(client: TestClient):
    response = client.post(
        "/api/v1/policies",
        json={
            "name": "off-world",
            "policy_type": "TRACKING_FENCING",
            "spec": {
                "geofences": [
                    {"name": "nowhere", "latitude": 91.0, "longitude": 0.0,
                     "radius_m": 500}
                ]
            },
        },
    )

    assert response.status_code == 422


def test_the_geofence_editor_warns_about_turning_wifi_off(client: TestClient):
    """⚠️ Turning the radio off also cuts the path used to tell it to come back.
    The console says so where the choice is made, not in a document."""
    body = client.get("/policies/new").text
    panel = body[body.index('data-page-panel="tracking_fencing:geofencing"'):]
    panel = panel[: panel.index("</section>")]

    assert "cuts the path" in panel
    # Wrapped across lines in the source, so match a phrase that cannot span it.
    assert "prompt whoever" in panel


def test_the_editor_uses_a_select_so_every_row_submits(client: TestClient):
    """The structural guarantee behind positional pairing, asserted on the markup
    rather than only on the parser."""
    body = client.get("/policies/new").text
    panel = body[body.index("data-geofences"):]
    panel = panel[: panel.index("</template>")]

    assert 'name="geofences__password"' in panel
    assert 'value="none"' in panel and 'value="off"' in panel and 'value="on"' in panel


# --------------------------------------------------------------------------- #
# ⚠️ A geofence lock needs a password policy beside it
# --------------------------------------------------------------------------- #
#
# Operator, 2026-09-08: "can we mandate that it be tied to the password policy if
# enabled? as in it requires a password policy be set in the same policy before it
# allows the geofence lock?"
#
# The hole it closes: a fence's requirement is a floor — "some lock". With a
# PASSWORD policy beside it that floor is the operator's own rule. Without one it
# is the only thing in play, so the device asks whoever is holding it to invent a
# PIN, and what they invent becomes the fleet's password policy.


def _fence(password: bool = True, name: str = "Vault") -> dict:
    return {
        "name": name,
        "latitude": 33.6236,
        "longitude": -117.127,
        "radius_m": 150,
        "trigger": "entry",
        "password_enforced": password,
    }


def _profile(client: TestClient, name: str, sections: dict):
    from starlette.datastructures import FormData

    return sections  # sections are exercised through the service directly below


def test_a_lone_fence_may_not_demand_a_lock(client: TestClient):
    """⚠️ A standalone policy has nothing it travels with.

    A PASSWORD policy assigned separately would also reach the device, but it can
    be unassigned on its own — leaving the fence demanding a lock with no rule
    behind it, which is the state being prevented.
    """
    response = client.post(
        "/api/v1/policies",
        json={
            "name": "lone-fence",
            "policy_type": "TRACKING_FENCING",
            "spec": {"geofences": [_fence()]},
        },
    )

    assert response.status_code == 422
    assert "Password policy" in response.text


def test_the_same_fence_without_a_lock_is_fine(client: TestClient):
    """The rule is about the lock, not about fences."""
    response = client.post(
        "/api/v1/policies",
        json={
            "name": "lone-fence-no-lock",
            "policy_type": "TRACKING_FENCING",
            "spec": {"geofences": [_fence(password=False)]},
        },
    )

    assert response.status_code == 201


def test_a_profile_with_both_sections_is_allowed(client: TestClient, db):
    from app.services import profiles as profile_service

    profile = profile_service.create_profile(
        db,
        name="fenced-and-locked",
        description=None,
        sections={
            "password": {"quality": 4, "min_length": 6},
            "tracking_fencing": {"geofences": [_fence()]},
        },
    )
    db.commit()

    assert profile_service.section_for(profile, "tracking_fencing") is not None
    assert profile_service.section_for(profile, "password") is not None


def test_a_profile_missing_the_password_section_is_refused(client: TestClient, db):
    from app.services import profiles as profile_service

    try:
        profile_service.create_profile(
            db,
            name="fenced-only",
            description=None,
            sections={"tracking_fencing": {"geofences": [_fence()]}},
        )
        raise AssertionError("should have been refused")
    except profile_service.ProfileError as exc:
        assert "Password policy" in str(exc)
        assert "Vault" in str(exc), "names the fence, so it can be found"


def test_adding_a_locking_fence_to_a_profile_without_a_password_is_refused(
    client: TestClient, db
):
    """⚠️ Judged against the profile as it *will* be. Reading the section back
    from the database would check the previous version and let the new one
    through."""
    from app.services import profiles as profile_service

    profile = profile_service.create_profile(
        db, name="later-fence", description=None, sections={}
    )
    db.commit()

    try:
        profile_service.upsert_section(
            db, profile, "tracking_fencing", {"geofences": [_fence()]}
        )
        raise AssertionError("should have been refused")
    except profile_service.ProfileError as exc:
        assert "Password policy" in str(exc)


def test_removing_the_password_section_is_refused_while_a_fence_needs_it(
    client: TestClient, db
):
    """⚠️ The check that looks unnecessary and is not.

    Every other one runs while the operator is looking at geofences. This fires
    from a different tab, minutes later, with the thing it protects nowhere on
    screen — and without it the rule is satisfied once and then deleted.
    """
    from app.services import profiles as profile_service

    profile = profile_service.create_profile(
        db,
        name="remove-me",
        description=None,
        sections={
            "password": {"quality": 4, "min_length": 6},
            "tracking_fencing": {"geofences": [_fence()]},
        },
    )
    db.commit()

    try:
        profile_service.remove_section(db, profile, "password")
        raise AssertionError("should have been refused")
    except profile_service.ProfileError as exc:
        assert "cannot be removed" in str(exc)


def test_the_password_section_can_go_once_no_fence_needs_it(client: TestClient, db):
    from app.services import profiles as profile_service

    profile = profile_service.create_profile(
        db,
        name="release-then-remove",
        description=None,
        sections={
            "password": {"quality": 4, "min_length": 6},
            "tracking_fencing": {"geofences": [_fence()]},
        },
    )
    db.commit()

    profile_service.upsert_section(
        db, profile, "tracking_fencing", {"geofences": [_fence(password=False)]}
    )
    profile_service.remove_section(db, profile, "password")
    db.commit()

    assert profile_service.section_for(profile, "password") is None


def test_an_empty_password_section_does_not_count(client: TestClient, db):
    """⚠️ A section that exists but says nothing defines exactly as little as no
    section at all, which is the thing being guarded against."""
    from app.policies import fence_rules

    assert fence_rules.violation({"geofences": [_fence()]}, {}) is not None
    assert fence_rules.violation({"geofences": [_fence()]}, None) is not None
    assert fence_rules.violation({"geofences": [_fence()]}, {"quality": 4}) is None


def test_a_string_true_from_the_form_counts_as_enforced():
    """⚠️ Called on raw form output as well as validated specs. Reading "true" as
    falsey would pass the check on a value the model then coerces to True."""
    from app.policies import fence_rules

    for raw in ("true", "yes", "1", "on", "True"):
        assert fence_rules.password_fences(
            {"geofences": [{"name": "x", "password_enforced": raw}]}
        ) == ["x"]
    for raw in ("false", "no", "0", ""):
        assert fence_rules.password_fences(
            {"geofences": [{"name": "x", "password_enforced": raw}]}
        ) == []


def test_the_console_says_why_the_lock_is_unavailable(client: TestClient):
    body = client.get("/policies/new").text

    assert "data-fence-lock-note" in body
    assert "needs a Password policy in this same profile" in body


def test_the_greyed_control_still_submits(client: TestClient):
    """⚠️ Greyed, never `disabled` — a disabled select submits nothing, and these
    rows pair by position, so one would shift every later fence's setting onto the
    wrong row."""
    script = (
        pathlib.Path("app/web/static/atlas.js").read_text(encoding="utf-8")
    )
    fence_block = script[script.index("function atlasWireFenceLock"):]

    assert 'classList.toggle("greyed"' in fence_block
    assert ".disabled = true" not in fence_block


def test_the_remove_button_reports_the_refusal_instead_of_failing(
    client: TestClient, db
):
    """⚠️ The one path that did not catch it, and the one an operator would use.

    The Remove button on the Password tab would have raised straight through the
    route — a 500 on exactly the check that exists to protect the geofence lock.
    """
    from app.services import profiles as profile_service

    profile = profile_service.create_profile(
        db,
        name="remove-via-button",
        description=None,
        sections={
            "password": {"quality": 4, "min_length": 6},
            "tracking_fencing": {"geofences": [_fence()]},
        },
    )
    db.commit()

    response = client.post(
        f"/profiles/{profile.id}/sections/password/remove",
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )

    assert response.status_code in (302, 303)
    assert "cannot be removed" in unquote(response.headers["location"])
    db.expire_all()
    assert profile_service.section_for(
        profile_service.get_profile(db, profile.id), "password"
    ) is not None, "the section survived"


def test_the_api_refuses_the_removal_with_a_status_not_a_traceback(
    client: TestClient, db
):
    from app.services import profiles as profile_service

    profile = profile_service.create_profile(
        db,
        name="remove-via-api",
        description=None,
        sections={
            "password": {"quality": 4, "min_length": 6},
            "tracking_fencing": {"geofences": [_fence()]},
        },
    )
    db.commit()

    response = client.delete(f"/api/v1/profiles/{profile.id}/sections/password")

    assert response.status_code == 409
    assert "cannot be removed" in response.text


def test_clearing_both_in_one_save_is_allowed(client: TestClient, db):
    """⚠️ Upserts before removals, or a legal end state gets refused.

    Catalog order puts Password before Tracking and fencing, so a save that both
    clears the Password section and releases the fence needing it would otherwise
    delete the section while the fence still demanded one — refusing a change
    whose result is perfectly valid.
    """
    from app.services import profiles as profile_service

    profile = profile_service.create_profile(
        db,
        name="clear-both",
        description=None,
        sections={
            "password": {"quality": 4, "min_length": 6},
            "tracking_fencing": {"geofences": [_fence()]},
        },
    )
    db.commit()

    # The whole-profile save: the fence keeps existing but stops demanding a
    # lock, and the Password section is emptied — both in one submission.
    form = {
        "geofences__name": "Vault",
        "geofences__latitude": "33.6236",
        "geofences__longitude": "-117.127",
        "geofences__radius_m": "150",
        "geofences__trigger": "entry",
        "geofences__wifi": "unmanaged",
        "geofences__bluetooth": "unmanaged",
        "geofences__reporting_interval_override_minutes": "0",
        "geofences__password_enforced": "no",
    }
    response = client.post(
        f"/profiles/{profile.id}",
        data=form,
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )

    assert response.status_code in (302, 303)
    assert "error" not in response.headers["location"], unquote(
        response.headers["location"]
    )

    db.expire_all()
    fresh = profile_service.get_profile(db, profile.id)
    assert profile_service.section_for(fresh, "password") is None
    assert profile_service.section_for(fresh, "tracking_fencing") is not None


# --------------------------------------------------------------------------- #
# ⚠️ Trusted areas: suspending the passcode this system set (W111)
# --------------------------------------------------------------------------- #


def test_the_old_boolean_still_reads(client: TestClient):
    """⚠️ Stored specs are not migrated when a model changes.

    Every fence written before this field became three-state is still in the
    database. Without the compatibility read they would fail validation the next
    time a policy was resolved — surfacing as a device that cannot get its
    policy, with nothing in the error mentioning geofences.
    """
    from app.policies.specs.tracking_fencing import Geofence

    base = dict(name="HQ", latitude=33.6, longitude=-117.1, radius_m=200)

    assert Geofence(**base, password_enforced=True).password.value == "on"
    assert Geofence(**base, password_enforced=False).password.value == "none"
    assert Geofence(**base).password.value == "none"


def test_a_trusted_area_needs_a_passcode_to_restore(client: TestClient, db):
    """⚠️ The condition that makes this safe at all.

    Suspending works by clearing the passcode *this policy set* and putting it
    back on the way out. Where the user chose their own PIN there is nothing to
    put back — and clearing it would strand them without their own credential.
    """
    from app.policies import fence_rules

    trusted = {"geofences": [{"name": "Base", "password": "off"}]}

    assert fence_rules.violation(trusted, None) is not None
    assert fence_rules.violation(trusted, {"quality": 4}) is not None, (
        "a password policy that sets no passcode is not enough"
    )
    assert fence_rules.violation(trusted, {"set_password": "246810"}) is None


def test_the_refusal_explains_what_is_missing(client: TestClient, db):
    from app.policies import fence_rules

    message = fence_rules.violation(
        {"geofences": [{"name": "Base", "password": "off"}]}, {"quality": 4}
    )

    assert "suspends the passcode" in message
    assert "nothing to restore" in message


def test_a_lone_trusted_fence_is_refused_by_the_api(client: TestClient):
    response = client.post(
        "/api/v1/policies",
        json={
            "name": "lone-trusted",
            "policy_type": "TRACKING_FENCING",
            "spec": {
                "geofences": [
                    {"name": "Base", "latitude": 33.6, "longitude": -117.1,
                     "radius_m": 500, "password": "off"}
                ]
            },
        },
    )

    assert response.status_code == 422
    assert "Password" in response.text


def test_a_profile_with_a_set_passcode_accepts_a_trusted_area(client: TestClient, db):
    from app.services import profiles as profile_service

    profile = profile_service.create_profile(
        db,
        name="trusted-base",
        description=None,
        sections={
            "password": {"quality": 2, "min_length": 6, "set_password": "246810"},
            "tracking_fencing": {
                "geofences": [
                    {"name": "Base", "latitude": 33.6, "longitude": -117.1,
                     "radius_m": 500, "password": "off"}
                ]
            },
        },
    )
    db.commit()

    assert profile_service.section_for(profile, "tracking_fencing") is not None


def test_removing_the_passcode_policy_is_refused_while_a_fence_suspends_it(
    client: TestClient, db
):
    """⚠️ The same trap as W106 C4a, one level subtler: deleting the Password
    section would leave a fence trying to restore a passcode that no longer
    exists."""
    from app.services import profiles as profile_service

    profile = profile_service.create_profile(
        db,
        name="trusted-then-removed",
        description=None,
        sections={
            "password": {"quality": 2, "min_length": 6, "set_password": "246810"},
            "tracking_fencing": {
                "geofences": [
                    {"name": "Base", "latitude": 33.6, "longitude": -117.1,
                     "radius_m": 500, "password": "off"}
                ]
            },
        },
    )
    db.commit()

    try:
        profile_service.remove_section(db, profile, "password")
        raise AssertionError("should have been refused")
    except profile_service.ProfileError as exc:
        assert "cannot be removed" in str(exc)


def test_the_editor_offers_three_states(client: TestClient):
    body = client.get("/policies/new").text
    panel = body[body.index('data-page-panel="tracking_fencing:geofencing"'):]
    panel = panel[: panel.index("</section>")]

    assert 'name="geofences__password"' in panel
    for value in ("none", "off", "on"):
        assert f'value="{value}"' in panel


def test_the_editor_says_what_off_cannot_do(client: TestClient):
    """⚠️ An operator reading "Off" will assume it defeats any lock. It does not,
    and the console has to say so where the choice is made."""
    body = client.get("/policies/new").text

    assert "cannot remove a PIN the user chose" in body
    assert "restores it" in body


def test_the_trusted_area_fails_secure_when_position_is_stale(client: TestClient):
    """⚠️ The edge that decides whether this is safe.

    A device that lost GPS indoors, or was carried out of the zone in a bag,
    would otherwise sit unlocked on a fix from hours ago — and nothing would look
    wrong from the console.
    """
    tracker = pathlib.Path(
        "agent/app/src/main/java/com/taksolutions/atlasmdm/policy/LocationTracker.kt"
    ).read_text(encoding="utf-8")

    assert "TRUSTED_FIX_MAX_AGE_MS" in tracker
    assert "actions.copy(lock = GeofencePlan.Lock.NONE)" in tracker
    # Not derived from the reporting interval: a long interval set for battery
    # must not buy a longer unlocked window.
    assert "10 * 60 * 1000L" in tracker


def test_the_passcode_is_cleared_only_after_the_constraints_are_released(
    client: TestClient,
):
    """⚠️ AOSP clears a passcode only "if the current password constraints allow
    it". Called before the release it is refused, returns false, and the device
    stays locked with nothing to say why."""
    reconciler = pathlib.Path(
        "agent/app/src/main/java/com/taksolutions/atlasmdm/sync/Reconciler.kt"
    ).read_text(encoding="utf-8")

    apply_at = reconciler.index("errors += policyApplier.apply(policy)")
    clear_at = reconciler.index("clearPasscodeForTrustedArea")

    assert apply_at < clear_at, "the clear must come after the policy is applied"
