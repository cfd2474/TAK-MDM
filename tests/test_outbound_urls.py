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

"""`SEC_AUDIT.md` M-2 — the geocoder is not a way into the host's network.

Two axes, and the tests are grouped by them because conflating them is how this
gets fixed wrongly:

* **What an administrator may configure.** A private LAN address is *allowed*.
  ⚠️ A self-hosted Nominatim or Photon is exactly what an air-gapped TAK
  installation runs, and the reflex "reject private ranges" would make this a
  security fix that reads as an outage on the deployments that need the product
  most. The bottom half of this file is as much a part of the guard as the top.
* **Where a redirect may go.** This is the half that reaches past the
  administrator: a public service can steer the fetch inward while the setting
  stays exactly as they left it.

No test here touches DNS — `conftest.resolves` replaces the resolver for the
whole suite.
"""

from __future__ import annotations

import httpx
import pytest

from app.security import outbound
from app.services import geocoding, settings_store

ADMIN = {"x-authentik-username": "ssrf", "x-authentik-groups": "takmdm-admins"}


def _responder(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _literal(address: str) -> str:
    """An address as it appears in a URL.

    ⚠️ IPv6 has to be bracketed. Without brackets `urlsplit` reads
    `http://fc00::1/x` as the host `fc00`, which the stub resolver then answers
    with a public address — so two of these tests passed for entirely the wrong
    reason before this existed.
    """
    return f"[{address}]" if ":" in address else address


# --------------------------------------------------------------------------- #
# Address classification
# --------------------------------------------------------------------------- #


#: The classification table, asserted directly.
#:
#: ⚠️ `is_public` is exported and answers a question of its own — "is this on
#: the public internet?" — so it is tested as a predicate rather than only through
#: `inspect`. Multicast is the case that needs it: `inspect` refuses multicast via
#: `is_forbidden` whatever `is_public` says, so dropping the multicast clause
#: changed no end-to-end behaviour and survived a mutation sweep. A predicate that
#: calls `224.0.0.1` a public internet address is wrong even where nothing
#: currently asks.
PUBLIC = ["8.8.8.8", "1.1.1.1", "2606:4700::1", "::ffff:8.8.8.8"]
NOT_PUBLIC = [
    "10.0.0.5",
    "172.17.0.1",
    "192.168.1.20",
    "127.0.0.1",
    "169.254.169.254",
    "100.100.100.200",  # shared address space; is_private does NOT cover it
    "224.0.0.1",        # multicast; is_global DOES call it global
    "fc00::1",
    "fe80::1",
    "::1",
]


@pytest.mark.parametrize("address", PUBLIC)
def test_a_routable_address_is_public(address):
    import ipaddress

    assert outbound.is_public(ipaddress.ip_address(address)) is True


@pytest.mark.parametrize("address", NOT_PUBLIC)
def test_everything_else_is_not(address):
    import ipaddress

    assert outbound.is_public(ipaddress.ip_address(address)) is False


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "::1",
        "169.254.169.254",  # the cloud metadata service
        "fe80::1",
        "224.0.0.1",
        "0.0.0.0",
        "::ffff:127.0.0.1",  # loopback wearing a hat
        "::ffff:169.254.169.254",
    ],
)
def test_somewhere_no_geocoder_is_is_refused_outright(address):
    """Refused even when an administrator configures it deliberately — there is
    no deployment in which any of these is the right answer."""
    with pytest.raises(outbound.UnsafeUrl):
        outbound.inspect(f"http://{_literal(address)}/search")


@pytest.mark.parametrize("address", ["10.0.0.5", "172.17.0.1", "192.168.1.20", "fc00::1"])
def test_a_private_address_is_allowed_because_people_self_host(address):
    """⚠️ The test that stops the obvious over-fix.

    `http://10.0.0.5:8080/search` is a self-hosted Nominatim on somebody's LAN.
    Refusing it would break air-gapped deployments for no gain: an administrator
    who can set this setting can already reach their own network.
    """
    target = outbound.inspect(f"http://{_literal(address)}/search")

    assert target.is_internal is True


@pytest.mark.parametrize("scheme", ["file", "ftp", "gopher", "data", "jar"])
def test_only_http_and_https_are_fetched(scheme):
    with pytest.raises(outbound.UnsafeUrl):
        outbound.inspect(f"{scheme}://example.org/x")


def test_a_url_with_no_host_is_refused():
    with pytest.raises(outbound.UnsafeUrl):
        outbound.inspect("http:///search")


def test_shared_address_space_is_not_public(resolves):
    """⚠️ `100.64.0.0/10` is Alibaba's metadata range and CGNAT, and Python's
    `is_private` does **not** cover it. Using `is_global` rather than a
    hand-written list of private ranges is what catches it."""
    resolves.points("geo.example", "100.100.100.200")

    assert outbound.inspect("http://geo.example/search").is_internal is True


def test_a_host_is_internal_if_any_of_its_addresses_is(resolves):
    """⚠️ Any, not the first.

    A hostile resolver can answer with several addresses in any order, so
    judging by the first is a coin toss the attacker calls.
    """
    resolves.points("split.example", "93.184.216.34", "10.0.0.5")

    assert outbound.inspect("http://split.example/search").is_internal is True


def test_a_name_that_does_not_resolve_is_refused_rather_than_attempted():
    """Unknown is refused, not attempted. A name we cannot classify is a name we
    cannot say is safe, and trying it anyway is the whole guard optional."""
    def explode(host):
        raise OSError("no such host")

    with pytest.raises(outbound.UnsafeUrl):
        outbound.inspect("http://nope.example/search", resolve=explode)


# --------------------------------------------------------------------------- #
# Redirects — the half that reaches past the administrator
# --------------------------------------------------------------------------- #


