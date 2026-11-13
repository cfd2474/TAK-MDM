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

"""Export a policy's settings as a file another ATLAS can import (W492).

Operator, 2026-11-13: *"could we build an "Export Policy Configs" to the policy
list page as well as on each policy page? the policy list page should allow to
put all policies into a zip file."*

One JSON document per policy. The operator's decisions, asked the same day:

* **Settings only.** No Content file travels with a policy. A file reference
  carries the file's name and sha256 in `files`, so an import can find the same
  file on the other server (the stock animations match everywhere) or say
  which setting lost its file.
* **Passwords included.** First the operator chose to leave them out, but a
  Wi-Fi network, a TAK Server connection and a kiosk exit are not valid
  without theirs, so most policies could not import; the operator then chose
  to include them, with a warning beside each Export button that anyone who
  gets the file can read them.
* **No assignments.** Which devices and groups a policy reaches is this
  server's business; an imported policy reaches nothing until it is assigned.

A standalone policy (the older single-type kind) exports as a one-section
policy, so every document has the same shape.
"""

from __future__ import annotations

import io
import json
import re
import uuid
import zipfile
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ManagedFile, Policy, PolicyProfile
from app.policies import creator_catalog
from app.services import policy_admin
from app.services import profiles as profile_service

FORMAT = "atlas-policy"
FORMAT_VERSION = 1
MEDIA_TYPE = "application/json"


def _file_ids(value: Any) -> list[str]:
    """Every value under a key ending in `file_id`, anywhere in a spec."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, inner in value.items():
            if key.endswith("file_id") and isinstance(inner, str):
                found.append(inner)
            else:
                found.extend(_file_ids(inner))
    elif isinstance(value, list):
        for inner in value:
            found.extend(_file_ids(inner))
    return found


def _files(session: Session, specs: list[dict]) -> dict[str, dict[str, str]]:
    """`{file id: {name, sha256}}` for each Content file the specs name."""
    ids = set()
    for spec in specs:
        for raw in _file_ids(spec):
            try:
                ids.add(uuid.UUID(raw))
            except ValueError:
                continue
    if not ids:
        return {}
    rows = session.scalars(select(ManagedFile).where(ManagedFile.id.in_(ids)))
    return {str(f.id): {"name": f.name, "sha256": f.artifact_sha256} for f in rows}


def _document(session: Session, *, name: str, description: str | None,
              sections: dict[str, tuple[str, dict]], atlas_version: str | None) -> dict[str, Any]:
    """`sections`: category key -> (policy type, stored spec)."""
    exported = {key: spec or {} for key, (_policy_type, spec) in sections.items()}
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "atlas_version": atlas_version,
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "name": name,
        "description": description,
        "sections": exported,
        "files": _files(session, list(exported.values())),
    }


def for_profile(session: Session, profile: PolicyProfile, atlas_version: str | None) -> dict[str, Any]:
    """A policy built in the creator: each section's newest saved settings."""
    sections = {
        s.profile_section: (s.policy_type, s.latest_version.spec)
        for s in profile.sections
        if s.profile_section and s.latest_version is not None
    }
    return _document(session, name=profile.name, description=profile.description,
                     sections=sections, atlas_version=atlas_version)


def for_policy(session: Session, policy: Policy, atlas_version: str | None) -> dict[str, Any] | None:
    """An older single-type policy, as one section. None when its type has no
    category in the creator, because the import could not place it."""
    category = creator_catalog.for_policy_type(policy.policy_type)
    if category is None or policy.latest_version is None:
        return None
    return _document(session, name=policy.name, description=policy.description,
                     sections={category.key: (policy.policy_type, policy.latest_version.spec)},
                     atlas_version=atlas_version)


def to_json(document: dict[str, Any]) -> bytes:
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=False).encode("utf-8")


_UNSAFE = re.compile(r"[^A-Za-z0-9._ -]+")


def filename(name: str) -> str:
    """A file name for a policy: its name with anything risky in a path replaced."""
    stem = _UNSAFE.sub("_", name).strip(" .") or "policy"
    return stem[:100] + ".json"


def every_policy(session: Session, atlas_version: str | None) -> list[dict[str, Any]]:
    """Each live policy on the Device policies tab: no template, nothing archived,
    nothing the system owns (the breach profile)."""
    documents = [for_profile(session, p, atlas_version) for p in profile_service.list_profiles(session)]
    for policy in policy_admin.list_tab(session, "device"):
        document = for_policy(session, policy, atlas_version)
        if document is not None:
            documents.append(document)
    return documents


def zip_of(documents: list[dict[str, Any]]) -> bytes:
    """One .json per policy. Two policies whose names make the same file name
    get "-2", "-3" … so neither is lost."""
    out = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for document in documents:
            name = filename(document["name"])
            stem, n = name[:-5], 2
            while name.lower() in used:
                name, n = f"{stem}-{n}.json", n + 1
            used.add(name.lower())
            archive.writestr(name, to_json(document))
    return out.getvalue()
