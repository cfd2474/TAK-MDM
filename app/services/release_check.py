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

"""Is this ATLAS behind the main release? (W499)

Operator: "add a version checker alert to the top of the dashboard, which
compares to the main release ... If current version is behind, show a banner
that says an update is available, contact your infraTAK admin to update. If its
current (or newer due to dev), don't show anything."

**Main, read as `VERSION` on the public mirror's `main` branch.** Only a
promotion moves that branch, so it *is* the main release, and a dev release
(newer than main) is "current", as asked. raw.githubusercontent.com is used,
not the Releases API, because the API allows 60 unauthenticated calls an hour
per address and a box behind a shared NAT could run out.

⚠️ **Never a false alarm, never a wait.** An offline or air-gapped box, a
GitHub outage or a version that does not parse all mean *no banner*: telling an
operator to call their InfraTAK admin about an update that may not exist costs
more than missing one. The dashboard only reads the cached answer; a background
thread does the fetching, so a slow GitHub never slows the page.

ATLAS cannot update itself (InfraTAK's update does it), which is why the banner
sends the reader to their InfraTAK administrator.
"""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

import httpx

log = logging.getLogger(__name__)

_TIMEOUT = 10.0
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def parse(text: str | None) -> tuple[int, int, int] | None:
    """`2.5.0` or `v2.5.0` as numbers; anything else None."""
    match = _VERSION.match((text or "").strip())
    if not match:
        return None
    major, minor, patch = (int(p) for p in match.groups())
    return major, minor, patch


def is_behind(current: str | None, latest: str | None) -> bool:
    """True only when both parse and `current` is older. Equal or newer (a dev
    release), or either unknown, is not behind."""
    mine, theirs = parse(current), parse(latest)
    return mine is not None and theirs is not None and mine < theirs


@dataclass(frozen=True)
class Notice:
    """What the dashboard banner says."""

    current: str
    latest: str


def fetch_main_version(url: str, client: httpx.Client | None = None) -> str | None:
    """The main release's version, or None when it cannot be read or parsed."""
    owned = client is None
    client = client or httpx.Client(timeout=_TIMEOUT, follow_redirects=True)
    try:
        response = client.get(url)
        if response.status_code != 200:
            log.info("release check: %s answered %s", url, response.status_code)
            return None
        text = response.text.strip()
        if parse(text) is None:
            log.info("release check: %s did not hold a version", url)
            return None
        return text.lstrip("v")
    except httpx.HTTPError as exc:
        log.info("release check: cannot read %s (%s)", url, exc.__class__.__name__)
        return None
    finally:
        if owned:
            client.close()


class ReleaseChecker:
    """Holds the last answer. `refresh` fetches; `notice` only reads."""

    def __init__(self, current: str | None, fetch: Callable[[], str | None]):
        self._current = current
        self._fetch = fetch
        self._latest: str | None = None
        self.checked_at: datetime | None = None
        self._lock = threading.Lock()

    def refresh(self) -> None:
        latest = self._fetch()
        with self._lock:
            # A failed read keeps nothing: an old answer must not hold a banner
            # up after the box has been updated and then lost its route out.
            self._latest = latest
            self.checked_at = datetime.now(timezone.utc)

    def notice(self) -> Notice | None:
        with self._lock:
            latest = self._latest
        if is_behind(self._current, latest):
            return Notice(current=self._current or "", latest=latest or "")
        return None


#: The process's checker, set by the startup thread; None means "not checking".
checker: ReleaseChecker | None = None


def current_notice() -> Notice | None:
    return checker.notice() if checker else None