def test_a_public_service_may_not_redirect_into_this_network(resolves):
    """⚠️ The finding, exactly. An external geocoder — or an open redirect on
    one — steering the fetch inward without the setting ever changing."""
    resolves.points("geocoder.example", "93.184.216.34")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "geocoder.example":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})
        raise AssertionError(f"reached {request.url} — the redirect was followed")

    with pytest.raises(outbound.UnsafeUrl):
        outbound.fetch(_responder(handler), "http://geocoder.example/search")


def test_a_public_service_may_not_redirect_to_a_private_address(resolves):
    resolves.points("geocoder.example", "93.184.216.34")
    resolves.points("inside.example", "10.0.0.5")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "geocoder.example":
            return httpx.Response(302, headers={"location": "http://inside.example/x"})
        raise AssertionError("the redirect was followed")

    with pytest.raises(outbound.UnsafeUrl):
        outbound.fetch(_responder(handler), "http://geocoder.example/search")


def test_an_internal_geocoder_may_still_redirect_internally(resolves):
    """The other half. A deployment that deliberately runs its own geocoder on a
    private network keeps working, including through its own redirects — it
    never left the network it started in."""
    resolves.points("geo.internal", "10.0.0.5")
    resolves.points("geo2.internal", "10.0.0.6")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "geo.internal":
            return httpx.Response(301, headers={"location": "http://geo2.internal/search"})
        return httpx.Response(200, json=[{"lat": "1", "lon": "2", "display_name": "ok"}])

    response = outbound.fetch(_responder(handler), "http://geo.internal/search")

    assert response.status_code == 200


def test_an_ordinary_https_upgrade_still_works(resolves):
    """The common real redirect, and one that must not be collateral damage."""
    resolves.points("geocoder.example", "93.184.216.34")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.scheme == "http":
            return httpx.Response(301, headers={"location": "https://geocoder.example/search"})
        return httpx.Response(200, json=[])

    assert outbound.fetch(_responder(handler), "http://geocoder.example/search").status_code == 200


#: Where the test server gives up redirecting.
#:
#: ⚠️ The loop is **bounded**, deliberately. An endless one would mean a missing
#: hop limit *hangs* the suite rather than failing it, and a test run that never
#: finishes is not diagnosed as "the redirect limit regressed" — it is diagnosed
#: as a broken machine. (It hung a mutation sweep here before this was bounded.)
RUNAWAY = 20


def test_a_redirect_loop_is_stopped(resolves):
    hops = []

    def handler(request: httpx.Request) -> httpx.Response:
        hops.append(str(request.url))
        if len(hops) > RUNAWAY:
            return httpx.Response(200, json=[])
        return httpx.Response(302, headers={"location": "http://geocoder.example/again"})

    with pytest.raises(outbound.UnsafeUrl):
        outbound.fetch(_responder(handler), "http://geocoder.example/search")

    assert len(hops) <= outbound.MAX_REDIRECTS + 1, hops


def test_the_query_is_not_re_appended_after_a_redirect(resolves):
    """⚠️ After a redirect the server has chosen the whole URL, query included.
    Re-appending ours either duplicates it or overrides what it asked for."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if "moved" not in str(request.url):
            return httpx.Response(302, headers={"location": "http://geocoder.example/moved?token=abc"})
        return httpx.Response(200, json=[])

    outbound.fetch(_responder(handler), "http://geocoder.example/search", params={"q": "x"})

    assert seen[0].endswith("/search?q=x")
    assert seen[1] == "http://geocoder.example/moved?token=abc"


def test_a_redirect_with_no_destination_is_handed_back_not_invented(resolves):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302)

    response = outbound.fetch(_responder(handler), "http://geocoder.example/search")

    assert response.status_code == 302


# --------------------------------------------------------------------------- #
# Through the geocoder, which is where it actually matters
# --------------------------------------------------------------------------- #


def test_the_geocoder_refuses_a_metadata_url_and_says_why(client, db):
    """⚠️ A distinct message from "could not be reached". This one is fixed by
    editing a setting; the other sends an operator to check their network."""
    settings_store.put(db, geocoding.SETTING_ENDPOINT, "http://169.254.169.254/latest/")

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"the server fetched {request.url}")

    with pytest.raises(geocoding.GeocodingError) as raised:
        geocoding.search(db, "anywhere", client=_responder(handler))

    assert "Admin" in str(raised.value)


def test_the_geocoder_refuses_a_redirect_into_the_network(client, db, resolves):
    resolves.points("nominatim.openstreetmap.org", "93.184.216.34")

    def handler(request: httpx.Request) -> httpx.Response:
        if "169.254" in str(request.url):
            raise AssertionError("the redirect was followed")
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/"})

    with pytest.raises(geocoding.GeocodingError):
        geocoding.search(db, "anywhere", client=_responder(handler))


def test_suggestions_stay_silent_when_the_url_is_refused(client, db):
    """⚠️ Suggestions fail quietly by design — this runs on every keystroke, and
    an error banner per character would bury the form. The refusal is logged, not
    raised."""
    settings_store.put(db, geocoding.SETTING_SUGGEST_ENDPOINT, "http://127.0.0.1:5432/api")

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"the server fetched {request.url}")

    assert geocoding.suggest(db, "corona", client=_responder(handler)) == []


def test_a_self_hosted_geocoder_on_a_private_lan_still_works(client, db, resolves):
    """The deployment the over-fix would have broken, exercised end to end."""
    resolves.points("geo.internal", "10.0.0.5")
    settings_store.put(db, geocoding.SETTING_ENDPOINT, "http://geo.internal/search")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"lat": "33.9", "lon": "-117.5", "display_name": "Corona"}])

    places = geocoding.search(db, "corona", client=_responder(handler))

    assert [p.label for p in places] == ["Corona"]
