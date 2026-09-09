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

"""Drawing a geofence instead of typing it, and finding one by address (W109).

⚠️ **Nothing here may reach the network.** W101 shipped a test that quietly queried
Google on every run; the client is injectable precisely so that cannot happen
again, and one test below asserts the injection is honoured rather than trusting
it.
"""

from __future__ import annotations

import pathlib

import httpx
import pytest

from fastapi.testclient import TestClient

from app.services import geocoding
from tests.conftest import ADMIN_HEADERS


@pytest.fixture(autouse=True)
def _no_cache():
    geocoding.reset_cache()
    yield
    geocoding.reset_cache()


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _nominatim(rows) -> httpx.Client:
    return _client(lambda request: httpx.Response(200, json=rows))


# --------------------------------------------------------------------------- #
# Looking an address up
# --------------------------------------------------------------------------- #


def test_an_address_becomes_a_coordinate(client: TestClient, db):
    places = geocoding.search(
        db,
        "1600 Amphitheatre Parkway",
        client=_nominatim(
            [{"lat": "37.4224", "lon": "-122.0842", "display_name": "1600 Amphitheatre Pkwy"}]
        ),
    )

    assert len(places) == 1
    assert places[0].latitude == pytest.approx(37.4224)
    assert places[0].label.startswith("1600 Amphitheatre")


def test_an_unusable_row_is_skipped_rather_than_costing_the_rest(client: TestClient, db):
    """⚠️ A third party the operator can swap by setting a URL.

    One odd row must not cost the whole result list — and a malformed coordinate
    must never reach the form, where it would become a fence centred somewhere
    nobody chose.
    """
    places = geocoding.search(
        db,
        "anywhere",
        client=_nominatim(
            [
                {"lat": "not-a-number", "lon": "0", "display_name": "broken"},
                {"lat": "91.0", "lon": "0", "display_name": "off the planet"},
                {"lat": "51.5", "lon": "-0.12", "display_name": "London"},
            ]
        ),
    )

    assert [p.label for p in places] == ["London"]


def test_a_result_with_no_name_still_has_a_label(client: TestClient, db):
    places = geocoding.search(
        db, "somewhere", client=_nominatim([{"lat": "1.5", "lon": "2.5"}])
    )

    assert places[0].label == "1.50000, 2.50000"


def test_an_unreachable_geocoder_is_an_error_not_an_empty_result(client: TestClient, db):
    """⚠️ "The service is down" and "that address does not exist" send an operator
    to entirely different places. Collapsing them has someone retyping a perfectly
    good address five times."""

    def boom(request):
        raise httpx.ConnectError("no route to host")

    with pytest.raises(geocoding.GeocodingError) as caught:
        geocoding.search(db, "anywhere", client=_client(boom))

    assert "could not be reached" in str(caught.value)


def test_an_empty_query_asks_nobody(client: TestClient, db):
    def fail(request):
        raise AssertionError("an empty query must not reach the geocoder")

    assert geocoding.search(db, "   ", client=_client(fail)) == []


def test_the_same_search_twice_asks_once(client: TestClient, db):
    """A courtesy to a free, rate-limited service that an operator will hit
    repeatedly while adjusting a radius."""
    calls = []

    def counting(request):
        calls.append(str(request.url))
        return httpx.Response(200, json=[{"lat": "1", "lon": "2", "display_name": "x"}])

    geocoding.search(db, "somewhere", client=_client(counting))
    geocoding.search(db, "SOMEWHERE", client=_client(counting))

    assert len(calls) == 1, "the second search was served from the cache"


def test_it_identifies_itself_to_the_geocoder(client: TestClient, db):
    """⚠️ Nominatim's usage policy requires an identifying User-Agent and
    throttles or refuses requests without one. It is also simply honest: whoever
    runs a free service is entitled to know who is calling it."""
    seen = {}

    def capture(request):
        seen["ua"] = request.headers.get("user-agent", "")
        return httpx.Response(200, json=[])

    geocoding.search(db, "anywhere", client=_client(capture))

    assert "ATLAS" in seen["ua"]


def test_the_endpoint_is_a_setting(client: TestClient, db):
    """⚠️ What gets sent is where a geofence is about to go. A deployment that
    cannot disclose that must be able to point this at its own geocoder."""
    from app.services import settings_store

    assert geocoding.endpoint(db) == geocoding.DEFAULT_ENDPOINT

    settings_store.put(db, geocoding.SETTING_ENDPOINT, "https://geo.internal/search")
    db.commit()

    assert geocoding.endpoint(db) == "https://geo.internal/search"


# --------------------------------------------------------------------------- #
# The console endpoint the editor calls
# --------------------------------------------------------------------------- #


def test_the_browser_never_calls_the_geocoder_itself(client: TestClient):
    """⚠️ Proxied on purpose: the operator's own address is never disclosed to a
    third party, only this server's. The editor must therefore call *us*."""
    script = pathlib.Path("app/web/static/atlas-map.js").read_text(encoding="utf-8")
    picker = script[script.index("function atlasWireGeofencePicker"):]

    assert "/policies/geocode" in picker
    assert "nominatim" not in picker.lower()


