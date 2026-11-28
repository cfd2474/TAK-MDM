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

"""What each standard administrator may reach (W495).

A scope is three things a super admin sets per username: the categories of
action (`app.security.permissions.CATEGORIES`), the device groups, and single
devices. The devices a standard admin may act on are the named devices plus
every device in the named groups (`device_ids_in_scope`).

⚠️ **Read defensively.** A stored category that is no longer a grantable one —
renamed, removed, or SUPER written in by hand — is dropped on read, never
honoured. Writing refuses it outright.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Device,
    DeviceGroup,
    Policy,
    PolicyProfile,
    StandardAdminScope,
    device_group_member,
    standard_admin_scope_device,
    standard_admin_scope_group,
    standard_admin_scope_policy_template,
    standard_admin_scope_profile_template,
)
from app.security.admin_auth import AdminIdentity
from app.security.permissions import CATEGORIES, Permission


class ScopeError(ValueError):
    """A scope the super admin asked for that cannot be stored, with why."""


def _username(value: str) -> str:
    name = (value or "").strip()
    if not name:
        raise ScopeError("Give the administrator's Authentik username.")
    if len(name) > 150:
        raise ScopeError("That username is too long (150 characters at most).")
    return name


def granted_categories(raw: Iterable | None) -> frozenset[Permission]:
    """The grantable categories in a stored list; anything else is dropped."""
    out = set()
    for value in raw or ():
        try:
            permission = Permission(value)
        except ValueError:
            continue
        if permission in CATEGORIES:
            out.add(permission)
    return frozenset(out)


def get(session: Session, username: str) -> StandardAdminScope | None:
    return session.scalar(
        select(StandardAdminScope).where(StandardAdminScope.username == username)
    )


def categories_for(session: Session, username: str) -> frozenset[Permission]:
    scope = get(session, username)
    return granted_categories(scope.categories) if scope else frozenset()


def save(
    session: Session,
    *,
    username: str,
    categories: Iterable[str],
    group_ids: Iterable[uuid.UUID] = (),
    device_ids: Iterable[uuid.UUID] = (),
    profile_template_ids: Iterable[uuid.UUID] = (),
    policy_template_ids: Iterable[uuid.UUID] = (),
    by: str | None,
) -> StandardAdminScope:
    """Create or replace one administrator's scope. Commits."""
    name = _username(username)

    wanted: set[Permission] = set()
    for value in categories:
        try:
            permission = Permission(value)
        except ValueError:
            raise ScopeError(f"{value!r} is not a permission ATLAS knows.") from None
        if permission not in CATEGORIES:
            raise ScopeError(
                f"{permission.value!r} cannot be granted to a standard administrator."
            )
        wanted.add(permission)

    group_ids = set(group_ids)
    groups = list(
        session.scalars(select(DeviceGroup).where(DeviceGroup.id.in_(group_ids)))
    ) if group_ids else []
    if len(groups) != len(group_ids):
        raise ScopeError("One of the device groups no longer exists. Reload and retry.")

    device_ids = set(device_ids)
    devices = list(
        session.scalars(select(Device).where(Device.id.in_(device_ids)))
    ) if device_ids else []
    if len(devices) != len(device_ids):
        raise ScopeError("One of the devices no longer exists. Reload and retry.")

    profile_templates = _templates(session, PolicyProfile, profile_template_ids)
    policy_templates = _templates(session, Policy, policy_template_ids)

    scope = get(session, name)
    if scope is None:
        scope = StandardAdminScope(username=name)
        session.add(scope)
    # Sorted, so the stored list (and an audit of it) does not change order
    # between two saves of the same choice.
    scope.categories = sorted(p.value for p in wanted)
    scope.groups = groups
    scope.devices = devices
    scope.profile_templates = profile_templates
    scope.policy_templates = policy_templates
    scope.updated_by = by
    session.commit()
    return scope


def _templates(session: Session, model, ids: Iterable[uuid.UUID]) -> list:
    """The live templates named, or ScopeError: only a template can be shared."""
    ids = set(ids)
    if not ids:
        return []
    found = list(session.scalars(select(model).where(model.id.in_(ids))))
    if len(found) != len(ids) or any(
        not t.is_template or t.archived_at is not None for t in found
    ):
        raise ScopeError("One of the templates no longer exists. Reload and retry.")
    return found


