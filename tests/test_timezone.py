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

"""What time the console says it is (W163).

⚠️ **The dangerous failure here is not a crash.** A missed template keeps printing
UTC beside times that have become local, and a page showing two zones with nothing
to distinguish them is worse than the all-UTC page it replaced. So the scan below
matters more than any single rendering assertion: it is what makes "every
timestamp goes through the filter" a fact rather than an intention.
"""

from __future__ import annotations

import io
import pathlib
import re

import pytest
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.services import clock
from tests.conftest import ADMIN_HEADERS

TEMPLATES = pathlib.Path("app/web/templates")


def _stored_point(db):
    """The location row the page is actually rendering.

    ⚠️ Assertions compare against this rather than against `datetime.now()`.
    A point recorded minutes ago and the current clock can sit either side of an
    hour boundary, and a test that depends on what time it is run produces
    failures that look like bugs in the code.
    """
    from app.db.models import DeviceLocation

    point = db.scalars(
        select(DeviceLocation).order_by(DeviceLocation.recorded_at.desc())
    ).first()
    assert point is not None, "no location was stored for this test to check"
    return point



# --------------------------------------------------------------------------- #
# The service
# --------------------------------------------------------------------------- #


def test_the_default_is_utc():
    """An unconfigured deployment renders exactly what it did before this existed."""
    assert clock.DEFAULT_TIMEZONE == "UTC"
    assert clock.zone(None) is clock.UTC
    assert clock.zone("") is clock.UTC
    assert clock.zone("   ") is clock.UTC
    assert clock.zone("UTC") is clock.UTC


def test_a_real_zone_shifts_the_clock():
    instant = datetime(2026, 1, 15, 19, 30, tzinfo=timezone.utc)

    assert clock.format(instant, clock.zone("America/Denver"), "%Y-%m-%d %H:%M") == (
        "2026-01-15 12:30"
    )
    assert clock.format(instant, clock.zone("Asia/Tokyo"), "%Y-%m-%d %H:%M") == (
        "2026-01-16 04:30"
    )


def test_daylight_saving_is_handled_on_both_sides():
    """⚠️ A fixed offset would be right for half the year and quietly wrong for the
    other half — the kind of error nobody reports because it looks plausible."""
    denver = clock.zone("America/Denver")
    winter = datetime(2026, 1, 15, 19, 0, tzinfo=timezone.utc)
    summer = datetime(2026, 7, 15, 19, 0, tzinfo=timezone.utc)

    assert clock.format(winter, denver, "%H:%M %Z") == "12:00 MST"
    assert clock.format(summer, denver, "%H:%M %Z") == "13:00 MDT"


def test_an_unknown_zone_falls_back_to_utc_rather_than_raising():
    """⚠️ This runs on every page render.

    A zone name is a string, and the IANA database does retire names. Raising here
    would not mean a wrong time on one page — it would mean the whole console
    returning 500 until someone with database access edited a settings row.
    """
    for junk in ("Mars/Olympus_Mons", "America/Nowhere", "../../etc/passwd", "EST5EDT!"):
        assert clock.zone(junk) is clock.UTC, junk


def test_a_naive_timestamp_is_read_as_utc_not_as_the_servers_zone():
    """⚠️ Letting Python attach the host's local zone is a bug that looks like
    correct behaviour on a machine set to UTC.

    ⚠️ **And this test shares that blind spot**, which is worth knowing rather
    than discovering: on a host whose local zone is UTC it passes whether the code
    reads naive timestamps as UTC or as local, because the two agree. It was
    mutation-checked on a host at UTC-7, where they do not. That is the reason the
    code says `replace(tzinfo=UTC)` explicitly instead of relying on a default —
    the test cannot be trusted to catch it everywhere it runs.
    """
    naive = datetime(2026, 1, 15, 19, 30)

    assert clock.format(naive, clock.zone("America/Denver"), "%H:%M") == "12:30"


def test_an_absent_timestamp_renders_as_nothing():
    assert clock.format(None, clock.zone("America/Denver"), "%H:%M") == ""


