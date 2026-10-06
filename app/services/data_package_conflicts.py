"""Duplicate data packages: refuse the identical, ask about a new version (W344).

Copyright 2026 TAK-Solutions LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

Operator: *"confirm that it can detect and rejects duplicates, or offers option to
overwrite."* It did neither: the same zip uploaded twice became two library
entries. Now, per the operator's answers:

* **Identical contents** (same digest as a library package): refused. A second
  entry for the same bytes buys nothing.
* **The same package with different contents** (same library name, or the same
  manifest UID): the operator chooses.
  * **Replace** keeps the library entry -- and every policy that names it -- and
    swaps its contents. A device remembers a delivered package by its content
    hash (`persist: false`), so each device on such a policy receives the new
    version **once**, on its next check-in.
  * **Keep both** adds it under the next free name, "Name (1)", "Name (2)", …
    (*"keep will append name change with a +1 index"*).
  * **Skip** adds nothing.

⚠️ **The upload is staged while the operator decides**, so the choice costs no
second upload: a 157 MB package over a satellite link is minutes, not a click.
Staged files live under `cache_dir` -- somewhere losing them costs only a
re-upload -- never under `artifact_dir`, which is digest-addressed and swept.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artifacts import mission_package
from app.artifacts.storage import ArtifactStorage
from app.db.models import Artifact, ManagedFile, Policy
from app.services import data_packages as data_package_service
from app.services import files as file_service

#: How long a staged upload waits for the operator's choice.
STAGE_TTL_SECONDS = 3600

_TOKEN = re.compile(r"^[0-9a-f]{32}$")

IDENTICAL = "identical"
SAME_NAME = "same_name"
SAME_UID = "same_uid"


class StagedUploadGone(LookupError):
    """The staged upload expired or never existed."""


@dataclass(frozen=True)
class Conflict:
    kind: str
    existing: ManagedFile
    #: For "keep both": the name the new package would be saved under.
    suggested_name: str
    #: Current policies naming the existing package.
    used_by: int


def library_name(name: str, package: mission_package.DataPackage) -> str:
    """The name an upload is catalogued under: typed, else the manifest's."""
    return (name or "").strip() or package.name


def find(
    session: Session,
    storage: ArtifactStorage,
    *,
    digest: str,
    name: str,
    package: mission_package.DataPackage,
) -> Conflict | None:
    """The library package this upload collides with, if any. Identical first."""
    packages = list(session.scalars(
        select(ManagedFile).where(ManagedFile.is_data_package.is_(True))
        .order_by(ManagedFile.created_at)
    ))
    for existing in packages:
        if existing.artifact_sha256 == digest:
            return Conflict(IDENTICAL, existing, "", _used_by(session, existing))
    folded = name.casefold()
    for existing in packages:
        if existing.name.casefold() == folded:
            return Conflict(SAME_NAME, existing, next_free_name(session, name), _used_by(session, existing))
    for existing in packages:
        if package.uid and _uid_of(session, storage, existing) == package.uid:
            return Conflict(SAME_UID, existing, next_free_name(session, name), _used_by(session, existing))
    return None


def _uid_of(session: Session, storage: ArtifactStorage, managed: ManagedFile) -> str | None:
    """The package's manifest UID, read once and kept on the row."""
    if managed.package_uid:
        return managed.package_uid
    manifest = data_package_service.manifest_of(storage, managed)
    if manifest is None:
        return None
    managed.package_uid = manifest.uid
    session.flush()
    return manifest.uid


def next_free_name(session: Session, name: str) -> str:
    """"Name (1)", "Name (2)", …: the lowest index no library file is using."""
    taken = {
        n.casefold() for n in session.scalars(
            select(ManagedFile.name).where(ManagedFile.is_data_package.is_(True)))
    }
    index = 1
    while f"{name} ({index})".casefold() in taken:
        index += 1
    return f"{name} ({index})"


def _used_by(session: Session, managed: ManagedFile) -> int:
    """How many current policies name this package."""
    wanted = str(managed.id)
    count = 0
    for policy in session.scalars(
        select(Policy).where(Policy.archived_at.is_(None), Policy.is_template.is_(False))
    ):
        latest = policy.latest_version
        spec = (latest.spec if latest else None) or {}
        if any(str(e.get("file_id")) == wanted for e in spec.get("data_packages") or []):
            count += 1
    return count


