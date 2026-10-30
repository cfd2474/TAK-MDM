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

"""What Google Play offers a search row's app, beside what the library holds (W435).

Operator: "Is there a way to ping the Google play version that comes up of an
app when we run a search? Something we can use to compare against the library
version?"

⚠️ **Only as a fleet profile.** The answer belongs to one device profile, and
the built-in Flagship is apkeep's AuroraOSS data (GPL-3.0) that ATLAS keeps no
copy of. With a built-in chosen, the rows say so rather than guess.

⚠️ **It informs; it never acts**, as `catalog_status` does. And it is
"currently offers", not "you will get": a staged rollout can serve the download
a different build (docs/GOOGLE_PLAY_DETAILS.md).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.services import catalog_status, google_play_link, play_profiles
from app.services.app_sources.base import SourceError
from app.services.app_sources.play_details import PlayBuild, PlayDetails

#: Seconds per request to Play. A search row waits on this, so it is short:
#: a slow answer is shown as "version unknown", never as a stalled page.
TIMEOUT_SECONDS = 6.0

#: The most packages one call looks up -- more than any search returns.
MAX_PACKAGES = 50

NOT_FLEET = (
    "Pick one of your own devices under Download as to see the version Play "
    "offers it. The Flagship Smartphone can't be asked directly."
)
NOT_LINKED = "No Google account is linked."


@dataclass(frozen=True)
class Offer:
    """One package: what Play offers this profile, and the library pill."""

    package_name: str
    #: None when Play offers this profile no build of it.
    build: PlayBuild | None
    library: catalog_status.RowStatus | None = None

    def as_json(self) -> dict:
        lib = None
        if self.library is not None:
            lib = {"kind": self.library.kind, "version_name": self.library.held.version_name,
                   "version_code": self.library.held.version_code}
        return {
            "offered": self.build is not None,
            "version_code": self.build.version_code if self.build else None,
            "version_name": self.build.version_name if self.build else None,
            "library": lib,
        }


@dataclass(frozen=True)
class Answer:
    """The whole lookup. `note` explains an answer with no versions in it."""

    offers: dict[str, Offer] = field(default_factory=dict)
    note: str | None = None
    #: True when the note is a failure rather than a choice ("version unknown").
    failed: bool = False

    def as_json(self) -> dict:
        return {
            "versions": {name: offer.as_json() for name, offer in self.offers.items()},
            "note": self.note,
            "failed": self.failed,
        }


Details = Callable[[str, str, dict], PlayDetails]


def lookup(
    session: Session,
    vault,
    device_profile: str,
    packages: Iterable[str],
    *,
    details: Details | None = None,
) -> Answer:
    """Play's current build of each package as `device_profile`, with the library pill.

    `details` builds the client; a test passes one that never reaches Google.
    """
    details = details or client_for_search
    wanted = list(dict.fromkeys(p.strip() for p in packages if p and p.strip()))[:MAX_PACKAGES]
    if not wanted:
        return Answer()
    properties = play_profiles.fleet_properties(session, device_profile)
    if properties is None:
        return Answer(note=NOT_FLEET)
    linked = google_play_link.credentials(session, vault)
    if linked is None:
        return Answer(note=NOT_LINKED, failed=True)
    email, token, _stored = linked
    try:
        found = details(email, token, properties).lookup(wanted)
    except SourceError as exc:
        # Already redacted by the client: no token, no email, no URL.
        return Answer(note=f"Version unknown: {exc}", failed=True)

    held = catalog_status.library_builds(session, wanted)
    offers = {}
    for name in wanted:
        build = found.get(name)
        status = catalog_status.status_for(held.get(name, []), build.version_code) if build else None
        offers[name] = Offer(name, build, status)
    return Answer(offers=offers)


def client_for_search(email: str, token: str, properties: dict) -> PlayDetails:
    """The search's client: a short timeout, the process's shared sign-ins."""
    return PlayDetails(email, token, properties, timeout=TIMEOUT_SECONDS)
