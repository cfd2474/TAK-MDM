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

"""What a third-party app repository has to be able to answer (W97).

Two sources sit behind this, and they are **not** equally trustworthy:

* **F-Droid** publishes a signed index that states, for every build, its SHA-256,
  the ABIs it carries, its `minSdkVersion` and its signing certificate. A download
  can be verified against the index, and the index against `entry.json`.
* **APKPure** is scraped. It offers no hash and no declared ABIs, so a download
  can only be checked *after* the fact, by reading the file.

⚠️ **That difference is modelled, not smoothed over.** `SourceVersion.sha256` is
optional and `None` means *"this source does not say"* — never *"it matched"*.
Faking a hash to keep the type tidy would turn an unverifiable download into one
that looks verified, which is the whole risk of pulling binaries from a mirror.

⚠️ **Nothing here is trusted for identity.** Every field is a *claim by the
catalogue*, useful for showing the operator what they are about to fetch and for
refusing an obvious mismatch early. The package name, version code and signing
certificate that actually get recorded are read from the downloaded file by
`inspect_apk` — the same rule `tak_gov_link.import_plugin` states: identity comes
from the file, not from the listing.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class SourceApp:
    """One app as a catalogue lists it."""

    #: Android package name. The join to everything else ATLAS knows.
    package_name: str
    #: Human name, for the operator. Falls back to the package name.
    name: str
    summary: str | None = None
    #: Where a person can read about it, for an operator who wants to check.
    web_url: str | None = None
    icon_url: str | None = None
    #: Which source produced this row, so the console can say so plainly.
    source: str = ""


@dataclass(frozen=True)
class SourceVersion:
    """One downloadable build, as a catalogue describes it."""

    package_name: str
    #: ⚠️ **Optional, because not every source knows it before downloading** (W98).
    #: APKPure states version *names* only; the real versionCode is read from the
    #: file at ingest, where it was always the authoritative answer. Inventing one
    #: here would put a fabricated number in a field the library keys on.
    version_code: int | None
    version_name: str | None
    #: What the *source* needs in order to fetch this exact build — a versionCode
    #: for F-Droid, a version name for APKPure. Opaque to everything else, and the
    #: handle the import route uses so it never has to care which.
    version_key: str = ""
    download_url: str = ""
    #: Bytes, when stated. Used only to show progress and to sanity-check.
    size: int | None = None
    #: ⚠️ **None means the source publishes no hash**, not that nothing matched.
    #: An import can only be verified against the source when this is set.
    sha256: str | None = None
    #: ABIs the build carries, when the catalogue declares them (F-Droid does).
    #: Empty tuple means "declared, and it carries none" — the universal build —
    #: exactly as `AppPackageVersion.abis` distinguishes it from unknown (W96).
    abis: tuple[str, ...] | None = None
    min_sdk: int | None = None
    #: The signing certificate the catalogue claims. Compared against what is
    #: already in the library *before* downloading, so an obvious substitution is
    #: caught early — but never recorded from here.
    signer_sha256: str | None = None
    source: str = ""
    #: True when this build arrives as a bundle (XAPK/APKS) rather than a lone
    #: APK. `inspect_bundle` handles both; the console says which is coming.
    is_bundle: bool = False

    def __post_init__(self) -> None:
        if not self.version_key:
            # Frozen dataclass: the default is derived once, here, so every source
            # that only knows a versionCode keeps working untouched.
            object.__setattr__(self, "version_key", str(self.version_code or ""))

    @property
    def verifiable(self) -> bool:
        """Can this download be checked against what the source promised?"""
        return bool(self.sha256)

    @property
    def display_version(self) -> str:
        """What to show an operator, given a source may know one or the other."""
        if self.version_name and self.version_code is not None:
            return f"{self.version_name} ({self.version_code})"
        return self.version_name or str(self.version_code or "unknown")


@dataclass(frozen=True)
class Downloaded:
    """A fetched build, and what could be established about it."""

    data: bytes
    #: The digest actually computed over the bytes received.
    sha256: str
    #: Whether that digest was compared against one the source published.
    verified: bool = False
    source_url: str = ""


#: Called during a download with (bytes so far, total or 0 when unknown).
#:
#: ⚠️ **Zero means "not known", never "nothing to download".** Play cannot state
#: a size — its downloads run through `apkeep`, which offers no HTTP response to
#: read a `Content-Length` from — so the console shows bytes rather than
#: inventing a denominator to make a bar move (W127).
Progress = Callable[[int, int], None]


def watch_directory(
    directory: Path, progress: Progress, stop: threading.Event
) -> None:
    """Report the bytes an out-of-process downloader has written so far.

    ⚠️ **The only progress available for an `apkeep` source.** There is no
    stream to count and nothing parseable on its stdout, so the size on disk is
    the measurement. Total stays 0: the files appear one at a time and their
    eventual count is unknown, so any denominator here would be a guess.

    Errors are swallowed deliberately — a download must not fail because a
    progress poll lost a race with a file being renamed.
    """
    while not stop.wait(0.5):
        try:
            written = sum(
                f.stat().st_size for f in directory.rglob("*") if f.is_file()
            )
        except OSError:
            continue
        progress(written, 0)


def collect_output(directory: "Path") -> bytes:
    """Everything a fetch produced, as one artifact the library can ingest (W99).

    ⚠️ **A split app arrives as several files, and keeping only the biggest is a
    silent corruption.** apkeep writes a bundle as its parts::

        com.microsoft.office.outlook.apk                 165.0 MB   base
        com.microsoft.office.outlook.config.arm64_v8a.apk  17.2 MB   native code
        com.microsoft.office.outlook.config.en.apk          2.0 MB
        com.microsoft.office.outlook.config.xxhdpi.apk      1.4 MB

    Taking the largest yields a base with **no native libraries**, which Android
    refuses to install as `INSTALL_FAILED_MISSING_SPLIT` — and which then reports
    `abis = ()`, meaning *"runs anywhere"*. That is worse than the missing files:
    it is a lie in the one field W96 exists to make true, and it would sail
    through the preflight built to catch exactly this.

    So every part is kept, zipped into the container shape `inspect_bundle`
    already understands from XAPK uploads. A single file is returned unchanged.

    Stored rather than deflated: these are APKs, already compressed, and a second
    pass costs minutes to save nothing. Written to disk rather than assembled in
    memory, because a base APK alone can be 222 MB.
    """
    import tempfile
    import zipfile

    files = sorted(
        p for p in directory.rglob("*") if p.is_file() and p.suffix in (".apk", ".xapk")
    )
    if not files:
        raise SourceError("the download produced no APK")
    if len(files) == 1:
        return files[0].read_bytes()

    with tempfile.TemporaryDirectory() as staging:
        bundle = Path(staging) / "bundle.xapk"
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_STORED) as archive:
            for part in files:
                # Basename only: a nested path would still be found, but the flat
                # shape is what an XAPK upload looks like, and one shape is easier
                # to reason about than two.
                archive.write(part, arcname=part.name)
        return bundle.read_bytes()


class SourceError(RuntimeError):
    """A repository could not answer, in words an operator can act on."""


class AppSource(Protocol):
    """A place to look up apps and fetch builds from.

    Kept to three questions on purpose. Anything a particular source can do
    beyond them belongs to that source, not to this interface — the point is that
    the import path and the console never have to know which one they are talking
    to.
    """

    #: Stable identifier, stored as provenance on the imported version.
    name: str
    #: Shown to the operator.
    label: str

    def search(self, query: str, *, limit: int = 25) -> list[SourceApp]: ...

    def versions(self, package_name: str, *, limit: int = 25) -> list[SourceVersion]: ...

    def download(
        self, version: SourceVersion, progress: Progress | None = None
    ) -> Downloaded: ...


_REGISTRY: dict[str, AppSource] = {}


def register(source: AppSource) -> AppSource:
    """Make a source reachable by name."""
    _REGISTRY[source.name] = source
    return source


def get(name: str) -> AppSource | None:
    return _REGISTRY.get(name)


def available() -> list[AppSource]:
    """Every registered source, in the order the console should offer them.

    F-Droid first, deliberately: it is the one whose downloads can be verified
    against what it published, so it is the one an operator should reach for
    unless the app they need is not there.
    """
    order = {"fdroid": 0, "apkpure": 1}
    return sorted(_REGISTRY.values(), key=lambda s: (order.get(s.name, 99), s.name))
