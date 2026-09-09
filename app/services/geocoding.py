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

"""Turning an address into a coordinate, for the geofence editor (W109).

⚠️ **This sends what the operator typed to a third party**, and what they typed is
where they are about to put a geofence — planning, not history. W106 C3 declined
*reverse* geocoding because it would have sent device positions automatically on
every page view; this is the other direction and a smaller disclosure, but not a
free one. Three things follow from that, and none of them is decoration:

* **Server-side.** The browser never contacts the geocoder, so the operator's own
  address is not disclosed to it either — only this server's.
* **Two services, each where it is strong.** :func:`search` is the explicit press
  and goes to Nominatim, whose usage policy forbids type-ahead. :func:`suggest` is
  the as-you-type box and goes to Photon, which is built for it. Measured before
  choosing — see :func:`suggest` for the numbers.
* **Type-ahead is more disclosure than a press, and is treated as such.** It sends
  partial strings, so it is debounced in the browser, refuses queries under three
  characters, and fails silently rather than complaining once per keystroke.
* **Configurable, and optional.** A deployment can point this at its own geocoder
  or leave it off. Coordinates stay typeable either way — an operator with no
  internet must still be able to draw a fence.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from threading import Lock

import httpx
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

#: OpenStreetMap's public geocoder. A default, not a recommendation — see above.
DEFAULT_ENDPOINT = "https://nominatim.openstreetmap.org/search"

SETTING_ENDPOINT = "location.geocoder_url"

#: ⚠️ Nominatim's usage policy **requires** an identifying User-Agent and refuses
#: or throttles requests without one. Sending a real name is also the honest thing
#: to do: the operator of a free service is entitled to know who is calling it.
USER_AGENT = "ATLAS-MDM/1.0 (self-hosted device management; geofence editor)"

#: Short. This runs inside a console request while somebody watches a spinner, and
#: a geocoder that has gone away must fail visibly rather than hang the page.
TIMEOUT_SECONDS = 6.0

MAX_RESULTS = 5

#: Repeat searches are common — an operator tries a place, adjusts the radius,
#: searches the same place again. Small and process-local on purpose: this is a
#: courtesy to the geocoder, not a store of anything.
_CACHE: dict[str, list["Place"]] = {}
_CACHE_LOCK = Lock()
_CACHE_LIMIT = 128


class GeocodingError(Exception):
    """The lookup could not be completed. The message is shown to the operator."""


@dataclass(frozen=True)
class Place:
    label: str
    latitude: float
    longitude: float


def endpoint(session: Session) -> str:
    from app.services import settings_store

    return (settings_store.get(session, SETTING_ENDPOINT, "").strip() or DEFAULT_ENDPOINT)


def search(session: Session, query: str, *, client: httpx.Client | None = None) -> list[Place]:
    """Look up an address. Returns candidates, best first.

    ``client`` is injectable so tests never reach the network — a lesson from
    W101, where a test quietly queried Google on every run.
    """
    query = (query or "").strip()
    if not query:
        return []

    url = endpoint(session)
    key = f"{url}\n{query.lower()}"
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
    if cached is not None:
        return cached

    owned = client is None
    http = client or httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=True)
    try:
        response = http.get(
            url,
            params={"q": query, "format": "jsonv2", "limit": MAX_RESULTS},
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        # ⚠️ Reported, never swallowed into "no results". "The geocoder is
        # unreachable" and "that address does not exist" are different answers,
        # and an operator who reads the first as the second retypes a perfectly
        # good address five times.
        logger.warning("geocoder %s failed for %r: %s", url, query, exc)
        raise GeocodingError(
            "The address lookup service could not be reached. "
            "Enter coordinates directly, or check Admin → Location."
        ) from exc
    except ValueError as exc:
        logger.warning("geocoder %s returned unreadable JSON: %s", url, exc)
        raise GeocodingError("The address lookup service returned an unusable answer.") from exc
    finally:
        if owned:
            http.close()

    places = _parse(payload)
    with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_LIMIT:
            _CACHE.clear()
        _CACHE[key] = places
    return places


def _parse(payload: object) -> list[Place]:
    """Read whatever the geocoder returned, skipping anything unusable.

    ⚠️ Tolerant on purpose. This is a third-party service that may be swapped for
    another one by a setting, and a single odd row must not cost the whole result
    list — nor must a malformed coordinate reach the form and become a fence
    centred somewhere nobody chose.
    """
    if not isinstance(payload, list):
        return []

    places: list[Place] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        try:
            latitude = float(row.get("lat"))
            longitude = float(row.get("lon"))
        except (TypeError, ValueError):
            continue
        if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
            continue
        label = str(row.get("display_name") or "").strip()
        if not label:
            label = f"{latitude:.5f}, {longitude:.5f}"
        places.append(Place(label=label, latitude=latitude, longitude=longitude))
    return places


def reset_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


# --------------------------------------------------------------------------- #
# Suggestions as you type (W110)
# --------------------------------------------------------------------------- #

#: komoot's public Photon instance. Free, keyless, and built for type-ahead —
#: which is the one thing Nominatim's usage policy forbids, and the reason the
#: two live side by side rather than one replacing the other.
DEFAULT_SUGGEST_ENDPOINT = "https://photon.komoot.io/api"

SETTING_SUGGEST_ENDPOINT = "location.suggest_url"

#: ⚠️ Below this, suggestions are noise and the request is wasted. Two characters
#: match half the planet, and every one of them is a query a third party sees.
MIN_QUERY_LENGTH = 3

MAX_SUGGESTIONS = 6


def suggest_endpoint(session: Session) -> str:
    from app.services import settings_store

    return (
        settings_store.get(session, SETTING_SUGGEST_ENDPOINT, "").strip()
        or DEFAULT_SUGGEST_ENDPOINT
    )


def suggest(
    session: Session,
    query: str,
    *,
    near: tuple[float, float] | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    client: httpx.Client | None = None,
) -> list[Place]:
    """Address suggestions for a partial string, for a type-ahead box.

    ⚠️ **Separate from :func:`search`, and deliberately a different service.**
    Measured against the operator's own address before choosing:

    * Photon answers `"Upper Dr Corona"` with three Upper Drives in Corona,
      California — exactly the disambiguation a chooser needs.
    * Photon answers `"110 W Upper"` with a road in **Nova Scotia**, at every
      `location_bias_scale` from the default to 5. Its ranking lets the house
      number dominate the street name.
    * Nominatim answers the fully-typed `"110 W Upper Dr, Corona CA"` correctly,
      and forbids type-ahead in its usage policy.

    So each is used where it is strong: Photon while typing, Nominatim on the
    press. A single service for both would be worse at one of the two jobs.

    ``bbox`` restricts results to what the map is showing, and ``near`` biases
    toward its centre. **The box does the real work**: bias alone still answered
    `"110 w upper d"` with roads in Nova Scotia at every `location_bias_scale` up
    to 5, while the same query inside a southern California box returns only
    southern California.

    ⚠️ **A box that finds nothing is retried without it.** Constraining to the
    visible map is right until somebody searches for a place they are not looking
    at — `"Berlin Germany"` inside a California box returns exactly zero, and a
    chooser that says "no matches" for a real city is worse than a less local one.
    """
    query = (query or "").strip()
    if len(query) < MIN_QUERY_LENGTH:
        return []

    url = suggest_endpoint(session)

    key = f"suggest\n{url}\n{query.lower()}\n{near}"
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
    if cached is not None:
        return cached

    owned = client is None
    http = client or httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=True)
    try:
        places = _ask_photon(http, url, query, near, bbox)
        if not places and bbox is not None:
            # The operator is searching for somewhere off-screen. Widen rather
            # than answer "no matches" for a place that plainly exists.
            places = _ask_photon(http, url, query, near, None)
    except (httpx.HTTPError, ValueError) as exc:
        # ⚠️ Suggestions fail *quietly*. This runs on almost every keystroke, and
        # an error banner per character would bury the form in complaints about a
        # convenience. The Find button still reports failures loudly, which is
        # where an operator actually needs to hear about them.
        logger.info("suggestions unavailable from %s: %s", url, exc)
        return []
    finally:
        if owned:
            http.close()

    with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_LIMIT:
            _CACHE.clear()
        _CACHE[key] = places
    return places


def _ask_photon(
    http: httpx.Client,
    url: str,
    query: str,
    near: tuple[float, float] | None,
    bbox: tuple[float, float, float, float] | None,
) -> list[Place]:
    """One request to Photon, with whatever narrowing we have."""
    params: dict[str, object] = {"q": query, "limit": MAX_SUGGESTIONS}
    if near is not None:
        params["lat"], params["lon"] = near
    if bbox is not None:
        # Photon wants minLon,minLat,maxLon,maxLat.
        params["bbox"] = ",".join(f"{value:.5f}" for value in bbox)

    response = http.get(url, params=params, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return _parse_photon(response.json())


def _parse_photon(payload: object) -> list[Place]:
    """Read Photon's GeoJSON. A different shape from Nominatim's flat JSON."""
    if not isinstance(payload, dict):
        return []
    features = payload.get("features")
    if not isinstance(features, list):
        return []

    places: list[Place] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            continue
        try:
            # ⚠️ GeoJSON is [longitude, latitude] — the opposite order to every
            # other coordinate in this codebase. Reading it as lat/lon puts a
            # fence in the sea off West Africa for anywhere in the Americas.
            longitude = float(coordinates[0])
            latitude = float(coordinates[1])
        except (TypeError, ValueError):
            continue
        if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
            continue

        label = _photon_label(feature.get("properties") or {})
        if not label:
            label = f"{latitude:.5f}, {longitude:.5f}"
        places.append(Place(label=label, latitude=latitude, longitude=longitude))
    return places


def _photon_label(properties: object) -> str:
    """A readable one-line address from Photon's separate fields.

    Nominatim hands back a finished `display_name`; Photon hands back the parts
    and expects the caller to assemble them. Joined widest-last so the
    distinguishing detail — which of three Upper Drives — is what the eye meets
    first in a list.
    """
    if not isinstance(properties, dict):
        return ""

    number = str(properties.get("housenumber") or "").strip()
    street = str(properties.get("street") or properties.get("name") or "").strip()
    head = f"{number} {street}".strip() if number else street

    parts = [
        head,
        str(properties.get("city") or properties.get("county") or "").strip(),
        str(properties.get("state") or "").strip(),
        str(properties.get("country") or "").strip(),
    ]
    return ", ".join(part for part in parts if part)