def test_utc_leads_the_zone_list():
    zones = clock.available()

    assert zones[0] == "UTC"
    assert "America/Denver" in zones
    assert zones[1:] == sorted(zones[1:]), "the rest stay alphabetical"


# --------------------------------------------------------------------------- #
# The console
# --------------------------------------------------------------------------- #


def test_the_general_tab_is_first_and_is_where_admin_lands(client: TestClient):
    body = client.get("/admin", headers=ADMIN_HEADERS).text

    tabs = re.findall(r'data-tab="([a-z]+)"', body) or re.findall(
        r'href="#tab-([a-z]+)"', body
    )
    assert tabs, "no tabs found; the selector in this test needs updating"
    assert tabs[0] == "general", tabs[:4]
    assert tabs[1] == "certificates", tabs[:4]

    # The landing panel is the one that is not hidden.
    visible = re.findall(r'<div class="tab-panel" data-tab-panel="([a-z]+)"(?![^>]*hidden)', body)
    assert visible == ["general"], visible


def test_the_timezone_field_is_a_dropdown_of_real_zones(client: TestClient):
    body = client.get("/admin", headers=ADMIN_HEADERS).text

    select = re.search(
        r'<select[^>]*name="general\.timezone".*?</select>', body, re.S
    )
    assert select, "the timezone field did not render as a dropdown"
    block = select.group(0)
    assert '<option value="UTC" selected>' in block, "UTC is the default and is selected"
    assert '<option value="America/Denver"' in block
    assert block.count("<option") > 100, "the whole IANA list should be offered"


def test_setting_the_zone_changes_what_the_console_prints(
    client: TestClient, db, enrolled, mtls_headers
):
    """The operator's actual ask, end to end."""
    from tests.test_checkin import checkin
    from tests.test_locations import _report

    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    # With a position, so the Location card renders its timestamp — one of the
    # `%Z` sites, which is where the zone is actually named on the page.
    checkin(client, headers, locations=[_report(2)])

    device_url = f"/devices/{result['device_id']}"
    utc_page = client.get(device_url, headers=ADMIN_HEADERS).text
    assert "UTC" in utc_page

    client.post(
        "/admin/settings/general",
        data={"general.timezone": "America/Denver"},
        follow_redirects=False,
    )

    local_page = client.get(device_url, headers=ADMIN_HEADERS).text
    # %Z prints the zone's own abbreviation, so the page names the zone it is in
    # rather than leaving the reader to assume.
    assert "MST" in local_page or "MDT" in local_page, "the page still reads UTC"


def test_location_history_follows_the_setting(client: TestClient, db, enrolled, mtls_headers):
    """Named in the request, and the page where a wrong zone misleads most:
    a track is read as a sequence of times."""
    from tests.test_checkin import checkin
    from tests.test_locations import _report

    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    checkin(client, headers, locations=[_report(5)])

    client.post(
        "/admin/settings/general",
        data={"general.timezone": "Asia/Tokyo"},
        follow_redirects=False,
    )

    page = client.get(
        f"/devices/{result['device_id']}/location-history", headers=ADMIN_HEADERS
    ).text
    # ⚠️ The **hour**, not just the date. This asserted a `%Y-%m-%d` string until
    # W165, which is true of UTC and Tokyo alike whenever the two share a date —
    # so it passed throughout the whole period the page was wrong.
    #
    # ⚠️ And measured against the *stored point*, not against `now`. Taking the
    # hour from the clock made this fail whenever the two fell either side of an
    # hour boundary: a test that passes depending on what time it is run is worse
    # than no test, because the failure looks like a bug in the code.
    tokyo = clock.format(
        _stored_point(db).recorded_at, clock.zone("Asia/Tokyo"), "%Y-%m-%d %H:"
    )
    assert tokyo in page, "the history table is not in the configured zone"


