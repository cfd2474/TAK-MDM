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

"""App groups — a named set of packages a policy can reference as a unit."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AppGroup, AppPackage


class AppGroupError(Exception):
    """An app-group operation cannot be completed."""


def list_groups(session: Session) -> list[AppGroup]:
    return list(session.scalars(select(AppGroup).order_by(AppGroup.name)))


def get(session: Session, group_id: uuid.UUID) -> AppGroup | None:
    return session.get(AppGroup, group_id)


def create(session: Session, *, name: str, description: str | None = None) -> AppGroup:
    name = name.strip()
    if not name:
        raise AppGroupError("an app group needs a name")
    group = AppGroup(name=name, description=(description or None))
    session.add(group)
    session.flush()
    return group


def set_members(
    session: Session, group: AppGroup, package_ids: list[uuid.UUID]
) -> AppGroup:
    """Replace the group's package set, preserving the order given."""
    found = {
        p.id: p
        for p in session.scalars(select(AppPackage).where(AppPackage.id.in_(package_ids)))
    }
    missing = [pid for pid in package_ids if pid not in found]
    if missing:
        raise AppGroupError(
            f"unknown package ids: {', '.join(str(m) for m in missing)}"
        )
    # De-dupe while keeping first-seen order.
    ordered: list[AppPackage] = []
    seen: set[uuid.UUID] = set()
    for pid in package_ids:
        if pid not in seen:
            ordered.append(found[pid])
            seen.add(pid)
    group.packages = ordered
    session.flush()
    return group


def rename(session: Session, group: AppGroup, *, name: str, description: str | None) -> AppGroup:
    name = name.strip()
    if not name:
        raise AppGroupError("an app group needs a name")
    group.name = name
    group.description = description or None
    session.flush()
    return group


def delete(session: Session, group: AppGroup) -> None:
    session.delete(group)
    session.flush()
