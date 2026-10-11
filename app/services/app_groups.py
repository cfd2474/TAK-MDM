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

"""App groups — a named set of packages a policy can reference as a unit.

⚠️ **Two kinds, never mixed (W317).** Operator: *"atak can never be part of an app
group. plugins cannot be part of general apps group, general apps cannot be part
of plugin group"*. A group is `apps` or `plugins` from the moment it is created,
and the kind decides where the policy editor offers it: Required apps, or ATAK
Core and Plugins. The kinds are the policy editor's own partition (`app_kinds`,
W141), so a group can never carry a package its section would refuse.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AppGroup, AppPackage


class AppGroupError(Exception):
    """An app-group operation cannot be completed."""


APPS = "apps"
PLUGINS = "plugins"
KINDS = {APPS: "General apps", PLUGINS: "ATAK plugins"}


@dataclass(frozen=True)
class Library:
    """The library partitioned the way groups need it, asked once per request."""

    plugin_names: frozenset[str]

    @classmethod
    def of(cls, session: Session) -> "Library":
        from app.services import atak_compat

        return cls(frozenset(atak_compat.plugin_packages(session)))

    def kind_of(self, package_name: str) -> str | None:
        """The group kind a package may join, or None for ATAK, which joins none."""
        from app.services import atak_compat

        if atak_compat.is_atak(package_name):
            return None
        return PLUGINS if package_name in self.plugin_names else APPS

    def why_not(self, package_name: str, kind: str) -> str | None:
        """Why a package cannot join a group of this kind, or None if it can."""
        found = self.kind_of(package_name)
        if found == kind:
            return None
        if found is None:
            return (
                f"{package_name} is ATAK, which is never part of an app group: it "
                "is chosen under ATAK Core in a policy"
            )
        if found == PLUGINS:
            return (
                f"{package_name} is an ATAK plugin and cannot be part of a general "
                "apps group: put it in an ATAK plugins group"
            )
        return (
            f"{package_name} is not an ATAK plugin and cannot be part of an ATAK "
            "plugins group: put it in a general apps group"
        )

    def misfits(self, group: AppGroup) -> list[str]:
        """Members that do not belong, from groups made before the split.

        ⚠️ Shown, never deleted: the picker does not offer them, so the
        operator's next save drops them, and the policy editor never inserts
        them.
        """
        return [p.package_name for p in group.packages if self.why_not(p.package_name, group.kind)]


def list_groups(session: Session) -> list[AppGroup]:
    return list(session.scalars(select(AppGroup).order_by(AppGroup.name)))


def get(session: Session, group_id: uuid.UUID) -> AppGroup | None:
    return session.get(AppGroup, group_id)


def create(
    session: Session, *, name: str, description: str | None = None, kind: str = APPS
) -> AppGroup:
    name = name.strip()
    if not name:
        raise AppGroupError("an app group needs a name")
    if kind not in KINDS:
        raise AppGroupError(f"an app group is general apps or ATAK plugins, not {kind!r}")
    group = AppGroup(name=name, description=(description or None), kind=kind)
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
    # ⚠️ ATLAS's own apps reach a device by other means (W273). The picker
    # never offers them; this is what stops a stale page or the API.
    from app.services import reserved_packages

    for pid in package_ids:
        if reserved_packages.is_reserved(found[pid].package_name):
            raise AppGroupError(reserved_packages.why(found[pid].package_name))
    # ⚠️ The picker offers only the group's kind (W317); this is what stops a
    # stale page or the API.
    library = Library.of(session)
    for pid in package_ids:
        reason = library.why_not(found[pid].package_name, group.kind)
        if reason:
            raise AppGroupError(reason)
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
