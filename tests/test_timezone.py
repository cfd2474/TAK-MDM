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
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.services import clock
from tests.conftest import ADMIN_HEADERS

TEMPLATES = pathlib.Path("app/web/templates")


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
    tokyo = clock.format(datetime.now(timezone.utc), clock.zone("Asia/Tokyo"), "%Y-%m-%d")
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
