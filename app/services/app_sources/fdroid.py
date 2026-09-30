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

"""F-Droid as an app source (W97).

⚠️ **The reason this source comes first: it can be checked.** `entry.json` is
small and states the SHA-256 of the full index; the index states the SHA-256 of
every APK in it. So the chain *entry → index → file* is verifiable end to end, and
a download that does not match what was published is refused rather than
inspected and hoped over.

Measured against the live repository on 2026-09-07: the index is **58.9 MB across
4335 packages**, and its published digest matched the bytes received.

⚠️ **The index is big enough that fetching it per search would be absurd**, so it
is cached on disk and only re-fetched when `entry.json` says the digest changed.
That check costs a few kilobytes.

What the index gives that matters here, per build::

    file.sha256                    -> verify the download
    manifest.nativecode            -> the ABIs it carries (W96)
    manifest.usesSdk.minSdkVersion -> the API level it needs
    manifest.signer.sha256         -> the signing certificate

Which means the console can answer *"will this run on my devices"* **before**
importing, rather than discovering it as a failed install days later (R19).
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from app.services.app_sources.base import (
    Downloaded,
    Progress,
    SourceApp,
    SourceError,
    SourceVersion,
)

REPO = "https://f-droid.org/repo"
ENTRY = f"{REPO}/entry.json"

#: The index is 59 MB; a search must not pay for that. Re-checked against
#: `entry.json` at most this often, which costs a few kilobytes.
_ENTRY_TTL_SECONDS = 3600

_TIMEOUT = httpx.Timeout(120.0, connect=15.0)
_CHUNK = 1 << 20


def _text(value: Any) -> str | None:
    """F-Droid localises names and summaries as ``{"en-US": "...", "de": "..."}``.

    English first, then whatever the first entry is — a name in the wrong language
    is far more use to an operator than no name at all.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and value:
        for key in ("en-US", "en"):
            if key in value:
                return str(value[key])
        return str(next(iter(value.values())))
    return None


