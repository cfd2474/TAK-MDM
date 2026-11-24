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

"""Which policies and profiles a standard administrator may touch (W495 B4).

Operator decision 2: a standard admin may create and edit policies only when
every device the policy reaches is in their scope. Read here as: **every
target the policy has — each device and each group — is in their scope.**

⚠️ **Targets, not today's reach.** A policy assigned to a group outside the
scope that happens to be empty reaches no device now, and would reach the next
device put in that group. Judging by targets keeps the answer stable.

⚠️ **The reserved profiles never qualify.** The breach profile has no
assignments; it reaches every device whose breach flag is set, wherever it is.

⚠️ **Templates and archived policies never qualify (B7, operator: "I approve
your recommendations").** Both have no targets — archiving removes a profile's
assignments — so the "every target in scope" rule alone would hand them to
every standard admin with policies.edit, and those are the super admin's.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Assignment,
    AssignmentScope,
    Policy,
    PolicyProfile,
    ProfileAssignment,
)
from app.services import profiles
from app.services.admin_scopes import DeviceScope


@dataclass(frozen=True)
class Targets:
    device_ids: frozenset[uuid.UUID] = frozenset()
    group_ids: frozenset[uuid.UUID] = frozenset()
    #: Reaches devices by some other route (the breach profile).
    reserved: bool = False
    #: A template or an archived policy: the super admin's alone.
    super_only: bool = False

    def __or__(self, other: "Targets") -> "Targets":
        return Targets(
            self.device_ids | other.device_ids,
            self.group_ids | other.group_ids,
            self.reserved or other.reserved,
            self.super_only or other.super_only,
        )

    def within(self, scope: DeviceScope) -> bool:
        if scope.unrestricted:
            return True
        if self.reserved or self.super_only:
            return False
        return self.device_ids <= scope.device_ids and self.group_ids <= scope.group_ids


def _of_rows(rows) -> Targets:
    devices, groups = set(), set()
    for row in rows:
        if row.scope is AssignmentScope.DEVICE and row.device_id:
            devices.add(row.device_id)
        elif row.scope is AssignmentScope.GROUP and row.group_id:
            groups.add(row.group_id)
    return Targets(frozenset(devices), frozenset(groups))


def _super_only(item: Policy | PolicyProfile | None) -> bool:
    return item is not None and (bool(item.is_template) or item.archived_at is not None)


def of_profile(session: Session, profile_id: uuid.UUID) -> Targets:
    profile = session.get(PolicyProfile, profile_id)
    reserved = profile is not None and profile.name in profiles.RESERVED_NAMES
    rows = session.scalars(
        select(ProfileAssignment).where(ProfileAssignment.profile_id == profile_id)
    )
    return _of_rows(rows) | Targets(reserved=reserved, super_only=_super_only(profile))


def of_policy(session: Session, policy_id: uuid.UUID) -> Targets:
    """A policy's own assignments, and its profile's when it is a section."""
    targets = _of_rows(
        session.scalars(select(Assignment).where(Assignment.policy_id == policy_id))
    )
    policy = session.get(Policy, policy_id)
    targets = targets | Targets(super_only=_super_only(policy))
    if policy is not None and policy.profile_id is not None:
        targets = targets | of_profile(session, policy.profile_id)
    return targets


def of_assignment(row: Assignment | ProfileAssignment) -> Targets:
    return _of_rows([row])


def policy_within(session: Session, scope: DeviceScope, policy_id: uuid.UUID) -> bool:
    return scope.unrestricted or of_policy(session, policy_id).within(scope)


def profile_within(session: Session, scope: DeviceScope, profile_id: uuid.UUID) -> bool:
    return scope.unrestricted or of_profile(session, profile_id).within(scope)


def requested_within(
    scope: DeviceScope,
    device_ids=(),
    group_ids=(),
) -> bool:
    """Whether targets someone asked for are all in scope."""
    return Targets(frozenset(device_ids), frozenset(group_ids)).within(scope)


def visible_policies(session: Session, scope: DeviceScope, policies) -> list:
    """The policies a standard admin may see, in their order; all for a super."""
    if scope.unrestricted:
        return list(policies)
    return [p for p in policies if of_policy(session, p.id).within(scope)]


def visible_profiles(session: Session, scope: DeviceScope, items) -> list:
    if scope.unrestricted:
        return list(items)
    return [p for p in items if of_profile(session, p.id).within(scope)]


# --------------------------------------------------------------------------- #
# Shared templates (B8)
# --------------------------------------------------------------------------- #
#
# A super admin may share a template with chosen standard admins. Sharing lets
# them create a policy *from* it (the copy is theirs, with no targets) and
# nothing else: opening, editing, archiving and deleting the template stay
# refused by the rules above. An archived template is never usable.


def _live_template(item) -> bool:
    return item is not None and bool(item.is_template) and item.archived_at is None


def profile_template_usable(session: Session, scope: DeviceScope, profile_id: uuid.UUID) -> bool:
    if scope.unrestricted:
        return True
    return profile_id in scope.profile_template_ids and _live_template(
        session.get(PolicyProfile, profile_id))


def policy_template_usable(session: Session, scope: DeviceScope, policy_id: uuid.UUID) -> bool:
    if scope.unrestricted:
        return True
    return policy_id in scope.policy_template_ids and _live_template(
        session.get(Policy, policy_id))


def profile_copyable(session: Session, scope: DeviceScope, profile_id: uuid.UUID) -> bool:
    """May this profile be the source of a copy: theirs, or shared with them."""
    return profile_within(session, scope, profile_id) or profile_template_usable(
        session, scope, profile_id)


def policy_copyable(session: Session, scope: DeviceScope, policy_id: uuid.UUID) -> bool:
    return policy_within(session, scope, policy_id) or policy_template_usable(
        session, scope, policy_id)


def usable_profile_templates(scope: DeviceScope, items) -> list:
    """The profile templates to list: all for a super, the shared live ones else."""
    if scope.unrestricted:
        return list(items)
    return [t for t in items if t.id in scope.profile_template_ids and _live_template(t)]


def usable_policy_templates(scope: DeviceScope, items) -> list:
    if scope.unrestricted:
        return list(items)
    return [t for t in items if t.id in scope.policy_template_ids and _live_template(t)]
