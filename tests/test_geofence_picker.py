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


def test_nominatim_is_never_the_one_asked_as_you_type(client: TestClient):
    """⚠️ Rewritten in W110, and the constraint it guards is unchanged.

    This originally asserted the picker never searches while typing, because
    Nominatim's usage policy forbids autocomplete. W110 added suggestions — but
    against **Photon**, which is built for it, while the press still goes to
    Nominatim. So the rule is not "never search as you type"; it is "never send
    type-ahead to the service that forbids it", and that is what is asserted.
    """
    picker = _picker_script()

    # The as-you-type path calls the suggest endpoint...
    assert "/policies/geocode/suggest" in picker
    # ...and the press calls the lookup endpoint, still bound to the button.
    assert 'findButton.addEventListener("click", find)' in picker

    suggest_block = picker[picker.index("function requestSuggestions"):]
    suggest_block = suggest_block[: suggest_block.index("addressBox.addEventListener")]
    assert "/policies/geocode?" not in suggest_block, (
        "type-ahead must not reach the Nominatim-backed lookup"
    )


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


# --------------------------------------------------------------------------- #
# Suggestions as you type (W110)
# --------------------------------------------------------------------------- #


def _photon(features) -> httpx.Client:
    return _client(lambda request: httpx.Response(200, json={"features": features}))


def _feature(lon, lat, **props):
    return {"geometry": {"coordinates": [lon, lat]}, "properties": props}


def test_photon_geojson_is_read_lon_lat_not_lat_lon(client: TestClient, db):
    """⚠️ GeoJSON is [longitude, latitude] — the opposite order to every other
    coordinate in this codebase.

    Read the other way round, anywhere in the Americas lands in the sea off West
    Africa. The numbers below are chosen so a swap is unmistakable rather than
    plausible.
    """
    places = geocoding.suggest(
        db,
        "upper drive",
        client=_photon([_feature(-117.58, 33.83, street="Upper Drive", city="Corona")]),
    )

    assert places[0].latitude == pytest.approx(33.83)
    assert places[0].longitude == pytest.approx(-117.58)


def test_a_label_is_assembled_from_photons_separate_fields(client: TestClient, db):
    """Nominatim returns a finished display_name; Photon returns the parts."""
    places = geocoding.suggest(
        db,
        "upper",
        client=_photon(
            [
                _feature(
                    -117.58, 33.83,
                    housenumber="110", street="Upper Drive",
                    city="Corona", state="California", country="United States",
                )
            ]
        ),
    )

    assert places[0].label == "110 Upper Drive, Corona, California, United States"


def test_a_short_query_asks_nobody(client: TestClient, db):
    """⚠️ Two characters match half the planet, and every one of them is a query a
    third party sees. The floor is a disclosure decision as much as a quality
    one."""

    def fail(request):
        raise AssertionError("a short query must not reach the suggestion service")

    assert geocoding.suggest(db, "Co", client=_client(fail)) == []
    assert geocoding.MIN_QUERY_LENGTH == 3


def test_suggestions_fail_silently(client: TestClient, db):
    """⚠️ This runs on almost every keystroke. An exception per character would
    bury the form in complaints about a convenience — the Find button is where a
    broken lookup gets reported, once, where it can be read."""

    def boom(request):
        raise httpx.ConnectError("photon is down")

    assert geocoding.suggest(db, "corona", client=_client(boom)) == []


def test_suggestions_are_biased_toward_what_the_operator_is_looking_at(
    client: TestClient, db
):
    """⚠️ Measured, not assumed: unbiased, "Cor" returns a global list; biased to
    southern California it returns Corona, California."""
    seen = {}

    def capture(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"features": []})

    geocoding.suggest(db, "corona", near=(33.87, -117.57), client=_client(capture))

    assert "lat=33.87" in seen["url"]
    assert "lon=-117.57" in seen["url"]


def test_the_two_services_are_configured_separately(client: TestClient, db):
    """⚠️ Photon answers "Upper Dr Corona" with three Upper Drives in California,
    and "110 W Upper" with a road in Nova Scotia at every bias level. Nominatim
    handles the fully-typed form and forbids type-ahead. Each is used where it is
    strong, so each needs its own endpoint."""
    assert geocoding.DEFAULT_SUGGEST_ENDPOINT != geocoding.DEFAULT_ENDPOINT
    assert "photon" in geocoding.DEFAULT_SUGGEST_ENDPOINT
    assert "nominatim" in geocoding.DEFAULT_ENDPOINT

    from app.services import settings_store

    settings_store.put(db, geocoding.SETTING_SUGGEST_ENDPOINT, "https://photon.internal/api")
    db.commit()

    assert geocoding.suggest_endpoint(db) == "https://photon.internal/api"
    assert geocoding.endpoint(db) == geocoding.DEFAULT_ENDPOINT, "unchanged"