def test_a_retired_zone_name_is_kept_rather_than_silently_reassigned(client: TestClient, db):
    """⚠️ Rendering only the known choices would re-point the console at the first
    entry in the list the moment someone opened this page to change something
    else — a silent change of a setting they did not touch."""
    from app.services import settings_store

    settings_store.put(db, clock.SETTING_KEY, "America/Nowhere")
    db.commit()

    body = client.get("/admin", headers=ADMIN_HEADERS).text

    assert '<option value="America/Nowhere" selected>' in body
    assert "no longer a known zone" in body


# --------------------------------------------------------------------------- #
# The guard
# --------------------------------------------------------------------------- #


def test_no_template_formats_a_timestamp_behind_the_filters_back():
    """⚠️ The whole point of the filter, enforced.

    A template calling `.strftime()` directly does not fail — it prints UTC, next
    to times that are local, with nothing to say which is which. That is a worse
    page than the all-UTC one this replaced, and it is invisible in review because
    the line looks exactly like the twenty-two that were correct until W163.
    """
    offenders = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        for number, line in enumerate(io.open(path, encoding="utf-8"), 1):
            if ".strftime(" in line:
                offenders.append(f"{path}:{number}: {line.strip()}")

    assert not offenders, (
        "these render a timestamp without |localtime, so they will print UTC:\n"
        + "\n".join(offenders)
    )


# --------------------------------------------------------------------------- #
# ⚠️ What W163 missed: the timestamps Python formats (W165)
#
# The filter covered the templates and a scan enforced it, and the operator still
# found UTC on the location-history page — because the map popups beside the table
# are built in `routes.py`, and reports render pre-formatted strings. A guard that
# only looks where you already looked finds nothing.
# --------------------------------------------------------------------------- #

APP = pathlib.Path("app")

#: A `.strftime(` in app code is allowed only where the zone is deliberate and
#: said out loud. The marker goes on or just above the line.
_UTC_MARKER = "utc-by-design"


def test_no_python_formats_a_timestamp_outside_the_clock_service():
    """⚠️ The companion to the template scan, and the half that was missing.

    `clock.py` is the one place allowed to call `strftime`. Anywhere else, a
    timestamp formatted in Python is one the display zone cannot reach — and it
    will sit next to one that it can, on the same page, labelled neither.
    """
    offenders = []
    for path in sorted(APP.rglob("*.py")):
        if path == pathlib.Path("app/services/clock.py"):
            continue
        lines = io.open(path, encoding="utf-8").read().splitlines()
        for number, line in enumerate(lines, 1):
            if ".strftime(" not in line:
                continue
            stripped = line.strip()
            # Prose, not code: a comment, or a docstring quoting the call in
            # backticks — including the ones that explain why this scan exists.
            if stripped.startswith("#") or "`" in line:
                continue
            window = "\n".join(lines[max(0, number - 10):number])
            if _UTC_MARKER in window:
                continue
            offenders.append(f"{path}:{number}: {stripped}")

    assert not offenders, (
        "these format a timestamp outside the display zone. Use "
        "`clock.format(value, tz, fmt)`, or mark the line `utc-by-design` with a "
        "reason if UTC is genuinely intended:\n" + "\n".join(offenders)
    )


def test_the_map_popup_is_in_the_configured_zone(client: TestClient, db, enrolled, mtls_headers):
    """⚠️ The exact bug an operator reported: the table said one zone, the map
    beside it said another, and the page gave no way to tell."""
    from tests.test_checkin import checkin
    from tests.test_locations import _report

    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    checkin(client, headers, locations=[_report(3)])

    client.post(
        "/admin/settings/general",
        data={"general.timezone": "America/Los_Angeles"},
        follow_redirects=False,
    )

    page = client.get(
        f"/devices/{result['device_id']}/location-history", headers=ADMIN_HEADERS
    ).text

    assert "PDT" in page or "PST" in page, (
        "the map popup does not name the configured zone; it is built in "
        "routes.py, which the template scan cannot see"
    )
    # ⚠️ Matched against a *rendered timestamp*, not the bare word. The page's own
    # help text mentions UTC to explain what the dates are not, and a blunter
    # assertion would forbid the sentence that prevents the confusion.
    stamped_utc = re.search(r"\d\d:\d\d(:\d\d)?\s*UTC", page)
    assert not stamped_utc, (
        f"a timestamp on this page is still in UTC: {stamped_utc.group(0)!r}"
    )


