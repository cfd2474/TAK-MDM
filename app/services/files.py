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

"""Managed file ingestion and resolution.

Files here are opaque payloads — a zip of ATAK data packages, a `.pref`, a cert.
Unlike APKs there is nothing to validate structurally, so the only inspection is
detecting whether a payload is an archive, which the policy layer needs in order to
refuse an extraction directive on something that cannot be extracted.
"""

from __future__ import annotations

import io
import uuid
import zipfile
from collections.abc import Mapping, Sequence
from typing import Any, BinaryIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artifacts.storage import ArtifactStorage
from app.artifacts import dted
from app.db.models import Artifact, Device, DeviceFileSelection, ManagedFile


class FileError(ValueError):
    """Raised when a file upload or reference cannot be accepted."""


def is_archive(data: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)):
            return True
    except zipfile.BadZipFile:
        return False


def _is_archive_stream(source: BinaryIO) -> bool:
    """`is_archive` for something too big to hold in memory.

    `ZipFile` leaves a file object it was handed open, so the stream survives to
    be stored afterwards — it is rewound either way.
    """
    try:
        source.seek(0)
        with zipfile.ZipFile(source):
            return True
    except (zipfile.BadZipFile, OSError):
        return False
    finally:
        source.seek(0)


def ingest_stream(
    session: Session,
    storage: ArtifactStorage,
    source: BinaryIO,
    *,
    name: str,
    original_filename: str,
    description: str | None = None,
    media_type: str = "application/octet-stream",
    in_library: bool = True,
) -> ManagedFile:
    """Store a seekable stream and catalogue it.

    ⚠️ **The stream form exists for size.** W94 repacks a nested DTED archive
    before storing it, and the operator's sample inflates to 1.75 GB; handing that
    back as `bytes` would hold the whole thing in memory a second time for no
    reason. `storage.put` already streams, so this only keeps it that way.
    """
    archive = _is_archive_stream(source)
    digest, size = storage.put(source)
    if size == 0:
        raise FileError("uploaded file is empty")

    if session.get(Artifact, digest) is None:
        session.add(Artifact(sha256=digest, size_bytes=size, media_type=media_type))
        session.flush()

    managed = ManagedFile(
        name=name,
        description=description,
        original_filename=original_filename,
        media_type=media_type,
        is_archive=archive,
        artifact_sha256=digest,
        in_library=in_library,
    )
    session.add(managed)
    session.flush()
    return managed


def ingest_file(
    session: Session,
    storage: ArtifactStorage,
    data: bytes,
    *,
    name: str,
    original_filename: str,
    description: str | None = None,
    media_type: str = "application/octet-stream",
    in_library: bool = True,
) -> ManagedFile:
    """Store bytes and catalogue them.

    ``in_library`` false marks a file uploaded from inside a policy editor (W46):
    identical in every way the device cares about, but kept out of the Content
    listings so a wallpaper does not turn up as deployable content.
    """
    if not data:
        raise FileError("uploaded file is empty")

    return ingest_stream(
        session,
        storage,
        io.BytesIO(data),
        name=name,
        original_filename=original_filename,
        description=description,
        media_type=media_type,
        in_library=in_library,
    )


def delete_file(session: Session, storage: ArtifactStorage, managed: ManagedFile) -> None:
    """Delete a catalog entry, reclaiming its blob if nothing else references it."""
    digest = managed.artifact_sha256
    session.delete(managed)
    session.flush()

    still_referenced = session.scalar(
        select(ManagedFile).where(ManagedFile.artifact_sha256 == digest).limit(1)
    )
    if still_referenced is not None:
        return

    from app.db.models import AppPackageFile

    used_by_package = session.scalar(
        select(AppPackageFile).where(AppPackageFile.artifact_sha256 == digest).limit(1)
    )
    if used_by_package is not None:
        return

    artifact = session.get(Artifact, digest)
    if artifact is not None:
        session.delete(artifact)
    storage.delete(digest)
    session.flush()


#: Where ATLAS drops a data package for ATAK to import (W91).
#:
#: ✅ **`incoming/`, chosen on hardware evidence over the source.** Both
#: directories were tested on `SM-X520` with a package each: the watched parent
#: imported, and `incoming/` imported too — which the source says it should not,
#: since `MissionPackageFileIO` marks it `// no watch` and the parent's watcher
#: is provably non-recursive (it ignores directory events outright).
#:
#: ⚠️ **The mechanism that imports from `incoming/` is unidentified.** Nothing in
#: `com/atakmap` references this directory except the network-transfer path. It
#: works; *why* it works is not established, which makes it version-fragile in a
#: way the watched directory is not. Recorded as R17.
#:
#: The reason to prefer it anyway is `DirectoryCleanup`: it sweeps `incoming/`
#: after two hours, so delivered packages do not accumulate in ATAK's directory
#: forever — which is exactly what the watched parent, with its explicit
#: `no auto-cleanup`, does.
DATA_PACKAGE_DEST = "/sdcard/atak/tools/datapackage/incoming"


