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

"""Is certificate renewal ready on this server? (W463)

Renewal (W458) needs InfraTAK to make the `atlas-renewal` Authentik account and
write its token, and (W461) to copy TAK Server's revoked list. An ATLAS updated
on an InfraTAK without those changes renews nothing, and the client key alone
(`tak_renewal.configured`) does not show it. The Retire step warns with these
problems, because a QR-enrolled device then stays on the retired CA until it
gets a new QR code.

Warning only: a connection an ATLAS policy manages moves without renewal.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from app.config import get_settings
from app.services import tak_renewal
from app.services.tak_renewal import RenewalClient

#: The step that repairs most problems.
UPDATE = ("In InfraTAK, check that Renewal is on for this ATLAS deployment, "
          "then press Update for ATLAS.")

#: Seconds an answer is kept. An admin page renders every tab at once.
TTL = 60


@dataclass(frozen=True)
class Readiness:
    problems: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return not self.problems


def check(client: RenewalClient | None) -> Readiness:
    """Ask the renewal container. Never raises."""
    if client is None:
        return Readiness((
            "InfraTAK has not set up certificate renewal on this server: there is "
            "no renewal account. This needs an InfraTAK version with ATLAS "
            "certificate renewal. Update InfraTAK, then press Update for ATLAS.",))
    try:
        body = client.status()
    except tak_renewal.Unavailable as exc:
        return Readiness(("ATLAS gets no answer from the renewal container (%s). %s" % (exc, UPDATE),))
    except (tak_renewal.Refusal, ValueError) as exc:
        return Readiness(("The renewal container gave an unexpected answer (%s). %s" % (exc, UPDATE),))
    problems = []
    missing = body.get("missing") or []
    account = body.get("account") or {}
    revocation = body.get("revocation") or {}
    if missing:
        problems.append("InfraTAK has not written these renewal files: %s. %s"
                        % (", ".join(map(str, missing)), UPDATE))
    elif not account.get("ok"):
        problems.append("The renewal account in Authentik does not work: %s. Press Update "
                        "for ATLAS in InfraTAK to make it again." % account.get("detail", "unknown"))
    if not revocation.get("ok"):
        problems.append("InfraTAK does not send TAK Server's list of revoked certificates "
                        "(%s). This needs a newer InfraTAK. Until then, every renewal is refused."
                        % revocation.get("detail", "unknown"))
    return Readiness(tuple(problems))


class _Cache:
    """One answer per renewal address and key, for `TTL` seconds."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._entry: tuple[tuple[str, str], float, Readiness] | None = None

    def get(self, key: tuple[str, str], compute: Callable[[], Readiness]) -> Readiness:
        now = self._clock()
        if self._entry and self._entry[0] == key and now - self._entry[1] < TTL:
            return self._entry[2]
        value = compute()
        self._entry = (key, now, value)
        return value


_cache = _Cache()


def current() -> Readiness:
    settings = get_settings()
    return _cache.get((settings.renewal_url, settings.renewal_client_key),
                      lambda: check(tak_renewal.client_from_settings()))
