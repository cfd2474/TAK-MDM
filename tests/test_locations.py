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
from datetime import datetime, timedelta, timezone

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


def test_geofencing_says_it_is_coming_rather_than_offering_a_form(client: TestClient):
    """D94: hidden instead, an operator would read it as forgotten."""
    body = client.get("/policies/new").text
    panel = body[body.index('data-page-panel="tracking_fencing:geofencing"'):]
    panel = panel[: panel.index("</section>")]

    assert "Not available yet." in panel


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
