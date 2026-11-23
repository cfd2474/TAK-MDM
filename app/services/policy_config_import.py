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

"""Import policy configs exported by `policy_config_export` (W492).

Operator, 2026-11-13: *"Importing should popup an intermediate modal with a
list of all policies with checkboxes next to each one. user selects the check
box for the ones that they want to import. there should be a select all
checkbox at the top."*

Two steps, both stateless: `read` lists what a file holds (nothing written),
then the browser sends the same file again with the chosen indexes and
`import_chosen` creates them.

* **A same name becomes a copy** (operator's choice): "<name> (imported)",
  then "(imported 2)" …, so nothing on this server changes.
* **Content files are matched by sha256.** The export carries no file, only
  its name and sha256; the same file here (the stock animations, a shared
  data package) takes its place, and a reference to a file this server does
  not have is removed and named in the result. A setting that points at an
  uploaded file by sha256 (a TAK certificate, a pinned app build) is kept
  only when this server holds that file.
* **Every policy goes through the creator's own checks**
  (`profiles.create_profile`, with the library, as an operator's save). One
  that fails is reported and the others still import: each runs in a
  savepoint.
* ⚠️ **A zip is read, never extracted**, with limits on members and sizes, so
  nothing in it becomes a path here and a zip bomb stops at the limit.
"""

from __future__ import annotations

import copy
import io
import json
import zipfile
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artifacts.storage import ArtifactStorage
from app.db.models import Artifact, ManagedFile, Policy, PolicyProfile
from app.policies import creator_catalog
from app.services import profiles as profile_service
from app.services.policy_config_export import FORMAT, FORMAT_VERSION

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_MEMBERS = 500
MAX_MEMBER_BYTES = 5 * 1024 * 1024
MAX_TOTAL_BYTES = 100 * 1024 * 1024
SUFFIX = " (imported)"


class PolicyImportError(ValueError):
    """The file as a whole cannot be read; the message says why."""


@dataclass
class Candidate:
    """One policy found in the file."""

    index: int
    source: str  # the file, or the zip member, it came from
    name: str = ""
    description: str | None = None
    categories: list[str] = field(default_factory=list)
    problem: str | None = None  # set when it cannot be imported at all
    document: dict[str, Any] = field(default_factory=dict, repr=False)

    def describe(self) -> dict[str, Any]:
        return {"index": self.index, "source": self.source, "name": self.name,
                "description": self.description, "categories": self.categories,
                "problem": self.problem}


@dataclass
class Result:
    """What happened to one chosen policy."""

    name: str
    imported_as: str | None = None
    profile_id: str | None = None
    error: str | None = None
    notes: list[str] = field(default_factory=list)

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "imported_as": self.imported_as, "profile_id": self.profile_id,
                "error": self.error, "notes": self.notes}


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #


def _documents(filename: str, data: bytes) -> list[tuple[str, bytes]]:
    """(source, bytes) for each .json in the upload."""
    if len(data) > MAX_FILE_BYTES:
        raise PolicyImportError(f"the file is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB")
    if not data.startswith(b"PK"):
        return [(filename or "upload.json", data)]
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise PolicyImportError("this is not a zip file") from None
    members = [i for i in archive.infolist()
               if not i.is_dir() and not i.filename.startswith("__MACOSX/")
               and not i.filename.rsplit("/", 1)[-1].startswith(".")
               and i.filename.lower().endswith(".json")]
    if not members:
        raise PolicyImportError("the zip holds no .json policy files")
    if len(members) > MAX_MEMBERS:
        raise PolicyImportError(f"the zip holds more than {MAX_MEMBERS} policy files")
    if sum(i.file_size for i in members) > MAX_TOTAL_BYTES:
        raise PolicyImportError("the zip's policy files are too large")
    out = []
    for info in members:
        if info.file_size > MAX_MEMBER_BYTES:
            out.append((info.filename, b""))  # reported as a problem below
            continue
        with archive.open(info) as handle:
            out.append((info.filename, handle.read(MAX_MEMBER_BYTES + 1)))
    return out


def _check(candidate: Candidate, raw: bytes) -> None:
    """Fill the candidate from its JSON, or set its problem."""
    if not raw or len(raw) > MAX_MEMBER_BYTES:
        candidate.problem = "empty, or larger than 5 MB"
        return
    try:
        document = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        candidate.problem = "not a policy config file (not JSON)"
        return
    if not isinstance(document, dict) or document.get("format") != FORMAT:
        candidate.problem = "not an ATLAS policy config file"
        return
    version = document.get("format_version")
    if not isinstance(version, int) or version > FORMAT_VERSION:
        candidate.problem = "made by a newer ATLAS: update this server first"
        return
    name, sections = document.get("name"), document.get("sections")
    if not isinstance(name, str) or not name.strip() or not isinstance(sections, dict):
        candidate.problem = "the file has no policy name or no settings"
        return
    candidate.name = name.strip()
    description = document.get("description")
    candidate.description = description if isinstance(description, str) else None
    candidate.categories = [
        (creator_catalog.get(key).label if creator_catalog.get(key) else key) for key in sections
    ]
    candidate.document = document