def resolve_files(session: Session, values: Mapping[str, Any]) -> dict[str, Any]:
    """Turn ``FILES.entries`` into concrete, downloadable instructions.

    Required and optional entries are returned separately: the agent installs the
    first unconditionally and offers the second in its marketplace (F4). Splitting
    them here keeps that distinction out of the agent's parsing logic.
    """
    spec = values.get("FILES") or {}
    entries = list(spec.get("entries") or [])
    packages = list(spec.get("data_packages") or [])
    terrain = list(spec.get("dted_archives") or [])
    if not entries and not packages and not terrain:
        return {"required": [], "available": []}

    # ⚠️ A data package is an ordinary file entry with the settings that make it
    # one, decided here rather than offered to the operator (W91). The device
    # needs no new contract: `persist: false` already means "placed once,
    # remembered by content hash, never re-pushed even when gone", which is
    # exactly right for a zip ATAK consumes — hardware-proven 2026-09-01.
    #
    # `data_package` rides along so the agent can render the card honestly; the
    # delivery decision is `persist`, and nothing reads this flag to make it.
    entries = entries + [
        {
            "file_id": package.get("file_id"),
            "title": package.get("title"),
            "dest_path": DATA_PACKAGE_DEST,
            "persist": False,
            "overwrite": "always",
            "extract": False,
            "availability": "required",
            "data_package": True,
        }
        for package in packages
    ]

    # ⚠️ `persist: True`, unlike a data package. ATAK reads terrain off the disk
    # for as long as it is there, and nothing re-imports it — so a cell the user
    # deleted should come back, and there is no repeated-import loop to avoid.
    # The two ATAK file types look alike and behave oppositely here.
    entries = entries + [
        {
            "file_id": archive.get("file_id"),
            "title": archive.get("title"),
            "dest_path": dted.DTED_DEST,
            "extract": True,
            "extract_to": dted.DTED_DEST,
            "persist": True,
            "overwrite": "if_newer",
            "availability": "required",
            "dted": True,
        }
        for archive in (spec.get("dted_archives") or [])
    ]

    file_ids = []
    for entry in entries:
        try:
            file_ids.append(uuid.UUID(str(entry.get("file_id"))))
        except (ValueError, TypeError):
            continue

    catalog = {
        managed.id: managed
        for managed in session.scalars(
            select(ManagedFile).where(ManagedFile.id.in_(file_ids))
        )
    }

    required: list[dict[str, Any]] = []
    available: list[dict[str, Any]] = []

    for entry in entries:
        try:
            file_id = uuid.UUID(str(entry.get("file_id")))
        except (ValueError, TypeError):
            continue

        managed = catalog.get(file_id)
        if managed is None:
            # Referenced but deleted from the catalog. Reported rather than dropped,
            # so a broken policy is visible instead of silently doing nothing.
            required.append({
                "file_id": str(file_id),
                "available": False,
                "data_package": bool(entry.get("data_package")),
            })
            continue

        resolved = {
            "file_id": str(file_id),
            "available": True,
            "name": managed.name,
            "title": entry.get("title") or managed.name,
            "description": entry.get("description") or managed.description,
            "file_name": managed.original_filename,
            "dest_path": entry.get("dest_path"),
            "overwrite": entry.get("overwrite", "if_newer"),
            "extract": bool(entry.get("extract")),
            # Falls back to dest_path for specs stored before the default was
            # recorded explicitly, so an older policy still extracts somewhere sane.
            "extract_to": (
                entry.get("extract_to") or entry.get("dest_path")
                if entry.get("extract")
                else entry.get("extract_to")
            ),
            # Falls back to the tier for specs stored before persist existed, so an
            # older policy behaves the way its author would have expected.
            "persist": (
                entry["persist"]
                if entry.get("persist") is not None
                else entry.get("availability", "required") != "optional"
            ),
            "data_package": bool(entry.get("data_package")),
            "dted": bool(entry.get("dted")),
            "sha256": managed.artifact_sha256,
            "size_bytes": managed.artifact.size_bytes if managed.artifact else None,
            "url": f"/api/v1/device/artifacts/{managed.artifact_sha256}",
        }

        if entry.get("availability", "required") == "optional":
            available.append(resolved)
        else:
            required.append(resolved)

    key = lambda item: (item.get("name") or "", item["file_id"])  # noqa: E731
    return {"required": sorted(required, key=key), "available": sorted(available, key=key)}


