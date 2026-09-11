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

"""The Manage section's fleet table.

Assembles one row per device — the device itself plus the names of every policy
reaching it — so the route stays thin and the template only renders (CLAUDE.md
§5). Deliberately does *not* resolve the effective policy per device: the table
answers "which policies apply here", not "what value won", and resolving the full
stack for every device on every page load is work the list view does not need.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Assignment,
    AssignmentScope,
    Device,
    Policy,
    PolicyProfile,
    ProfileAssignment,
)


@dataclass(frozen=True)
class FleetRow:
    device: Device
    policy_names: list[str]

    @property
    def policy_count(self) -> int:
        return len(self.policy_names)


def policy_names_for_device(session: Session, device: Device) -> list[str]:
    """The names of every non-archived policy reaching this device — directly, or
    through one of its groups. Matches what the resolver applies."""
    names: set[str] = set()

    direct = session.execute(
        select(Assignment, Policy.name)
        .join(Policy, Assignment.policy_id == Policy.id)
        .where(
            Assignment.enabled.is_(True),
            Policy.archived_at.is_(None),
            Policy.is_template.is_(False),
        )
    ).all()
    profiles = session.execute(
        select(ProfileAssignment, PolicyProfile.name)
        .join(PolicyProfile, ProfileAssignment.profile_id == PolicyProfile.id)
        .where(
            ProfileAssignment.enabled.is_(True), PolicyProfile.archived_at.is_(None)
        )
    ).all()

    group_ids = {g.id for g in device.groups}
    for assignment, name in (*direct, *profiles):
        if (
            (assignment.scope is AssignmentScope.DEVICE and assignment.device_id == device.id)
            or (assignment.scope is AssignmentScope.GROUP and assignment.group_id in group_ids)
        ):
            names.add(name)
    return sorted(names)


def fleet_rows(session: Session) -> list[FleetRow]:
    """Every device, newest-checked-in style ordering left to the caller.

    One query for devices, one for assignments. Archived policies and disabled
    assignments are excluded, matching what the resolver actually applies
    (`gather_assignments`).
    """
    devices = list(session.scalars(select(Device).order_by(Device.serial_number)))

    by_device: dict[object, set[str]] = {}
    by_group: dict[object, set[str]] = {}

    rows = session.execute(
        select(Assignment, Policy.name)
        .join(Policy, Assignment.policy_id == Policy.id)
        .where(
            Assignment.enabled.is_(True),
            Policy.archived_at.is_(None),
            Policy.is_template.is_(False),
        )
    ).all()

    for assignment, policy_name in rows:
        if assignment.scope is AssignmentScope.DEVICE:
            by_device.setdefault(assignment.device_id, set()).add(policy_name)
        elif assignment.scope is AssignmentScope.GROUP:
            by_group.setdefault(assignment.group_id, set()).add(policy_name)

    # Profile assignments contribute the profile's name (not each section's).
    profile_rows = session.execute(
        select(ProfileAssignment, PolicyProfile.name)
        .join(PolicyProfile, ProfileAssignment.profile_id == PolicyProfile.id)
        .where(
            ProfileAssignment.enabled.is_(True), PolicyProfile.archived_at.is_(None)
        )
    ).all()
    for assignment, profile_name in profile_rows:
        if assignment.scope is AssignmentScope.DEVICE:
            by_device.setdefault(assignment.device_id, set()).add(profile_name)
        elif assignment.scope is AssignmentScope.GROUP:
            by_group.setdefault(assignment.group_id, set()).add(profile_name)

    result: list[FleetRow] = []
    for device in devices:
        names: set[str] = set(by_device.get(device.id, set()))
        for group in device.groups:
            names |= by_group.get(group.id, set())
        result.append(FleetRow(device=device, policy_names=sorted(names)))
    return result
