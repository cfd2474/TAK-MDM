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

"""Data packages as library content (W91).

A data package is an ordinary :class:`ManagedFile` — same artifact store, same
dedupe, same reference counting, same delete. All this module adds is the one
thing the rest of the system needs to know: **that it is one**, checked against
ATAK's rules at upload rather than discovered on a tablet.

Two ways in, one result:

* **Upload** — an operator already has a package, and it is validated as-is.
* **Create** — an operator has loose files, and `mission_package.build` makes a
  package from them.

⚠️ **Both go through the same validator.** What Create produces is exactly what
an operator could have uploaded, which is what keeps the two paths from drifting
into "works when built here, refused when uploaded".
"""

from __future__ import annotations

import re
from collections import OrderedDict

from sqlalchemy.orm import Session

from app.artifacts import mission_package
from app.artifacts.storage import ArtifactStorage
from app.db.models import ManagedFile
from app.services import files as file_service

#: Manifests already read, keyed by the artifact's content hash.
#:
#: The result, never the bytes — the same rule the APK scans follow. A build is
#: immutable at its hash so this cannot go stale, and the Content page would
#: otherwise re-open every package zip on every render.
_MANIFESTS: OrderedDict[str, mission_package.DataPackage] = OrderedDict()
_MANIFEST_LIMIT = 64


def ingest_upload(
    session: Session,
    storage: ArtifactStorage,
    data: bytes,
    *,
    name: str,
    original_filename: str,
    description: str | None = None,
) -> ManagedFile:
    """Catalogue an uploaded zip, refusing anything ATAK would not import.

    Raises `mission_package.DataPackageError` with the validator's own words —
    the operator is standing right here, which is the entire reason this check
    is at upload and not at delivery.
    """
    package = mission_package.inspect(data)

    managed = file_service.ingest_file(
        session,
        storage,
        data,
        # The manifest's own name is the better default: it is what ATAK will
        # call the package, so an operator seeing something else in the console
        # is looking at two names for one thing.
        name=(name or "").strip() or package.name,
        original_filename=original_filename,
        description=description,
        media_type="application/zip",
    )
    managed.is_data_package = True
    session.flush()
    _MANIFESTS[managed.artifact_sha256] = package
    _trim()
    return managed


def create(
    session: Session,
    storage: ArtifactStorage,
    *,
    name: str,
    files: list[tuple[str, bytes]],
    description: str | None = None,
) -> ManagedFile:
    """Build a package from loose files and catalogue it."""
    built = mission_package.build(name, files)
    return ingest_upload(
        session,
        storage,
        built,
        name=name,
        original_filename=f"{_slug(name)}.zip",
        description=description,
    )


def manifest_of(
    storage: ArtifactStorage, managed: ManagedFile
) -> mission_package.DataPackage | None:
    """What this package declares, or None if it cannot be read.

    Never raises: this feeds a listing, and one unreadable blob must not take the
    Content page down with it.
    """
    if not managed.is_data_package:
        return None
    cached = _MANIFESTS.get(managed.artifact_sha256)
    if cached is not None:
        _MANIFESTS.move_to_end(managed.artifact_sha256)
        return cached
    try:
        with storage.open(managed.artifact_sha256) as handle:
            package = mission_package.inspect(handle.read())
    except (FileNotFoundError, OSError, mission_package.DataPackageError):
        return None
    _MANIFESTS[managed.artifact_sha256] = package
    _trim()
    return package


def _trim() -> None:
    while len(_MANIFESTS) > _MANIFEST_LIMIT:
        _MANIFESTS.popitem(last=False)


def _slug(name: str) -> str:
    """A filename for the built zip, derived from the operator's package name.

    Runs of separators collapse: "ATLAS test overlay (W91)" would otherwise land
    on the device as `atlas-test-overlay--w91.zip`, because " (" is two
    characters and each became its own hyphen. Cosmetic, but it is the name an
    operator reads in ATAK's own directory.
    """
    cleaned = "".join(c if c.isalnum() or c in "-_" else "-" for c in name.strip())
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return cleaned.strip("-").lower() or "data-package"