def record_selections(
    session: Session, device: Device, file_ids: Sequence[uuid.UUID]
) -> int:
    """Replace a device's recorded optional selections with what it just reported.

    The device's report is authoritative: it states what it currently has applied,
    so this is a set replacement rather than an append. A user who removed an item
    must not leave a stale record claiming it is installed.
    """
    reported = set(file_ids)

    existing = {
        selection.file_id: selection
        for selection in session.scalars(
            select(DeviceFileSelection).where(DeviceFileSelection.device_id == device.id)
        )
    }

    for file_id, selection in existing.items():
        if file_id not in reported:
            session.delete(selection)

    known = {
        managed.id
        for managed in session.scalars(
            select(ManagedFile).where(ManagedFile.id.in_(reported))
        )
    }
    for file_id in reported - set(existing):
        if file_id in known:  # ignore reports for files that no longer exist
            session.add(DeviceFileSelection(device_id=device.id, file_id=file_id))

    session.flush()
    return len(reported & known)


def list_selections(session: Session, device_id: uuid.UUID) -> list[DeviceFileSelection]:
    return list(
        session.scalars(
            select(DeviceFileSelection).where(DeviceFileSelection.device_id == device_id)
        )
    )


def resolve_wallpaper(session: Session, values: Mapping[str, Any]) -> dict[str, Any]:
    """Turn ``WALLPAPER``'s file ids into downloadable references.

    Both slots travel when both are filled: **the device chooses** (D46). It knows
    its own `smallestScreenWidthDp`, the server does not, and sending both costs two
    sha256 strings rather than two images — the agent fetches only the one it uses.

    A slot referencing a file that has been deleted is reported with
    ``available: false`` rather than dropped, for the same reason as `resolve_files`:
    a broken policy has to look broken, not empty.
    """
    spec = values.get("WALLPAPER") or {}
    slots = {
        form_factor: spec.get(f"{form_factor}_file_id")
        for form_factor in ("tablet", "phone")
    }
    wanted: dict[str, uuid.UUID] = {}
    for form_factor, raw in slots.items():
        if raw is None:
            continue
        try:
            wanted[form_factor] = uuid.UUID(str(raw))
        except (ValueError, TypeError):
            continue

    if not wanted:
        return {}

    catalog = {
        managed.id: managed
        for managed in session.scalars(
            select(ManagedFile).where(ManagedFile.id.in_(wanted.values()))
        )
    }

    resolved: dict[str, Any] = {}
    for form_factor, file_id in wanted.items():
        managed = catalog.get(file_id)
        if managed is None:
            resolved[form_factor] = {"file_id": str(file_id), "available": False}
            continue
        resolved[form_factor] = {
            "file_id": str(file_id),
            "available": True,
            "name": managed.name,
            "media_type": managed.media_type,
            "sha256": managed.artifact_sha256,
            "size_bytes": managed.artifact.size_bytes if managed.artifact else None,
            "url": f"/api/v1/device/artifacts/{managed.artifact_sha256}",
        }

    for key in ("lock_screen", "prevent_user_change"):
        if spec.get(key) is not None:
            resolved[key] = bool(spec[key])
    return resolved


def resolve_certificates(session: Session, values: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Turn ``CERTIFICATES``' file ids into downloadable references (W112).

    Same shape as :func:`resolve_wallpaper` on purpose: the agent already knows
    how to fetch `/api/v1/device/artifacts/<sha256>`, and the artifact store is
    content-addressed.

    ⚠️ **That addressing is what makes trusting the bytes reasonable.** The
    desired-state bundle is signed, the bundle carries the sha256, and the store
    is keyed by it — so a certificate cannot be swapped in transit without
    breaking either the signature or the hash. A trust anchor delivered any less
    carefully would be a way to make a device trust an attacker's CA.

    A file that has been deleted travels as ``available: false`` rather than
    being dropped, for the reason `resolve_files` gives: a broken policy has to
    look broken, not empty.
    """
    spec = values.get("CERTIFICATES") or {}
    raw_ids = spec.get("trusted_ca_file_ids") or []

    wanted: list[uuid.UUID] = []
    for raw in raw_ids:
        try:
            file_id = uuid.UUID(str(raw))
        except (ValueError, TypeError):
            continue
        if file_id not in wanted:
            wanted.append(file_id)

    if not wanted:
        return []

    catalog = {
        managed.id: managed
        for managed in session.scalars(
            select(ManagedFile).where(ManagedFile.id.in_(wanted))
        )
    }

    resolved: list[dict[str, Any]] = []
    for file_id in wanted:
        managed = catalog.get(file_id)
        if managed is None:
            resolved.append({"file_id": str(file_id), "available": False})
            continue
        resolved.append(
            {
                "file_id": str(file_id),
                "available": True,
                "name": managed.name,
                "sha256": managed.artifact_sha256,
                "size_bytes": managed.artifact.size_bytes if managed.artifact else None,
                "url": f"/api/v1/device/artifacts/{managed.artifact_sha256}",
            }
        )
    return resolved
