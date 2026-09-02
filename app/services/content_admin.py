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

"""The Content section: managed files and where every FILES policy places them.

A managed file carries no destination of its own — that lives on the `FileEntry`
of whichever FILES policy places it. This module reads those entries back so the
Content page can show, per file, every deployment it is part of.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ManagedFile, Policy


@dataclass(frozen=True)
class FileReference:
    policy_id: uuid.UUID
    policy_name: str
    is_profile_section: bool
    dest_path: str
    availability: str
    persist: object  # bool | None
    extract: bool
    extract_to: str | None
    overwrite: str


@dataclass
class ContentRow:
    file: ManagedFile
    size_bytes: int
    references: list[FileReference] = field(default_factory=list)


def _files_policies(session: Session) -> list[Policy]:
    return list(
        session.scalars(
            select(Policy).where(
                Policy.policy_type == "FILES", Policy.archived_at.is_(None)
            )
        )
    )


def _references_by_file(session: Session) -> dict[uuid.UUID, list[FileReference]]:
    out: dict[uuid.UUID, list[FileReference]] = {}
    for policy in _files_policies(session):
        version = policy.latest_version
        if version is None:
            continue
        for entry in version.spec.get("entries") or []:
            try:
                fid = uuid.UUID(str(entry["file_id"]))
            except (KeyError, ValueError):
                continue
            out.setdefault(fid, []).append(
                FileReference(
                    policy_id=policy.id,
                    policy_name=policy.name,
                    is_profile_section=policy.profile_id is not None,
                    dest_path=entry.get("dest_path", "—"),
                    availability=entry.get("availability", "required"),
                    persist=entry.get("persist"),
                    extract=bool(entry.get("extract")),
                    extract_to=entry.get("extract_to"),
                    overwrite=entry.get("overwrite", "if_newer"),
                )
            )
    return out


def content_rows(session: Session) -> list[ContentRow]:
    refs = _references_by_file(session)
    rows: list[ContentRow] = []
    for managed in session.scalars(select(ManagedFile).order_by(ManagedFile.name)):
        size = managed.artifact.size_bytes if managed.artifact else 0
        rows.append(ContentRow(file=managed, size_bytes=size, references=refs.get(managed.id, [])))
    return rows


def references(session: Session, file_id: uuid.UUID) -> list[FileReference]:
    return _references_by_file(session).get(file_id, [])