class FDroidSource:
    """Search and fetch from F-Droid's signed index."""

    def __init__(
        self,
        cache_dir: Path,
        *,
        client: httpx.Client | None = None,
        repo: str = REPO,
        name: str = "fdroid",
        label: str = "F-Droid",
    ) -> None:
        self._cache_dir = Path(cache_dir)
        self._client = client
        self._repo = repo.rstrip("/")
        # ⚠️ Per instance, not per class (W97 C3). Several repositories speak this
        # format, and the name is stored as provenance on whatever is imported —
        # a build from IzzyOnDroid recorded as "fdroid" would be a lie in the one
        # field that exists to answer "where did this come from".
        self.name = name
        self.label = label
        self._index: dict[str, Any] | None = None
        self._checked_at = 0.0
        # ⚠️ One loader at a time (W103). The warm-up thread and the concurrent
        # search pool now call `index()` together, and without this each would
        # download and parse the same 111 MB independently — competing for CPU,
        # and writing the same `.part` file underneath one another.
        self._lock = threading.Lock()

    # ----------------------------------------------------------------- #
    # The index
    # ----------------------------------------------------------------- #

    def _get_streamed(self, url: str, progress) -> bytes:
        """Read a download in chunks, reporting as it goes."""
        if progress is None:
            return self._get(url).content

        client = self._client or httpx.Client(timeout=_TIMEOUT, follow_redirects=True)
        chunks: list[bytes] = []
        try:
            with client.stream("GET", url) as response:
                if response.status_code != 200:
                    raise SourceError(
                        f"F-Droid returned {response.status_code} for {url}"
                    )
                total = int(response.headers.get("content-length") or 0)
                written = 0
                for chunk in response.iter_bytes():
                    chunks.append(chunk)
                    written += len(chunk)
                    progress(written, total)
        except httpx.HTTPError as exc:
            raise SourceError(f"could not reach F-Droid ({exc})") from exc
        finally:
            if self._client is None:
                client.close()
        return b"".join(chunks)

    def _get(self, url: str) -> httpx.Response:
        client = self._client or httpx.Client(timeout=_TIMEOUT, follow_redirects=True)
        try:
            response = client.get(url)
        except httpx.HTTPError as exc:
            raise SourceError(f"could not reach F-Droid ({exc})") from exc
        finally:
            if self._client is None:
                client.close()
        if response.status_code != 200:
            raise SourceError(f"F-Droid returned {response.status_code} for {url}")
        return response

    def _entry(self) -> dict[str, Any]:
        payload = self._get(f"{self._repo}/entry.json").json()
        index = payload.get("index") or {}
        if not index.get("name") or not index.get("sha256"):
            raise SourceError("F-Droid's entry.json does not name an index to fetch")
        return index

    def _index_path(self) -> Path:
        # ⚠️ Named per repository. A shared filename would have one repository's
        # index overwrite another's — and since each is verified against its own
        # `entry.json`, the collision would surface as a digest mismatch, or
        # worse, as the wrong catalogue answering.
        return self._cache_dir / f"{self.name}-index-v2.json"

    def index(self) -> dict[str, Any]:
        """The parsed index, fetched only when its published digest changes.

        ⚠️ **Loaded under a lock, and re-checked inside it.** Several threads
        arrive here at once now — the boot warm-up and every source in a
        concurrent search — and the first version let all of them download and
        parse the same file at the same time. The second search after a restart
        was instant while the first took 36 seconds, because it was racing the
        warm-up for the same work.

        Waiting on the lock is the point: the loser gets the winner's result
        rather than repeating it.
        """
        now = time.time()
        if self._index is not None and (now - self._checked_at) < _ENTRY_TTL_SECONDS:
            return self._index

        with self._lock:
            # Re-checked inside the lock: whoever held it may have just finished
            # the exact work this thread was about to start.
            now = time.time()
            if self._index is not None and (now - self._checked_at) < _ENTRY_TTL_SECONDS:
                return self._index

            entry = self._entry()
            self._checked_at = now
            path = self._index_path()

            if path.exists() and _digest_of(path) == entry["sha256"]:
                if self._index is None:
                    self._index = json.loads(path.read_text(encoding="utf-8"))
                return self._index

            self._download_index(entry)
            self._index = json.loads(path.read_text(encoding="utf-8"))
            return self._index

    def _download_index(self, entry: dict[str, Any]) -> None:
        """Fetch the index and refuse it unless it is what `entry.json` promised."""
        url = f"{self._repo}{entry['name']}"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        # Named per writer as well as per repository: the lock makes a collision
        # unlikely, but a shared staging file is the kind of thing that only
        # corrupts under load, which is when nobody is looking.
        temp = self._index_path().with_suffix(f".{os.getpid()}.{threading.get_ident()}.part")

        digest = hashlib.sha256()
        client = self._client or httpx.Client(timeout=_TIMEOUT, follow_redirects=True)
        try:
            with client.stream("GET", url) as response:
                if response.status_code != 200:
                    raise SourceError(f"F-Droid returned {response.status_code} for the index")
                with temp.open("wb") as handle:
                    for chunk in response.iter_bytes(_CHUNK):
                        digest.update(chunk)
                        handle.write(chunk)
        except httpx.HTTPError as exc:
            temp.unlink(missing_ok=True)
            raise SourceError(f"could not fetch the F-Droid index ({exc})") from exc
        finally:
            if self._client is None:
                client.close()

        if digest.hexdigest() != entry["sha256"]:
            # ⚠️ Never keep it. An index that is not what was published is the one
            # thing that could quietly poison every hash checked against it.
            temp.unlink(missing_ok=True)
            raise SourceError(
                "the F-Droid index does not match the digest entry.json published "
                f"(expected {entry['sha256'][:16]}…, got {digest.hexdigest()[:16]}…). "
                "Nothing was cached."
            )
        temp.replace(self._index_path())

    # ----------------------------------------------------------------- #
    # The interface
    # ----------------------------------------------------------------- #

    def search(self, query: str, *, limit: int = 25) -> list[SourceApp]:
        query = (query or "").strip().lower()
        if not query:
            return []

        found: list[tuple[int, SourceApp]] = []
        for package_name, entry in (self.index().get("packages") or {}).items():
            metadata = entry.get("metadata") or {}
            name = _text(metadata.get("name")) or package_name
            summary = _text(metadata.get("summary"))

            haystack = f"{name}\n{package_name}".lower()
            if query not in haystack:
                continue
            # An exact package match, then a name that starts with the query, then
            # the rest: someone typing a package name wants that app, not the 40
            # others whose description mentions it.
            rank = 0 if package_name.lower() == query else 1 if name.lower().startswith(query) else 2
            found.append(
                (
                    rank,
                    SourceApp(
                        package_name=package_name,
                        name=name,
                        summary=summary,
                        web_url=f"https://f-droid.org/packages/{package_name}/",
                        source=self.name,
                    ),
                )
            )

        found.sort(key=lambda pair: (pair[0], pair[1].name.lower()))
        return [app for _, app in found[:limit]]

    def versions(self, package_name: str, *, limit: int = 25) -> list[SourceVersion]:
        entry = (self.index().get("packages") or {}).get(package_name)
        if entry is None:
            raise SourceError(f"{package_name} is not in the F-Droid index")

        out: list[SourceVersion] = []
        for version in (entry.get("versions") or {}).values():
            file = version.get("file") or {}
            manifest = version.get("manifest") or {}
            name = file.get("name")
            code = manifest.get("versionCode")
            if not name or code is None:
                continue

            signer = (manifest.get("signer") or {}).get("sha256") or []
            native = manifest.get("nativecode")
            out.append(
                SourceVersion(
                    package_name=package_name,
                    version_code=int(code),
                    version_name=manifest.get("versionName"),
                    # The index keys builds by versionCode, so that is the handle.
                    version_key=str(int(code)),
                    download_url=f"{self._repo}{name}",
                    size=file.get("size"),
                    sha256=file.get("sha256"),
                    # ⚠️ None vs () matters (W96): absent means the index does not
                    # say, empty means it says there is no native code at all.
                    abis=tuple(native) if native is not None else None,
                    min_sdk=(manifest.get("usesSdk") or {}).get("minSdkVersion"),
                    signer_sha256=signer[0] if signer else None,
                    source=self.name,
                )
            )

        out.sort(key=lambda v: v.version_code, reverse=True)
        return out[:limit]

    def download(
        self, version: SourceVersion, progress: Progress | None = None
    ) -> Downloaded:
        # ⚠️ Streamed so the bar can move. `Content-Length` also supplies a
        # total when the catalogue omitted the size, which is the difference
        # between a real percentage and a byte counter (W127).
        data = self._get_streamed(version.download_url, progress)
        digest = hashlib.sha256(data).hexdigest()

        if version.sha256 and digest != version.sha256:
            raise SourceError(
                f"{version.package_name} {version.version_code} does not match the "
                f"digest F-Droid published (expected {version.sha256[:16]}…, got "
                f"{digest[:16]}…). Nothing was imported."
            )

        return Downloaded(
            data=data,
            sha256=digest,
            verified=bool(version.sha256),
            source_url=version.download_url,
        )


def _digest_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()