def replace(
    session: Session,
    storage: ArtifactStorage,
    existing: ManagedFile,
    data: bytes,
    *,
    original_filename: str,
) -> ManagedFile:
    """Swap the package's contents, keeping its id, name and policies.

    The old blob is released if nothing else references it, by the same rules
    as a delete.
    """
    package = mission_package.inspect(data)
    old_digest = existing.artifact_sha256
    digest, size = storage.put(io.BytesIO(data))
    if session.get(Artifact, digest) is None:
        session.add(Artifact(sha256=digest, size_bytes=size, media_type="application/zip"))
        session.flush()
    existing.artifact_sha256 = digest
    existing.original_filename = original_filename
    existing.package_uid = package.uid
    session.flush()
    file_service.release_artifact(session, storage, old_digest)
    return existing


# --------------------------------------------------------------------------- #
# Staging
# --------------------------------------------------------------------------- #


def _stage_dir(cache_dir: Path) -> Path:
    path = Path(cache_dir) / "upload-staging"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _sweep(directory: Path) -> None:
    cutoff = time.time() - STAGE_TTL_SECONDS
    for item in directory.iterdir():
        try:
            if item.stat().st_mtime < cutoff:
                item.unlink()
        except OSError:
            pass


def stage(cache_dir: Path, data: bytes, *, name: str, original_filename: str) -> str:
    """Hold an upload for the operator's decision; return its token."""
    directory = _stage_dir(cache_dir)
    _sweep(directory)
    token = secrets.token_hex(16)
    (directory / f"{token}.zip").write_bytes(data)
    (directory / f"{token}.json").write_text(
        json.dumps({"name": name, "original_filename": original_filename}), encoding="utf-8")
    return token


def take(cache_dir: Path, token: str) -> tuple[bytes, dict]:
    """The staged upload and what was typed with it. It is removed as taken."""
    if not _TOKEN.match(token or ""):
        raise StagedUploadGone("that upload is not waiting for a decision")
    directory = _stage_dir(cache_dir)
    _sweep(directory)
    data_path, meta_path = directory / f"{token}.zip", directory / f"{token}.json"
    try:
        data = data_path.read_bytes()
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StagedUploadGone(
            "that upload is no longer waiting (it is kept for an hour); upload it again"
        ) from exc
    discard(cache_dir, token)
    return data, meta


def discard(cache_dir: Path, token: str) -> None:
    if not _TOKEN.match(token or ""):
        return
    directory = _stage_dir(cache_dir)
    for suffix in (".zip", ".json"):
        try:
            (directory / f"{token}{suffix}").unlink()
        except OSError:
            pass


def describe(conflict: Conflict, new_name: str) -> str:
    """The question, in a sentence."""
    if conflict.kind == SAME_UID:
        return (f"“{new_name}” is the same data package (same manifest UID) as "
                f"“{conflict.existing.name}” in the library, with different contents.")
    return f"A data package named “{conflict.existing.name}” is already in the library."


def classify(
    session: Session, storage: ArtifactStorage, data: bytes, *, name: str
) -> tuple[mission_package.DataPackage, str, Conflict | None]:
    """Validate an upload and find what it collides with.

    Returns the parsed package, the name it would be catalogued under, and the
    conflict (or None). Raises `DataPackageError` for a zip that is not one.
    """
    package = mission_package.inspect(data)
    wanted = library_name(name, package)
    digest = hashlib.sha256(data).hexdigest()
    return package, wanted, find(session, storage, digest=digest, name=wanted, package=package)


def conflict_json(conflict: Conflict, wanted: str, token: str) -> dict:
    """What the page needs to ask the question."""
    return {
        "conflict": {
            "kind": conflict.kind,
            "existing": {"id": str(conflict.existing.id), "name": conflict.existing.name},
            "suggested_name": conflict.suggested_name,
            "used_by": conflict.used_by,
            "question": describe(conflict, wanted),
        },
        "token": token,
    }


def identical_message(conflict: Conflict) -> str:
    return f"this exact file is already in the library as “{conflict.existing.name}”"
