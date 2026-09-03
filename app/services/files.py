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
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artifacts.storage import ArtifactStorage
from app.db.models import Artifact, Device, DeviceFileSelection, ManagedFile


class FileError(ValueError):
    """Raised when a file upload or reference cannot be accepted."""


def is_archive(data: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)):
            return True
    except zipfile.BadZipFile:
        return False


def ingest_file(
    session: Session,
    storage: ArtifactStorage,
    data: bytes,
    *,
    name: str,
    original_filename: str,
    description: str | None = None,
    media_type: str = "application/octet-stream",
) -> ManagedFile:
    if not data:
        raise FileError("uploaded file is empty")

    digest, size = storage.put(io.BytesIO(data))
    if session.get(Artifact, digest) is None:
        session.add(Artifact(sha256=digest, size_bytes=size, media_type=media_type))
        session.flush()

    managed = ManagedFile(
        name=name,
        description=description,
        original_filename=original_filename,
        media_type=media_type,
        is_archive=is_archive(data),
        artifact_sha256=digest,
    )
    session.add(managed)
    session.flush()
    return managed


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


def resolve_files(session: Session, values: Mapping[str, Any]) -> dict[str, Any]:
    """Turn ``FILES.entries`` into concrete, downloadable instructions.

    Required and optional entries are returned separately: the agent installs the
    first unconditionally and offers the second in its marketplace (F4). Splitting
    them here keeps that distinction out of the agent's parsing logic.
    """
    spec = values.get("FILES") or {}
    entries = spec.get("entries") or []
    if not entries:
        return {"required": [], "available": []}

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
            required.append({"file_id": str(file_id), "available": False})
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