def test_the_table_and_the_map_agree(client: TestClient, db, enrolled, mtls_headers):
    """Two renderings of one instant on one page. If they disagree, the page is
    lying about at least one of them."""
    from tests.test_checkin import checkin
    from tests.test_locations import _report

    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    checkin(client, headers, locations=[_report(3)])

    client.post(
        "/admin/settings/general",
        data={"general.timezone": "Asia/Tokyo"},
        follow_redirects=False,
    )
    page = client.get(
        f"/devices/{result['device_id']}/location-history", headers=ADMIN_HEADERS
    ).text

    # From the stored point, never from the clock — see the note above.
    expected = clock.format(
        _stored_point(db).recorded_at, clock.zone("Asia/Tokyo"), "%Y-%m-%d %H:"
    )
    # Both the table cell and the map payload carry the same local hour.
    assert page.count(expected) >= 2, (
        f"expected the local hour {expected!r} in both the table and the map"
    )


def test_a_report_renders_in_the_configured_zone(client: TestClient, db, enrolled, mtls_headers):
    """Reports build their strings in Python, so the filter never saw them."""
    from tests.test_checkin import checkin

    result = enrolled()
    checkin(client, mtls_headers(result["certificate_pem"]))

    client.post(
        "/admin/settings/general",
        data={"general.timezone": "Asia/Tokyo"},
        follow_redirects=False,
    )

    page = client.get("/reports/fleet-inventory", headers=ADMIN_HEADERS).text
    from app.db.models import Device as _Device

    checked_in = db.scalar(select(_Device.last_checkin_at))
    expected = clock.format(checked_in, clock.zone("Asia/Tokyo"), "%Y-%m-%d %H:")
    assert expected in page, "the report is still in UTC"


def test_a_report_cannot_be_written_that_forgets_the_zone():
    """⚠️ `_dt` takes the zone as a required argument on purpose.

    A default would let a new report print UTC beside five printing local, which
    is precisely how this reached an operator in the first place.
    """
    from app.services import reports

    with pytest.raises(TypeError):
        reports._dt(datetime.now(timezone.utc))


# --------------------------------------------------------------------------- #
# The window an operator asks for is their own day
# --------------------------------------------------------------------------- #


def test_a_typed_date_is_read_in_the_display_zone(client: TestClient, db):
    """⚠️ Midnight local, not midnight UTC.

    With UTC edges, an operator in Los Angeles asking for "14 September" gets a
    window starting at 17:00 on the 13th their time — so the page shows times that
    fall outside the window it says it is showing.
    """
    from app.web.routes import _parse_day

    la = clock.zone("America/Los_Angeles")
    parsed = _parse_day("2026-09-14", la)

    assert parsed is not None
    assert clock.format(parsed, la, "%Y-%m-%d %H:%M") == "2026-09-14 00:00"
    # Which is 07:00 UTC that day — the boundary the query actually uses.
    assert parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M") == "2026-09-14 07:00"


def test_no_zone_still_means_utc_midnight(client: TestClient):
    """The default deployment is unchanged."""
    from app.web.routes import _parse_day

    parsed = _parse_day("2026-09-14")

    assert parsed is not None
    assert parsed.strftime("%Y-%m-%d %H:%M %Z") == "2026-09-14 00:00 UTC"


def test_a_malformed_date_still_reads_as_absent(client: TestClient):
    from app.web.routes import _parse_day

    for junk in (None, "", "not-a-date", "2026-13-45"):
        assert _parse_day(junk, clock.zone("America/Los_Angeles")) is None


# --------------------------------------------------------------------------- #
# ⚠️ What W165 missed: the label, not the times (W166)
#
# The times moved to the operator's zone and the column header still read
# "(UTC)" — a column of correct numbers under a wrong label, which is worse than
# the all-UTC table it replaced, because the numbers now look authoritative. The
# scans were checking how timestamps are *formatted*; nothing was checking what
# the page *calls* the zone.
# --------------------------------------------------------------------------- #

