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

"""The TAKWERX plugin catalog as an app source (W279).

`github.com/takwerx/atak-plugins` is a development workspace; each plugin is
released from its own public repository, one APK per ATAK line. The catalog
that lists those releases -- the one the takwerx-market plugin reads -- is
hosted at `mapdepot.takwerx.org/depot`, in ATAK's own `product.inf` format:

    <depot>/product.inf              every ATAK version it serves, abridged
    <depot>/5.8.0.CIV/product.inf    everything built for ATAK 5.8.0

One row per build, comma separated, no quoting::

    platform, type, package, label, version, versionCode, apk path, icon path,
    description, sha256, min sdk, plugin-api (com.atakmap.app@5.8.0.CIV), size

⚠️ **The reason to read the catalog rather than the GitHub releases: it states
the SHA-256 of every APK.** A download that does not match is refused, the same
guarantee F-Droid gives, and the releases alone offer no digest at all.

⚠️ Not every row is by takwerx. The catalog also carries other authors'
plugins, and ATAK itself. ATAK is left out -- this is a plugin catalog, and
ATAK has its own place in the library -- and every row says whose it is
(operator decision, 2026-09-29: "all plugins, labelled").
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

from app.security import outbound
from app.services.app_sources.base import (
    Downloaded,
    Progress,
    SourceApp,
    SourceError,
    SourceVersion,
)

#: Where takwerx-market looks (`TakwerxMarket.DEFAULT_BASE_URL`).
CATALOG_URL = "https://mapdepot.takwerx.org/depot"

#: The GitHub owner whose plugins are first-party here.
FIRST_PARTY = "takwerx"

#: Offered when the combined catalog cannot be read, so the tab still has a
#: version to ask for. The lines the catalog served when this was written.
FALLBACK_ATAK_VERSIONS = ("5.8.0.CIV", "5.7.0.CIV", "5.6.0.CIV")

#: A catalog directory name. ⚠️ It becomes part of a URL path, so nothing that
#: could climb out of the depot is accepted -- the Market's own rule.
_VERSION_DIR = re.compile(r"^\d+(?:\.\d+)+\.[A-Za-z]+$")

#: "0.8 () - [5.8.0]" -> "0.8", "1.1 (2f06ef98) - [5.8.0]" -> "1.1 (2f06ef98)": the
#: trailing ATAK line is the version the operator chose, and an empty `()` says
#: nothing. A commit hash in the brackets is kept -- it identifies the build.
_VERSION_DECOR = re.compile(r"^(?P<version>.*?)\s*(?:\(\s*\))?\s*-\s*\[[^\]]*\]\s*$")

_MIN_COLUMNS = 12
_REDIRECTS = frozenset({301, 302, 303, 307, 308})
_TIMEOUT = httpx.Timeout(120.0, connect=15.0)


@dataclass(frozen=True)
class CatalogEntry:
    """One plugin build, as the catalog lists it."""

    package_name: str
    label: str
    version: str
    version_code: int
    apk_url: str
    description: str
    sha256: str | None
    min_sdk: int | None
    plugin_api: str
    size: int | None

    @property
    def atak_version(self) -> str:
        """`com.atakmap.app@5.8.0.CIV` -> `5.8.0.CIV`."""
        return self.plugin_api.split("@", 1)[1] if "@" in self.plugin_api else ""

    @property
    def display_version(self) -> str:
        return display_version_of(self.version)

    @property
    def author(self) -> str:
        """Whose build this is: the GitHub owner, or the host serving it."""
        url = urlparse(self.apk_url)
        if url.hostname == "github.com":
            owner = url.path.strip("/").split("/", 1)[0]
            if owner:
                return owner
        return url.hostname or "unknown"

    @property
    def first_party(self) -> bool:
        return self.author.lower() == FIRST_PARTY


def display_version_of(text: str | None) -> str:
    """An ATAK plugin version as an operator reads it (see `_VERSION_DECOR`).

    Shared with the library-status pills (W281), so a held build's name reads
    the same as the catalog row beside it.
    """
    text = text or ""
    match = _VERSION_DECOR.match(text)
    return (match.group("version") if match else text) or text


def is_version(value: str | None) -> bool:
    return bool(value) and bool(_VERSION_DIR.match(value)) and ".." not in value


def version_sort_key(value: str) -> tuple[int, ...]:
    return tuple(int(p) for p in value.split(".") if p.isdigit())


def unescape(text: str) -> str:
    """The Market's `unescape`: a comma inside a field is `\\u002c`, a line
    break `\\n`. There is no quoting."""
    return text.strip().replace("\\u002c", ",").replace("\\n", "\n")


def _int(text: str) -> int | None:
    try:
        return int(text.strip())
    except ValueError:
        return None


def parse(text: str, base_url: str = CATALOG_URL) -> list[CatalogEntry]:
    """Every Android *plugin* row in a catalog; anything else is skipped.

    Read defensively, like the Market reads it: a row that does not parse costs
    that row, not the page.
    """
    base = base_url.rstrip("/") + "/"
    out: list[CatalogEntry] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cols = line.split(",")
        if len(cols) < _MIN_COLUMNS:
            continue
        platform, kind, package = unescape(cols[0]), unescape(cols[1]), unescape(cols[2])
        if platform.lower() != "android" or kind.lower() != "plugin" or not package:
            continue
        version_code = _int(cols[5])
        path = unescape(cols[6])
        if version_code is None or not path:
            continue
        digest = unescape(cols[9]).lower()
        out.append(
            CatalogEntry(
                package_name=package,
                label=unescape(cols[3]) or package,
                version=unescape(cols[4]),
                version_code=version_code,
                # Relative paths are relative to the depot root, not to the
                # per-version directory -- measured, `depot/atak/…` answers and
                # `depot/5.8.0.CIV/atak/…` is a 404.
                apk_url=urljoin(base, path),
                description=unescape(cols[8]),
                sha256=digest if re.fullmatch(r"[0-9a-f]{64}", digest) else None,
                min_sdk=_int(cols[10]),
                plugin_api=unescape(cols[11]),
                size=_int(cols[12]) if len(cols) > 12 else None,
            )
        )
    return out


def versions_in(text: str) -> list[str]:
    """The ATAK versions a catalog names, newest first."""
    found = {e.atak_version for e in parse(text)} - {""}
    return sorted((v for v in found if is_version(v)), key=version_sort_key, reverse=True)


class TakwerxSource:
    """The catalog for one ATAK version, behind the `AppSource` protocol.

    One instance per version on purpose: the version is the question the
    operator is asking, and a source that answered for every version at once
    would offer a 5.6.0 build to someone who chose 5.8.0.
    """

    name = "takwerx"
    label = "TAKWERX"

    def __init__(
        self,
        atak_version: str,
        *,
        client: httpx.Client | None = None,
        base_url: str = CATALOG_URL,
    ) -> None:
        if not is_version(atak_version):
            raise SourceError(f"{atak_version!r} is not an ATAK version")
        self.atak_version = atak_version
        self._client = client
        self._base = base_url.rstrip("/")
        self._entries: list[CatalogEntry] | None = None

    # ----------------------------------------------------------------- #
    # Reading the catalog
    # ----------------------------------------------------------------- #

    def _http(self) -> httpx.Client:
        # ⚠️ No `follow_redirects`: every hop is checked by hand (see `_guard`).
        return self._client or httpx.Client(timeout=_TIMEOUT)

    def _get_text(self, url: str) -> str:
        client = self._http()
        try:
            response = outbound.fetch(client, url)
        except outbound.UnsafeUrl as exc:
            raise SourceError(f"refusing the TAKWERX catalog at {url}: {exc}") from exc
        except httpx.HTTPError as exc:
            raise SourceError(f"could not reach the TAKWERX catalog ({exc})") from exc
        finally:
            if self._client is None:
                client.close()
        if response.status_code != 200:
            raise SourceError(
                f"the TAKWERX catalog returned {response.status_code} for {url}"
            )
        return response.text

    def available_versions(self) -> list[str]:
        """Every ATAK version the depot serves, from the combined catalog.

        ⚠️ Falls back rather than failing: the combined catalog is only how the
        dropdown is filled, and an outage there should not stop an operator
        asking for a version they already know.
        """
        try:
            found = versions_in(self._get_text(f"{self._base}/product.inf"))
        except SourceError:
            found = []
        return found or list(FALLBACK_ATAK_VERSIONS)

    def catalog(self) -> list[CatalogEntry]:
        """Every plugin built for this ATAK version."""
        if self._entries is None:
            text = self._get_text(f"{self._base}/{self.atak_version}/product.inf")
            # ⚠️ Filtered to this version even though the file is per-version:
            # a row the depot misfiled would otherwise be offered as a build
            # for the ATAK the operator chose.
            self._entries = [
                e for e in parse(text, self._base) if e.atak_version == self.atak_version
            ]
        return self._entries

    # ----------------------------------------------------------------- #
    # AppSource
    # ----------------------------------------------------------------- #

    def search(self, query: str, *, limit: int = 25) -> list[SourceApp]:
        needle = (query or "").strip().lower()
        seen: dict[str, SourceApp] = {}
        for e in self.catalog():
            haystack = f"{e.label} {e.package_name} {e.description}".lower()
            if needle in haystack and e.package_name not in seen:
                seen[e.package_name] = SourceApp(
                    package_name=e.package_name,
                    name=e.label,
                    summary=e.description or None,
                    source=self.name,
                )
        return list(seen.values())[:limit]

    def versions(self, package_name: str, *, limit: int = 25) -> list[SourceVersion]:
        out = [
            SourceVersion(
                package_name=e.package_name,
                version_code=e.version_code,
                version_name=e.display_version,
                download_url=e.apk_url,
                size=e.size,
                sha256=e.sha256,
                min_sdk=e.min_sdk,
                source=self.name,
            )
            for e in self.catalog()
            if e.package_name == package_name
        ]
        out.sort(key=lambda v: v.version_code or 0, reverse=True)
        return out[:limit]

    def _guard(self, url: str) -> None:
        """Refuse a hop that is not https or that lands inside this network.

        ⚠️ Stricter than `outbound.fetch`, on purpose. That guard lets an
        administrator point at their own LAN; nobody here chose these URLs --
        they are a third party's catalog -- so no hop may be internal at all,
        the first one included.
        """
        if urlparse(url).scheme != "https":
            raise SourceError(
                f"refusing {url}: the TAKWERX catalog must serve downloads over "
                f"https. Nothing was imported."
            )
        try:
            target = outbound.inspect(url)
        except outbound.UnsafeUrl as exc:
            raise SourceError(f"refusing {url}: {exc}. Nothing was imported.") from exc
        if target.is_internal:
            raise SourceError(
                f"refusing {url}: it resolves to an address inside this network, "
                f"and a catalog download never should. Nothing was imported."
            )

    def download(self, version: SourceVersion, progress: Progress | None = None) -> Downloaded:
        if not version.sha256:
            # ⚠️ Refused, not warned. Every row this catalog publishes carries a
            # digest; one without is malformed, and verification is the reason
            # this source was chosen over the bare GitHub releases.
            raise SourceError(
                f"the TAKWERX catalog gives no SHA-256 for {version.package_name} "
                f"{version.version_code}, so the download cannot be verified. "
                f"Nothing was imported."
            )

        client = self._http()
        chunks: list[bytes] = []
        current = version.download_url
        try:
            # GitHub answers a release download with a redirect to its storage
            # host, so following is normal -- but by hand, each hop guarded.
            for _hop in range(outbound.MAX_REDIRECTS + 1):
                self._guard(current)
                response = client.send(
                    client.build_request("GET", current), stream=True, follow_redirects=False
                )
                try:
                    if response.status_code in _REDIRECTS and response.headers.get("location"):
                        current = urljoin(current, response.headers["location"])
                        continue
                    if response.status_code != 200:
                        raise SourceError(
                            f"{version.download_url} returned {response.status_code}"
                        )
                    total = int(response.headers.get("content-length") or 0) or (version.size or 0)
                    written = 0
                    for chunk in response.iter_bytes():
                        chunks.append(chunk)
                        written += len(chunk)
                        # ⚠️ The catalog states the size; a response running past
                        # it cannot be the file whose digest it published, so stop
                        # reading rather than buffer whatever is being sent.
                        if version.size and written > version.size:
                            raise SourceError(
                                f"{version.download_url} sent more than the "
                                f"{version.size} bytes the catalog lists. Nothing "
                                f"was imported."
                            )
                        if progress is not None:
                            progress(written, total)
                    break
                finally:
                    response.close()
            else:
                raise SourceError(
                    f"{version.download_url} redirected more than "
                    f"{outbound.MAX_REDIRECTS} times. Nothing was imported."
                )
        except httpx.HTTPError as exc:
            raise SourceError(f"could not download {version.download_url} ({exc})") from exc
        finally:
            if self._client is None:
                client.close()

        data = b"".join(chunks)
        digest = hashlib.sha256(data).hexdigest()
        if digest != version.sha256:
            raise SourceError(
                f"{version.package_name} {version.version_code} does not match the "
                f"digest the TAKWERX catalog published (expected "
                f"{version.sha256[:16]}…, got {digest[:16]}…). Nothing was imported."
            )
        return Downloaded(data=data, sha256=digest, verified=True, source_url=version.download_url)
