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
    SourceApp,
    SourceError,
    SourceVersion,
)

_PACKAGE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")

_TIMEOUT_SECONDS = 900

#: ⚠️ Whatever Play currently serves. Unlike an index, Play offers one build for a
#: given account and device — there is no version list to choose from, so the
#: console shows a single row and says as much.
LATEST = "latest"


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
        """Play has no name search here, so only an exact id can be confirmed."""
        query = (query or "").strip()
        if not _PACKAGE.match(query):
            return []
        return [
            SourceApp(
                package_name=query,
                name=query,
                summary=f"Google Play, as {self._email} (device {self._device}).",
                web_url=f"https://play.google.com/store/apps/details?id={query}",
                source=self.name,
            )
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

            files = [p for p in Path(tmp).rglob("*") if p.suffix in (".apk", ".xapk")]
            if not files:
                raise SourceError(
                    f"apkeep reported success but produced no file for {package_name}. "
                    f"A paid or region-locked app can do this — Play only serves what "
                    f"the linked account may have."
                )
            data = max(files, key=lambda p: p.stat().st_size).read_bytes()

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
