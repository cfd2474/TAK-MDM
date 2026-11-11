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

"""Fetching an operator-supplied URL without turning the server into a probe.

`SEC_AUDIT.md` **M-2**. The geocoder and the suggestion service are addresses an
administrator types into Admin → Location, and the server fetches them. Before
this, that fetch had no validation at all and `follow_redirects=True`, so
`http://169.254.169.254/...` worked, and so did any external service that
redirected there.

## The policy, and why it is not "reject private addresses"

⚠️ **The reflex fix would break a real deployment.** A self-hosted Nominatim or
Photon on a private LAN is exactly what an air-gapped TAK installation runs, and
refusing `http://10.0.0.5:8080/search` would make this a security fix that reads
as an outage on the deployments that most need the product.

So there are two separate questions, and only the second is about the attacker
this finding names:

**What may an administrator configure?** Anywhere routable, and anywhere on their
own network. Never loopback (that is this container), never link-local (that is
the cloud metadata service), never multicast or the unspecified address — no
geocoder lives at any of those, so allowing them buys nothing and costs the
`169.254.169.254` credential theft.

**Where may a redirect go?** This is the half that reaches *past* the
administrator who set the URL. A public geocoder — or an open redirect on one —
can send the fetch inward while the setting stays exactly as the operator left
it. So a hop may never move from a public address to an internal one, redirects
are followed by hand, and there is a hop limit.

A deployment that has deliberately pointed at its own internal geocoder keeps
working, including through its own internal redirects. Nothing that starts
outside gets in.

## What this does not close

⚠️ **DNS rebinding.** The host is resolved here and resolved again by the HTTP
client when it connects, and a name that answers with a public address the first
time can answer with `127.0.0.1` the second. Closing that means connecting to the
address we validated and carrying the hostname only in SNI and the `Host` header,
which httpx does not make reachable without replacing its transport. The window
is small and the attacker has to control DNS for the host an administrator typed;
it is recorded rather than quietly left out of the claim.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

logger = logging.getLogger(__name__)

#: Everything else — `file:`, `gopher:`, `ftp:` — is refused outright.
ALLOWED_SCHEMES = ("http", "https")

#: How many hops a redirect chain may take before it is treated as a loop.
#:
#: Three is generous for a geocoder: the real services use at most one, usually
#: an http→https upgrade. A long chain is a sign of something other than
#: geocoding.
MAX_REDIRECTS = 3

#: Status codes that mean "go and ask over there".
_REDIRECTS = (301, 302, 303, 307, 308)


class UnsafeUrl(Exception):
    """The URL, or somewhere it redirected to, is not somewhere we will fetch."""


def _resolve(host: str) -> list[str]:
    """Every address a hostname answers with.

    ⚠️ A module attribute on purpose, so tests can replace it. A guard that
    silently performs a DNS lookup on every test run is the W101 mistake — a test
    that quietly queried a third party — wearing different clothes, and it also
    makes the suite's behaviour depend on the developer's network.
    """
    infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


def _address(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError:
        return None
    # `::ffff:127.0.0.1` is 127.0.0.1 wearing a hat. CPython classifies the
    # mapped form correctly today, but normalising costs nothing and does not
    # depend on that continuing to be true.
    mapped = getattr(parsed, "ipv4_mapped", None)
    return mapped or parsed


def is_public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Is this an address on the public internet?

    ⚠️ `is_global` and **not** a hand-written list of private ranges. CPython
    maintains it against the IANA special-purpose registries, so shared address
    space (`100.64.0.0/10`, the Alibaba metadata range — which `is_private` does
    *not* cover) and the documentation ranges are already accounted for.

    The one thing `is_global` gets wrong for this purpose is multicast:
    `224.0.0.1` reports global.
    """
    return bool(address.is_global) and not address.is_multicast


def is_forbidden(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Somewhere no geocoder is, and somewhere worth reaching only as an attack.

    Refused even when an administrator configures it deliberately, because there
    is no configuration in which any of these is the right answer:

    * **loopback** — this container, serving ATLAS;
    * **link-local** — `169.254.169.254`, the cloud metadata service, and the
      single highest-value target a server-side fetch can be pointed at;
    * **multicast** and the **unspecified** address — not destinations.
    """
    return (
        address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
    )


@dataclass(frozen=True)
class Target:
    """A URL, and what we know about where it actually goes."""

    url: str
    host: str
    addresses: tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]

    @property
    def is_internal(self) -> bool:
        """Does any address for this host sit off the public internet?

        ⚠️ **Any, not the first.** A resolver may return addresses in any order
        and a hostile one can return several, so a name that answers with both
        `93.184.216.34` and `10.0.0.5` is internal for our purposes. Judging by
        the first answer would make the check a coin toss the attacker calls.
        """
        return any(not is_public(address) for address in self.addresses)


def inspect(url: str, *, resolve=None) -> Target:
    """Work out where a URL goes, refusing it if that is nowhere legitimate.

    Raises `UnsafeUrl` for a bad scheme, a missing host, or a host that resolves
    to somewhere in `is_forbidden`. A private LAN address is *not* refused here —
    see the module docstring for why that is deliberate.
    """
    parts = urlsplit(url)
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeUrl(
            f"{parts.scheme or 'that'} is not a scheme this server will fetch; "
            f"use http or https"
        )
    host = parts.hostname
    if not host:
        raise UnsafeUrl("that URL names no host")

    literal = _address(host)
    if literal is not None:
        addresses = [literal]
    else:
        resolver = resolve or _resolve
        try:
            found = resolver(host)
        except OSError as exc:
            raise UnsafeUrl(f"{host} could not be resolved ({exc})") from exc
        addresses = [address for address in map(_address, found) if address is not None]
        if not addresses:
            raise UnsafeUrl(f"{host} resolved to nothing usable")

    for address in addresses:
        if is_forbidden(address):
            raise UnsafeUrl(f"{host} resolves to {address}, which this server will not fetch")

    return Target(url=url, host=host, addresses=tuple(addresses))


def fetch(
    client: httpx.Client,
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    max_redirects: int = MAX_REDIRECTS,
    resolve=None,
) -> httpx.Response:
    """GET a URL, following redirects by hand so each hop can be checked.

    ⚠️ `follow_redirects=True` is what made the original finding reach past the
    administrator who set the URL, so it is not used here and should not be
    reintroduced. The rule below is the whole point of doing this by hand: a
    chain that starts on the public internet may not end up inside.
    """
    origin = inspect(url, resolve=resolve)
    current = url
    seen = 0

    while True:
        response = client.get(current, params=params, headers=headers, follow_redirects=False)
        if response.status_code not in _REDIRECTS:
            return response

        location = response.headers.get("location")
        if not location:
            # A redirect with nowhere to go. Hand it back rather than invent a
            # destination; the caller's error handling already covers a response
            # it cannot read.
            return response

        seen += 1
        if seen > max_redirects:
            raise UnsafeUrl(f"{url} redirected more than {max_redirects} times")

        current = urljoin(current, location)
        hop = inspect(current, resolve=resolve)
        if hop.is_internal and not origin.is_internal:
            # The finding, exactly: a public service steering the fetch inward
            # without the setting changing.
            logger.warning(
                "refused a redirect from %s to %s: an external service may not "
                "redirect into this network",
                url,
                current,
            )
            raise UnsafeUrl(
                "that service redirected to an address inside this network, "
                "which is refused"
            )
        # ⚠️ Only the first request carries `params`. After a redirect the
        # server has chosen the whole URL, query included, and re-appending ours
        # would either duplicate it or override what it asked for.
        params = None