def read(filename: str, data: bytes) -> list[Candidate]:
    """Every policy in a .json or a .zip, in file order. Writes nothing."""
    candidates = []
    for index, (source, raw) in enumerate(_documents(filename, data)):
        candidate = Candidate(index=index, source=source)
        _check(candidate, raw)
        candidates.append(candidate)
    return candidates


# --------------------------------------------------------------------------- #
# Importing
# --------------------------------------------------------------------------- #


def _taken(session: Session, name: str, categories: list[creator_catalog.Category]) -> bool:
    """Would a policy of this name, or one of its sections, reuse a name here?"""
    names = [name] + [profile_service._child_name(name, c) for c in categories]
    return bool(
        session.scalar(select(PolicyProfile.id).where(PolicyProfile.name == name).limit(1))
        or session.scalar(select(Policy.id).where(Policy.name.in_(names)).limit(1))
        or name in profile_service.RESERVED_NAMES
    )


def free_name(session: Session, name: str, categories: list[creator_catalog.Category]) -> str:
    """`name`, or "name (imported)", "name (imported 2)" … the first that is free."""
    if not _taken(session, name, categories):
        return name
    n = 1
    while True:
        suffix = SUFFIX if n == 1 else f" (imported {n})"
        candidate = name[: profile_service.NAME_MAX - len(suffix) - 30] + suffix
        if not _taken(session, candidate, categories):
            return candidate
        n += 1


def _sha_fields(key: str) -> bool:
    return key.endswith("_sha256")


def _relink(session: Session, value: Any, files: dict, label: str, notes: list[str]) -> Any:
    """`value` with each Content file reference pointed at this server's copy
    (same sha256), and each one this server cannot satisfy removed."""
    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, dict) and "file_id" in item and _local_file(session, item["file_id"], files) is None:
                notes.append(f"{label}: {_file_label(item['file_id'], files)} is not on this server, so it was left out")
                continue
            out.append(_relink(session, item, files, label, notes))
        return out
    if not isinstance(value, dict):
        return value
    out = {}
    for key, inner in value.items():
        if key.endswith("file_id") and isinstance(inner, str):
            local = _local_file(session, inner, files)
            if local is None:
                notes.append(f"{label}: {_file_label(inner, files)} is not on this server, so {key} was cleared")
                continue
            out[key] = local
        elif _sha_fields(key) and isinstance(inner, str):
            if session.get(Artifact, inner) is None:
                notes.append(f"{label}: an uploaded file ({key}) is not on this server, so it was cleared")
                continue
            out[key] = inner
        else:
            out[key] = _relink(session, inner, files, label, notes)
    return out


def _file_label(file_id: str, files: dict) -> str:
    known = files.get(file_id) if isinstance(files, dict) else None
    name = known.get("name") if isinstance(known, dict) else None
    return f"the file {name!r}" if name else "a Content file"


def _local_file(session: Session, file_id: str, files: dict) -> str | None:
    """This server's id for the exported file, matched by sha256."""
    known = files.get(file_id) if isinstance(files, dict) else None
    sha = known.get("sha256") if isinstance(known, dict) else None
    if not isinstance(sha, str):
        return None
    match = session.scalars(
        select(ManagedFile.id).where(ManagedFile.artifact_sha256 == sha)
        .order_by(ManagedFile.in_library.desc(), ManagedFile.created_at)
        .limit(1)
    ).first()
    return str(match) if match else None


def _import_one(session: Session, storage: ArtifactStorage, document: dict, created_by: str | None) -> Result:
    result = Result(name=document["name"].strip())
    files = document.get("files") or {}
    sections: dict[str, dict] = {}
    categories = []
    for key, spec in document["sections"].items():
        category = creator_catalog.get(key)
        if category is None or not category.wired or category.key == "breach":
            result.notes.append(f"{key}: not a category this ATLAS has, so it was left out")
            continue
        if not isinstance(spec, dict):
            continue
        sections[key] = _relink(session, copy.deepcopy(spec), files, category.label, result.notes)
        categories.append(category)
    name = free_name(session, result.name, categories)
    description = document.get("description") if isinstance(document.get("description"), str) else None
    savepoint = session.begin_nested()
    try:
        profile = profile_service.create_profile(
            session, name=name, description=description, sections=sections,
            created_by=created_by, storage=storage)
        savepoint.commit()
    except profile_service.ProfileError as exc:
        savepoint.rollback()
        result.error = str(exc)
        return result
    result.imported_as, result.profile_id = profile.name, str(profile.id)
    return result


def import_chosen(session: Session, storage: ArtifactStorage, filename: str, data: bytes,
                  chosen: list[int], created_by: str | None) -> list[Result]:
    """Import the policies at the chosen indexes. The caller commits."""
    wanted = set(chosen)
    results = []
    for candidate in read(filename, data):
        if candidate.index not in wanted:
            continue
        if candidate.problem:
            results.append(Result(name=candidate.name or candidate.source, error=candidate.problem))
            continue
        results.append(_import_one(session, storage, candidate.document, created_by))
    return results
