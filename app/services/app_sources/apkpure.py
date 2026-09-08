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

"""APKPure, reached through EFF's `apkeep` (W98).

⚠️ **Not a scrape.** APKPure's *website* refuses a server outright — measured
2026-09-07, and `cloudscraper` does not get past it. Its **app API**
(`api.pureapk.com`) is a different endpoint that answers normally, and `apkeep`
speaks it. That distinction is the whole reason this source can exist.

`apkeep` is MIT, maintained by the EFF, and invoked as a subprocess rather than
imported — it is Rust, so there is nothing to conflict with this project's Python
dependencies. Its output goes through the ordinary ingest path, so identity and
signature continuity are still read from the file rather than believed from here.

⚠️ **The architecture is always pinned, and this is not optional.** `apkeep`
documents its default as preferring `arm64-v8a`, and on the first real fetch it
returned an `armeabi-v7a` build anyway — for a fleet that is arm64-only. That is
R19's exact shape. A build for the wrong CPU installs nowhere and fails forever,
so `-o arch=` is always passed, and what actually arrives is still checked by
reading the file (W96).

⚠️ **APKPure publishes no checksum**, so `sha256` stays `None` here — meaning
*"this source does not say"*, never *"it matched"*. Verification is what
`inspect_apk` does to the bytes afterwards.

⚠️ **There is no search.** `apkeep` answers for an exact package id and nothing
else, so [search] can only confirm that an id exists. An operator typing a name
gets no APKPure row, and the console says why rather than leaving them to wonder.
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

#: The fleet this console was built for is arm64. See the module note on why a
#: default is never relied upon and this is passed explicitly every time.
DEFAULT_ARCH = "arm64-v8a"

#: An Android package id. Validated before it reaches a command line — the call
#: uses no shell, but a value that cannot be a package should not travel at all.
_PACKAGE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")

_TIMEOUT_SECONDS = 600


class ApkPureSource:
    """Look up and fetch builds from APKPure via `apkeep`."""

    name = "apkpure"
    label = "APKPure"

    def __init__(
        self,
        binary: str = "apkeep",
        *,
        arch: str = DEFAULT_ARCH,
        runner=subprocess.run,
    ) -> None:
        self._binary = binary
        self._arch = arch
        # Injected so the tests never shell out, and so a failure mode can be
        # arranged rather than waited for.
        self._runner = runner

    # ----------------------------------------------------------------- #

    @property
    def available(self) -> bool:
        """Is apkeep actually installed?"""
        return bool(shutil.which(self._binary)) or Path(self._binary).exists()

    def _run(self, args: list[str], cwd: str | None = None):
        if not self.available:
            raise SourceError(
                "apkeep is not installed on this server, so APKPure cannot be "
                "searched. It is fetched into the image at build time; rebuild "
                "the api container if this persists."
            )
        try:
            return self._runner(
                [self._binary, *args],
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
        """Confirm an exact package id exists. APKPure has no name search here.

        Returning nothing for a name is correct, not a failure — the console
        explains the limit rather than letting it look like an outage.
        """
        query = (query or "").strip()
        if not _PACKAGE.match(query):
            return []
        if not self.versions(query, limit=1):
            return []
        return [
            SourceApp(
                package_name=query,
                name=query,
                summary="Found on APKPure by package id.",
                web_url=f"https://apkpure.com/search?q={query}",
                source=self.name,
            )
        ]

    def versions(self, package_name: str, *, limit: int = 25) -> list[SourceVersion]:
        package_name = (package_name or "").strip()
        if not _PACKAGE.match(package_name):
            raise SourceError(f"{package_name!r} is not a valid Android package id")

        result = self._run(
            ["-l", "-a", package_name, "-o", f"arch={self._arch}"]
        )
        if result.returncode != 0:
            raise SourceError(
                f"apkeep could not list {package_name} "
                f"({(result.stderr or '').strip()[:160] or 'no output'})"
            )

        names = _parse_versions(result.stdout or "")
        if not names:
            return []

        # ⚠️ Newest last in apkeep's output is not guaranteed, and these are
        # version *names* — not comparable as numbers. Reversed rather than
        # sorted, so the order shown is the source's own, not one invented here.
        return [
            SourceVersion(
                package_name=package_name,
                # Unknown until the file is read. See SourceVersion.version_code.
                version_code=None,
                version_name=name,
                version_key=name,
                download_url=f"apkeep:{package_name}@{name}",
                source=self.name,
            )
            for name in list(reversed(names))[:limit]
        ]

    def download(self, version: SourceVersion) -> Downloaded:
        package_name = version.package_name
        if not _PACKAGE.match(package_name):
            raise SourceError(f"{package_name!r} is not a valid Android package id")

        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(
                [
                    "-a",
                    f"{package_name}@{version.version_key}",
                    "-o",
                    f"arch={self._arch}",
                    ".",
                ],
                cwd=tmp,
            )
            if result.returncode != 0:
                raise SourceError(
                    f"apkeep could not download {package_name}@{version.version_key} "
                    f"({(result.stderr or '').strip()[:160] or 'no output'})"
                )

            try:
                # ⚠️ Every part, not the largest one. See collect_output: a split
                # app truncated to its base installs nowhere and claims to run
                # everywhere.
                data = collect_output(Path(tmp))
            except SourceError as exc:
                raise SourceError(
                    f"{exc} for {package_name}."
                ) from exc

        return Downloaded(
            data=data,
            sha256=hashlib.sha256(data).hexdigest(),
            # ⚠️ False, always: APKPure publishes nothing to check this against.
            verified=False,
            source_url=f"https://apkpure.com/{package_name} (via apkeep, "
            f"arch={self._arch})",
        )


def _parse_versions(output: str) -> list[str]:
    """Pull version names out of apkeep's listing.

    Its output is a header line followed by one beginning with a pipe::

        Versions available for net.osmand on APKPure:
        | 4.7.1, 4.7.10, 5.0.4, …
    """
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("|"):
            return [part.strip() for part in line.lstrip("|").split(",") if part.strip()]
    return []
