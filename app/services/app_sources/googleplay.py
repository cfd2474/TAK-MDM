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

"""Google Play as a source, through `apkeep` and a linked account (W99).

⚠️ **The credentials go in a `0600` ini file, never on the command line.** An AAS
token passed as `-t …` sits in argv, which anything able to read `/proc` on this
host can see. It is a durable bearer credential to a real Google account, so it
gets the same care as the device CA.

⚠️ **The device profile decides which build arrives.** Play serves device-matched
APKs: the profile is the architecture. It is stored on the link and passed
explicitly, because leaving it implicit is R19 through a different door — and it
travels into provenance so a build can be explained afterwards.

⚠️ **Play answers to an exact package id, not a name** — the same limit APKPure
has, and the console already states it for the unified search.

⚠️ **Nothing here is trusted for identity.** Play publishes no checksum through
this path, so `sha256` stays `None` and what the file actually is gets read by
`inspect_apk`, as with every other source.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.services.app_sources.base import (
    Downloaded,
    collect_output,
    SourceApp,
    SourceError,
    SourceVersion,
)

_PACKAGE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")

_TIMEOUT_SECONDS = 900

#: The listing link on Play's search page. ⚠️ **This is the load-bearing part and
#: the only one that must not fail**: the package id is what a fetch needs, it
#: lives in a URL, and a URL shape survives redesigns that rename every class.
_SEARCH_LINK = re.compile(
    r'href="/store/apps/details\?id=([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+)"'
)

#: The app name, when Play puts it on the link itself.
_ARIA_LABEL = re.compile(r'aria-label="([^"]{1,120})"')

_TAG = re.compile(r"<[^>]+>")

#: ⚠️ Whatever Play currently serves. Unlike an index, Play offers one build for a
#: given account and device — there is no version list to choose from, so the
#: console shows a single row and says as much.
LATEST = "latest"


def _extract_results(html: str, *, limit: int) -> dict[str, str]:
    """Package ids and names from Play's search page (W101).

    ⚠️ **Play renders two different card layouts and the difference is invisible
    until it bites.** A specific query returns list rows whose anchor carries the
    name::

        <a href="/store/apps/details?id=…" aria-label="Microsoft Outlook" class=…>

    A broad or brand query returns a grid whose anchor carries **no `aria-label`
    at all**::

        <a class="Si6A0c Gy4nib" href="/store/apps/details?id=…" jslog=…>

    A first version of this matched only the former. `outlook` and `handtevy`
    worked; `microsoft` and `esri` returned **nothing**, which reads as "Play has
    no Microsoft apps" rather than as a parsing failure. Both layouts are handled
    now, and both are in the tests.

    ⚠️ **The name is best effort; the package id is not.** The id comes from the
    href and is what a fetch needs. If a redesign hides the title, a row shows its
    package id and remains usable — degrading to something plainer, never to
    something wrong.
    """
    found: dict[str, str] = {}

    for match in _SEARCH_LINK.finditer(html):
        package = match.group(1)
        # First occurrence wins: Play lists the best match first, then repeats
        # apps in "similar" rails further down the page.
        if package in found:
            continue

        tag_end = html.find(">", match.end())
        if tag_end < 0:
            continue

        label = _ARIA_LABEL.search(html[match.start():tag_end])
        if label:
            found[package] = label.group(1).strip()
        else:
            # The grid layout: the first visible text inside the card is its
            # name. Read past the anchor's own closing bracket — starting at it
            # yields a stray ">" as the first "word", which is how this was
            # wrong the first time.
            text = _TAG.sub("\n", html[tag_end + 1:tag_end + 2500])
            runs = [run.strip() for run in text.split("\n") if run.strip()]
            found[package] = runs[0][:80] if runs else package

        if len(found) >= limit:
            break

    return found


class GooglePlaySource:
    """Fetch from Google Play as the linked account."""

    name = "google-play"
    label = "Google Play"

    def __init__(
        self,
        email: str,
        aas_token: str,
        *,
        device_profile: str = "px_9a",
        binary: str = "apkeep",
        runner=subprocess.run,
        ini_factory=None,
        client=None,
    ) -> None:
        self._email = email
        self._token = aas_token
        self._device = device_profile
        self._binary = binary
        self._runner = runner
        if ini_factory is None:
            from app.services.google_play_link import temporary_ini

            ini_factory = temporary_ini
        self._ini_factory = ini_factory
        # Injected so name search can be exercised without reaching Google — the
        # suite must not depend on a third party being up, or on the shape of a
        # page nobody here controls.
        self._client = client

    @property
    def available(self) -> bool:
        return bool(shutil.which(self._binary)) or Path(self._binary).exists()

    def _run(self, args: list[str], cwd: str | None = None):
        if not self.available:
            raise SourceError(
                "apkeep is not installed on this server, so Google Play cannot be "
                "reached. It is fetched into the image at build time; rebuild the "
                "api container if this persists."
            )
        # The ini exists only for the life of the call, and holds the token so the
        # command line never does.
        with self._ini_factory(self._email, self._token) as ini:
            try:
                return self._runner(
                    [
                        self._binary,
                        *args,
                        "-d",
                        "google-play",
                        "-i",
                        str(ini),
                        "-o",
                        f"device={self._device},split_apk=true",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=_TIMEOUT_SECONDS,
                    cwd=cwd,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise SourceError(f"apkeep timed out after {_TIMEOUT_SECONDS}s") from exc
            except OSError as exc:
                raise SourceError(f"could not run apkeep ({exc})") from exc

    # ----------------------------------------------------------------- #

    def search(self, query: str, *, limit: int = 25) -> list[SourceApp]:
        """Find apps by name, or take an exact package id (W101).

        ⚠️ **apkeep cannot search — this resolves names against Play's own search
        page.** The pattern used is the listing *link* and its `aria-label`
        (`/store/apps/details?id=…`), not a CSS class: a URL shape and an
        accessibility attribute both survive redesigns that break every scraper
        built on styling. That is why the earlier survey rejected the
        class-based scrapers and this is acceptable.

        It is still a page that can change without notice, so a failure here
        reports itself rather than pretending the catalogue is empty.
        """
        query = (query or "").strip()
        if not query:
            return []

        # An exact id needs no lookup, and is how a plugin or an app that does
        # not surface in search is reached.
        if _PACKAGE.match(query):
            return [
                SourceApp(
                    package_name=query,
                    name=query,
                    summary=f"Fetched as {self._email} (device {self._device}).",
                    web_url=f"https://play.google.com/store/apps/details?id={query}",
                    source=self.name,
                )
            ]

        return self._search_by_name(query, limit=limit)

    def _search_by_name(self, query: str, *, limit: int) -> list[SourceApp]:
        import httpx

        headers = {
            # Play serves a different, script-only page to a client that does not
            # look like a browser.
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }
        params = {"q": query, "c": "apps", "hl": "en", "gl": "US"}
        client = self._client or httpx.Client(
            timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True
        )
        try:
            response = client.get(
                "https://play.google.com/store/search", params=params, headers=headers
            )
        except httpx.HTTPError as exc:
            raise SourceError(f"could not reach Google Play search ({exc})") from exc
        finally:
            if self._client is None:
                client.close()

        if response.status_code != 200:
            raise SourceError(
                f"Google Play search returned {response.status_code}"
            )

        found = _extract_results(response.text, limit=limit)

        return [
            SourceApp(
                package_name=package,
                name=label or package,
                summary=f"Fetched as {self._email} (device {self._device}).",
                web_url=f"https://play.google.com/store/apps/details?id={package}",
                source=self.name,
            )
            for package, label in found.items()
        ]

    def versions(self, package_name: str, *, limit: int = 25) -> list[SourceVersion]:
        """The one build Play serves this account on this device profile."""
        package_name = (package_name or "").strip()
        if not _PACKAGE.match(package_name):
            raise SourceError(f"{package_name!r} is not a valid Android package id")

        return [
            SourceVersion(
                package_name=package_name,
                # Play states neither through this path; both are read from the
                # file once it arrives.
                version_code=None,
                version_name=LATEST,
                version_key=LATEST,
                download_url=f"google-play:{package_name}",
                source=self.name,
            )
        ]

    def download(self, version: SourceVersion) -> Downloaded:
        package_name = version.package_name
        if not _PACKAGE.match(package_name):
            raise SourceError(f"{package_name!r} is not a valid Android package id")

        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(["-a", package_name, "."], cwd=tmp)
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "").strip()[:200]
                raise SourceError(
                    f"apkeep could not download {package_name} from Google Play "
                    f"({detail or 'no output'})"
                )

            try:
                # ⚠️ Every part, not the largest one. See collect_output: a split
                # app truncated to its base installs nowhere and claims to run
                # everywhere.
                data = collect_output(Path(tmp))
            except SourceError as exc:
                raise SourceError(
                    f"{exc} for {package_name}."
                    f" A paid or region-locked app can do this — Play only serves"
                    f" what the linked account may have."
                ) from exc

        return Downloaded(
            data=data,
            sha256=hashlib.sha256(data).hexdigest(),
            # Play publishes no digest through this path; the bytes are checked by
            # reading them, not by comparison.
            verified=False,
            source_url=(
                f"https://play.google.com/store/apps/details?id={package_name} "
                f"(via apkeep, device={self._device})"
            ),
        )