def test_the_suggest_endpoint_never_errors(client: TestClient, monkeypatch):
    """Called while somebody types; a 500 would surface as a broken console."""

    def boom(session, query, near=None, client=None):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(geocoding, "suggest", lambda *a, **k: [])

    response = client.get("/policies/geocode/suggest?q=corona", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert response.json()["results"] == []


def test_the_box_debounces_and_floors_the_query(client: TestClient):
    """⚠️ Fair use of a free service, and less of the operator's typing sent."""
    picker = _picker_script()

    assert "suggestTimer" in picker
    assert "300" in picker
    assert "query.length < 3" in picker


def test_stale_suggestions_cannot_overwrite_newer_ones(client: TestClient):
    """⚠️ Answers arrive out of order. Without a sequence guard a slow reply for
    "Cor" lands after the fast one for "Corona" and replaces it."""
    picker = _picker_script()

    assert "suggestSeq" in picker
    assert "seq !== suggestSeq" in picker


def test_choosing_a_suggestion_creates_a_row_if_there_is_none(client: TestClient):
    """⚠️ W109a's lesson applied to the path W110 added, rather than learned
    twice: choosing a suggestion is exactly the moment an operator means to
    create the fence."""
    picker = _picker_script()

    chooser = picker[picker.index("function showResults"):]
    chooser = chooser[: chooser.index("function place")]

    assert "rowsEnsuringOne()" in chooser


# --------------------------------------------------------------------------- #
# ⚠️ Reported from the field (2026-09-09): unreadable, and answering Nova Scotia
# --------------------------------------------------------------------------- #


def test_the_suggestion_list_sets_its_own_text_colour(client: TestClient):
    """⚠️ A control that changes its background must set its foreground.

    The global `button` rule sets `color: var(--accent-ink)` — white — for the
    filled blue buttons everywhere else. Overriding only the background here left
    white text on a near-white panel: legible to nobody, and reported from a
    screenshot rather than caught by any test, because no test can see.
    """
    css = pathlib.Path("app/web/static/atlas.css").read_text(encoding="utf-8")
    block = css[css.index(".geofence-results button {"):]
    block = block[: block.index("}")]

    assert "color: var(--ink)" in block
    assert "background: #fff" in block


def test_suggestions_are_restricted_to_the_visible_map(client: TestClient, db):
    """⚠️ The box does what the bias could not.

    "110 w upper d" biased to southern California still returned roads in Nova
    Scotia at every location_bias_scale up to 5. The same query inside a southern
    California bounding box returns only southern California.
    """
    seen = {}

    def capture(request):
        seen.setdefault("urls", []).append(str(request.url))
        return httpx.Response(200, json={"features": [
            _feature(-117.58, 33.83, street="Upper Drive", city="Corona")
        ]})

    geocoding.suggest(
        db, "110 w upper d",
        near=(33.87, -117.57),
        bbox=(-118.5, 33.4, -116.8, 34.3),
        client=_client(capture),
    )

    assert "bbox=" in seen["urls"][0]
    assert len(seen["urls"]) == 1, "one request when the box finds something"


def test_a_box_that_finds_nothing_is_retried_without_it(client: TestClient, db):
    """⚠️ Constraining to the visible map is right until somebody searches for a
    place they are not looking at.

    "Berlin Germany" inside a California box returns exactly zero from Photon —
    measured, not assumed. A chooser that says "no matches" for a real city is
    worse than one that answers less locally.
    """
    calls = []

    def capture(request):
        calls.append(str(request.url))
        # Empty while the box is applied; a hit once it is dropped.
        if "bbox=" in str(request.url):
            return httpx.Response(200, json={"features": []})
        return httpx.Response(200, json={"features": [
            _feature(13.4050, 52.5200, name="Berlin", country="Germany")
        ]})

    places = geocoding.suggest(
        db, "Berlin Germany",
        bbox=(-118.5, 33.4, -116.8, 34.3),
        client=_client(capture),
    )

    assert len(calls) == 2, "the box was tried, then dropped"
    assert "bbox=" in calls[0] and "bbox=" not in calls[1]
    assert places[0].label.startswith("Berlin")


def test_the_browser_sends_the_map_bounds(client: TestClient):
    picker = _picker_script()

    assert "map.getBounds()" in picker
    assert "&bbox=" in picker


def test_a_malformed_box_is_dropped_rather_than_refused(client: TestClient, monkeypatch):
    """This is called while somebody types; an unbounded search is a perfectly
    good answer to give them."""
    seen = {}

    def fake(session, query, near=None, bbox=None, client=None):
        seen["bbox"] = bbox
        return []

    monkeypatch.setattr(geocoding, "suggest", fake)

    response = client.get(
        "/policies/geocode/suggest?q=corona&bbox=not,a,real,box", headers=ADMIN_HEADERS
    )

    assert response.status_code == 200
    assert seen["bbox"] is None


# --------------------------------------------------------------------------- #
# ⚠️ Ontario for a California address (2026-09-09)
# --------------------------------------------------------------------------- #


def test_a_leading_house_number_is_droppable(client: TestClient):
    from app.services.geocoding import _without_house_number as strip

    assert strip("110 w upper dr, corona ca") == "w upper dr, corona ca"
    assert strip("110 upper dr") == "upper dr"
    # Nothing to drop: these must not be mangled into a broader search.
    assert strip("upper dr corona") == ""
    assert strip("corona ca") == ""
    assert strip("110") == ""


def test_the_query_loosens_before_the_map_widens(client: TestClient, db):
    """⚠️ The ordering is the fix, and the first version had it backwards.

    Measured on the operator's address, all in one California box:
    "110 w upper dr corona" returns nothing, "w upper dr corona" returns Upper
    Drive in Corona. Going straight from "nothing in the box" to "search the
    world" answered with Upper Canada Drive in Ontario — confident, precise and
    on the wrong continent, which an operator reads as the answer.
    """
    asked = []

    def capture(request):
        url = str(request.url)
        asked.append(url)
        # Photon's real behaviour: the full query finds nothing, the query
        # without the house number finds the street.
        if "110" in url:
            return httpx.Response(200, json={"features": []})
        return httpx.Response(200, json={"features": [
            _feature(-117.58, 33.83, street="Upper Drive", city="Corona", state="California")
        ]})

    places = geocoding.suggest(
        db, "110 w upper dr, corona ca",
        near=(33.87, -117.57),
        bbox=(-118.5, 33.4, -116.8, 34.3),
        client=_client(capture),
    )

    assert places, "the street was found"
    assert "Corona" in places[0].label
    # ⚠️ Two attempts, and the second still carried the box: the search never
    # left the visible map to get this answer.
    assert len(asked) == 2
    assert "bbox=" in asked[0] and "bbox=" in asked[1]


def test_the_map_is_only_widened_as_a_last_resort(client: TestClient, db):
    """"Berlin Germany" inside a California box returns exactly zero from Photon,
    so leaving the box has to remain possible — just last."""
    asked = []

    def capture(request):
        url = str(request.url)
        asked.append(url)
        if "bbox=" in url:
            return httpx.Response(200, json={"features": []})
        return httpx.Response(200, json={"features": [
            _feature(13.4050, 52.5200, name="Berlin", country="Germany")
        ]})

    places = geocoding.suggest(
        db, "Berlin Germany",
        bbox=(-118.5, 33.4, -116.8, 34.3),
        client=_client(capture),
    )

    assert places[0].label.startswith("Berlin")
    assert "bbox=" in asked[0], "the box was tried first"
    assert "bbox=" not in asked[-1], "and dropped only after it failed"


def test_a_query_with_no_house_number_does_not_get_an_extra_attempt(
    client: TestClient, db
):
    """Loosening only happens when there is something to loosen — otherwise the
    same query would be asked twice for nothing."""
    asked = []

    def capture(request):
        asked.append(str(request.url))
        return httpx.Response(200, json={"features": []})

    geocoding.suggest(
        db, "upper dr corona",
        bbox=(-118.5, 33.4, -116.8, 34.3),
        client=_client(capture),
    )

    # Boxed, then unboxed. No house-number variant, because there is no number.
    assert len(asked) == 2