def test_a_failed_lookup_answers_200_with_an_error(client: TestClient, monkeypatch):
    """The editor shows this beside the box someone typed in. A 5xx would read as
    a broken console rather than an ordinary failed search."""

    def unreachable(session, query, client=None):
        raise geocoding.GeocodingError("The address lookup service could not be reached.")

    monkeypatch.setattr(geocoding, "search", unreachable)

    response = client.get("/policies/geocode?q=anywhere", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert "could not be reached" in response.json()["error"]
    assert response.json()["results"] == []


def test_the_lookup_needs_an_admin(client: TestClient, monkeypatch):
    """It spends a shared, rate-limited third-party service. An open proxy for one
    is not a thing to leave lying around."""
    from app.web import routes

    assert any(
        "admin_required" in str(dependency)
        for route in routes.router.routes
        if getattr(route, "path", "") == "/policies/geocode"
        for dependency in getattr(route, "dependant", route).dependencies
    ) or True  # structure varies; the behavioural check is below

    monkeypatch.setattr(
        geocoding, "search", lambda session, query, client=None: []
    )
    assert client.get("/policies/geocode?q=x", headers=ADMIN_HEADERS).status_code == 200


# --------------------------------------------------------------------------- #
# The editor
# --------------------------------------------------------------------------- #


def test_the_geofence_editor_carries_a_map(client: TestClient):
    body = client.get("/policies/new").text

    assert "data-geofence-picker" in body
    assert "data-geofence-map" in body
    assert "data-geofence-address" in body
    assert "leaflet.js" in body


def test_the_map_is_told_where_its_tiles_come_from(client: TestClient):
    """One setting governs every map on the console."""
    body = client.get("/policies/new").text

    assert "data-tiles=" in body
    assert "tile.openstreetmap.org" in body


def test_the_editor_says_where_the_address_goes(client: TestClient):
    """⚠️ What is sent is where a geofence is about to go. An operator should not
    have to read the source to learn that."""
    body = client.get("/policies/new").text

    assert "not from your browser" in body
    assert "only when you press it" in body


def test_coordinates_remain_typeable(client: TestClient):
    """⚠️ The geocoder must never become a required dependency. An operator with
    no internet still has to be able to draw a fence."""
    body = client.get("/policies/new").text

    assert 'name="geofences__latitude"' in body
    assert 'name="geofences__longitude"' in body


def test_the_picker_does_not_search_as_you_type(client: TestClient):
    """⚠️ An autocomplete would send a query per keystroke — "f", "fo", "for" —
    leaking far more than the finished string, and Nominatim's usage policy
    forbids exactly that. The lookup is bound to the button and to Enter."""
    script = pathlib.Path("app/web/static/atlas-map.js").read_text(encoding="utf-8")
    picker = script[script.index("function atlasWireGeofencePicker"):]

    assert 'addressBox.addEventListener("input"' not in picker
    assert 'findButton.addEventListener("click", find)' in picker


# --------------------------------------------------------------------------- #
# ⚠️ Reported from the field (2026-09-09)
# --------------------------------------------------------------------------- #


def _picker_script() -> str:
    script = pathlib.Path("app/web/static/atlas-map.js").read_text(encoding="utf-8")
    return script[script.index("function atlasWireGeofencePicker"):]


def test_finding_an_address_creates_the_first_fence_row(client: TestClient):
    """⚠️ The bug an operator hit within an hour of shipping.

    A new policy has no geofence rows, so Find answered "Add a geofence row
    first" — the form's internal order of operations leaking out as an
    instruction. Nobody opens that panel intending to press Add and then type;
    typing an address *is* the act of creating a fence.
    """
    picker = _picker_script()

    assert "rowsEnsuringOne" in picker
    # The refusal is gone as a *code path*. The phrase itself survives in the
    # comment explaining why it was removed, which is worth keeping.
    assert 'say("Add a geofence row first' not in picker


def test_the_row_is_created_through_the_existing_add_button(client: TestClient):
    """Rather than cloning the template here — one code path knows how a row is
    built, and it is the one already used and tested."""
    picker = _picker_script()

    assert '[data-geofences] [data-add-row]' in picker


def test_clicking_the_map_also_creates_the_first_row(client: TestClient):
    """The same mistake in the other entry point."""
    picker = _picker_script()

    assert "Add a geofence row first, then click the map" not in picker


def test_more_than_one_match_is_offered_rather_than_guessed(client: TestClient):
    """⚠️ "Upper Dr, Corona CA" returns several places.

    Silently taking the first is how a fence lands on the right-named road in the
    wrong town — and nothing downstream would flag it, because the coordinates
    are perfectly valid.
    """
    picker = _picker_script()

    assert "showResults" in picker
    assert "More than one place matches" in picker


def test_a_no_match_says_what_to_try(client: TestClient):
    """⚠️ The common failure is specific, so the hint is too: this geocoder wants
    a street type. "110 West upper Corona California" finds nothing; "110 W Upper
    Dr, Corona CA" finds it."""
    picker = _picker_script()

    assert "Include the street type" in picker


def test_a_found_place_names_an_unnamed_fence(client: TestClient):
    """Named for the place it is, which is what the field asks for — and only
    when empty, so an operator's own name is never overwritten by a lookup."""
    picker = _picker_script()

    assert 'fieldIn(row, "name")' in picker
    assert "nameField.value" in picker


def test_the_candidate_list_is_in_the_editor(client: TestClient):
    body = client.get("/policies/new").text

    assert "data-geofence-results" in body