def shared_with(
    session: Session, *, profile_id: uuid.UUID | None = None,
    policy_id: uuid.UUID | None = None,
) -> list[str]:
    """The standard admins a template is shared with, by name (B8)."""
    if profile_id is not None:
        link, column, value = (standard_admin_scope_profile_template,
                               standard_admin_scope_profile_template.c.profile_id, profile_id)
    else:
        link, column, value = (standard_admin_scope_policy_template,
                               standard_admin_scope_policy_template.c.policy_id, policy_id)
    return list(session.scalars(
        select(StandardAdminScope.username)
        .join(link, link.c.scope_id == StandardAdminScope.id)
        .where(column == value)
        .order_by(StandardAdminScope.username)
    ))


def delete(session: Session, username: str) -> bool:
    """Forget one administrator's scope. Commits. False when there was none."""
    scope = get(session, username)
    if scope is None:
        return False
    session.delete(scope)
    session.commit()
    return True


def device_ids_in_scope(session: Session, username: str) -> frozenset[uuid.UUID]:
    """The devices this administrator may act on: named ones, and every device
    in a named group. Empty when they have no scope."""
    scope_id = select(StandardAdminScope.id).where(
        StandardAdminScope.username == username
    ).scalar_subquery()
    named = select(standard_admin_scope_device.c.device_id).where(
        standard_admin_scope_device.c.scope_id == scope_id
    )
    grouped = select(device_group_member.c.device_id).where(
        device_group_member.c.group_id.in_(
            select(standard_admin_scope_group.c.group_id).where(
                standard_admin_scope_group.c.scope_id == scope_id
            )
        )
    )
    return frozenset(session.scalars(named.union(grouped)))


def group_ids_in_scope(session: Session, username: str) -> frozenset[uuid.UUID]:
    """The device groups named in this administrator's scope."""
    scope_id = select(StandardAdminScope.id).where(
        StandardAdminScope.username == username
    ).scalar_subquery()
    return frozenset(session.scalars(
        select(standard_admin_scope_group.c.group_id).where(
            standard_admin_scope_group.c.scope_id == scope_id
        )
    ))


def template_ids_in_scope(
    session: Session, username: str
) -> tuple[frozenset[uuid.UUID], frozenset[uuid.UUID]]:
    """The profile templates and policy templates shared with this admin (B8)."""
    scope_id = select(StandardAdminScope.id).where(
        StandardAdminScope.username == username
    ).scalar_subquery()
    profiles = frozenset(session.scalars(
        select(standard_admin_scope_profile_template.c.profile_id).where(
            standard_admin_scope_profile_template.c.scope_id == scope_id
        )
    ))
    policies = frozenset(session.scalars(
        select(standard_admin_scope_policy_template.c.policy_id).where(
            standard_admin_scope_policy_template.c.scope_id == scope_id
        )
    ))
    return profiles, policies


@dataclass(frozen=True)
class DeviceScope:
    """Which devices and device groups one request may see and act on.

    ⚠️ `unrestricted` is the only way to mean "everything". An empty set means
    nothing, never all: a standard admin with no scope sees no devices.
    """

    unrestricted: bool
    device_ids: frozenset[uuid.UUID] = frozenset()
    group_ids: frozenset[uuid.UUID] = frozenset()
    #: Templates a super admin shared with them (B8). They may create a
    #: policy from one; nothing else. `policy_scope` applies it.
    profile_template_ids: frozenset[uuid.UUID] = frozenset()
    policy_template_ids: frozenset[uuid.UUID] = frozenset()

    @classmethod
    def everything(cls) -> "DeviceScope":
        return cls(unrestricted=True)

    @classmethod
    def for_username(cls, session: Session, username: str) -> "DeviceScope":
        profile_templates, policy_templates = template_ids_in_scope(session, username)
        return cls(
            unrestricted=False,
            device_ids=device_ids_in_scope(session, username),
            group_ids=group_ids_in_scope(session, username),
            profile_template_ids=profile_templates,
            policy_template_ids=policy_templates,
        )

    def has_device(self, device_id: uuid.UUID) -> bool:
        return self.unrestricted or device_id in self.device_ids

    def has_group(self, group_id: uuid.UUID) -> bool:
        return self.unrestricted or group_id in self.group_ids

    def devices(self, items: Iterable, key=lambda d: d.id) -> list:
        """The items whose device is in scope, in their order."""
        if self.unrestricted:
            return list(items)
        return [item for item in items if key(item) in self.device_ids]

    def groups(self, items: Iterable, key=lambda g: g.id) -> list:
        if self.unrestricted:
            return list(items)
        return [item for item in items if key(item) in self.group_ids]


class StoredGrants:
    """`GrantSource` that reads the categories a super admin stored."""

    def __init__(self, session: Session):
        self._session = session

    def categories_for(self, identity: AdminIdentity) -> frozenset[Permission]:
        return categories_for(self._session, identity.username)