#: A template may name UTC only inside a Jinja comment, or under this marker.
_TEMPLATE_UTC_MARKER = "utc-by-design"


def _jinja_comment_lines(text: str) -> set[int]:
    """Line numbers inside `{# ... #}` blocks, which are design prose."""
    inside = set()
    depth = 0
    for number, line in enumerate(text.splitlines(), 1):
        opens, closes = line.count("{#"), line.count("#}")
        if depth or opens:
            inside.add(number)
        depth += opens - closes
        depth = max(depth, 0)
    return inside


def test_no_template_labels_a_zone_it_does_not_know():
    """⚠️ The companion to the two formatting scans, and the third thing missed.

    A hard-coded zone name is not a formatting bug — it survives every check that
    looks at how a timestamp is rendered — and it is the only thing telling a
    reader what a bare `13:23:19` means.
    """
    offenders = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        text = io.open(path, encoding="utf-8").read()
        prose = _jinja_comment_lines(text)
        lines = text.splitlines()
        for number, line in enumerate(lines, 1):
            if "UTC" not in line or number in prose:
                continue
            window = "\n".join(lines[max(0, number - 10):number])
            if _TEMPLATE_UTC_MARKER in window:
                continue
            offenders.append(f"{path}:{number}: {line.strip()}")

    assert not offenders, (
        "these name a zone the page may not actually be in. Use "
        "`zone_label(...)`, or mark it `utc-by-design` with a reason:\n"
        + "\n".join(offenders)
    )


def test_the_history_column_header_names_the_configured_zone(
    client: TestClient, db, enrolled, mtls_headers
):
    """The operator's report: the times updated, the header did not."""
    from tests.test_checkin import checkin
    from tests.test_locations import _report

    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    checkin(client, headers, locations=[_report(3)])

    url = f"/devices/{result['device_id']}/location-history"

    assert "Date / time (UTC)" in client.get(url, headers=ADMIN_HEADERS).text

    client.post(
        "/admin/settings/general",
        data={"general.timezone": "America/Los_Angeles"},
        follow_redirects=False,
    )

    page = client.get(url, headers=ADMIN_HEADERS).text
    assert "Date / time (PDT)" in page or "Date / time (PST)" in page, (
        "the column header still does not name the console's zone"
    )
    assert "Date / time (UTC)" not in page


# --------------------------------------------------------------------------- #
# ⚠️ One header cannot be right for rows in two different offsets
# --------------------------------------------------------------------------- #


def test_the_abbreviation_is_used_when_every_row_agrees():
    denver = clock.zone("America/Denver")
    summer = [
        datetime(2026, 7, 1, 19, 0, tzinfo=timezone.utc),
        datetime(2026, 7, 2, 19, 0, tzinfo=timezone.utc),
    ]

    assert clock.label(denver, summer) == "MDT"


def test_a_column_spanning_a_transition_falls_back_to_the_zone_name():
    """⚠️ The case an abbreviation cannot describe.

    A window over the November change contains both MDT and MST rows. Labelling
    the column either one is wrong for half of it, and nothing in the table would
    say which half — so the header names the zone instead, which is true of every
    row beneath it.
    """
    denver = clock.zone("America/Denver")
    across = [
        datetime(2026, 11, 1, 6, 0, tzinfo=timezone.utc),   # MDT
        datetime(2026, 11, 2, 19, 0, tzinfo=timezone.utc),  # MST
    ]

    assert clock.label(denver, across) == "America/Denver"


def test_an_empty_column_still_gets_a_header():
    """Nothing is being mislabelled, so today's abbreviation is honest enough."""
    assert clock.label(clock.UTC, []) == "UTC"
    assert clock.label(clock.zone("America/Denver"), []) in {"MST", "MDT"}


def test_utc_is_still_called_utc():
    moments = [datetime(2026, 7, 1, 19, 0, tzinfo=timezone.utc)]

    assert clock.label(clock.UTC, moments) == "UTC"
