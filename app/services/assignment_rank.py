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

"""Re-rank a policy or profile assignment from the page that owns it.

Rank was set only when assigning, and a profile's Assign gives every target one
rank, so one target could not be re-ranked on its own. Two pages now can:

- **the device page** (W383), for assignments made directly to that device;
- **the group page** (W385), for assignments made to that group.

⚠️ **The owner check is the control, not the template.** A device page must
not reorder a group's assignment (it looks per-device and would change every
member), and neither page may reach a row of another device or group through
a hand-edited URL. Each caller says who owns the row; anything else is refused
and nothing changes.

The reference is the assignment's id for a policy, or `profile:{id}` for a
profile assignment.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from contextlib import suppress

from sqlalchemy.orm import Session

from app.db.models import Assignment, Device, DeviceGroup, ProfileAssignment
from app.services import effective_policy as eff

#: Generous, and inside a 32-bit column. Ranks in practice are small numbers.
RANK_LIMIT = 1_000_000

PROFILE_PREFIX = "profile:"

AnyAssignment = Assignment | ProfileAssignment


class RerankRefused(ValueError):
    """Why a rank was not changed, in words the operator can act on."""


def parse_rank(raw: str) -> int:
    try:
        rank = int(str(raw).strip())
    except ValueError:
        raise RerankRefused("rank must be a whole number") from None
    if abs(rank) > RANK_LIMIT:
        raise RerankRefused(f"rank must be between -{RANK_LIMIT:,} and {RANK_LIMIT:,}")
    return rank


def profile_ref(profile_assignment_id: uuid.UUID) -> str:
    return f"{PROFILE_PREFIX}{profile_assignment_id}"


def rerank_for_device(session: Session, device: Device, ref: str, raw_rank: str) -> str:
    """Re-rank one of this device's direct assignments; returns its name."""
    return _rerank(
        session, ref, raw_rank,
        owns=lambda a: a.device_id == device.id,
        refusal=(
            "that policy is inherited from a group or tag; "
            "change its rank there rather than on this device"
        ),
    )


def rerank_for_group(session: Session, group: DeviceGroup, ref: str, raw_rank: str) -> str:
    """Re-rank one of this group's assignments; returns its name."""
    return _rerank(
        session, ref, raw_rank,
        owns=lambda a: a.group_id == group.id,
        refusal="that assignment does not belong to this group",
    )


def _rerank(
    session: Session,
    ref: str,
    raw_rank: str,
    *,
    owns: Callable[[AnyAssignment], bool],
    refusal: str,
) -> str:
    """Set the rank, invalidate every device it reaches, and commit.

    Raises `RerankRefused` and changes nothing when the rank is not a number,
    the row is gone, or the caller does not own it.
    """
    rank = parse_rank(raw_rank)
    assignment = _lookup(session, ref)
    if assignment is None:
        raise RerankRefused("that assignment no longer exists")
    if not owns(assignment):
        raise RerankRefused(refusal)

    assignment.rank = rank
    session.flush()
    if isinstance(assignment, ProfileAssignment):
        affected = eff.devices_targeted_by_profile_assignment(session, assignment)
        name = assignment.profile.name if assignment.profile else "the profile"
    else:
        affected = eff.devices_targeted_by(session, assignment)
        name = assignment.policy.name if assignment.policy else "the policy"
    eff.invalidate(session, affected)
    session.commit()
    return name


def _lookup(session: Session, ref: str) -> AnyAssignment | None:
    ref = str(ref)
    with suppress(ValueError):
        if ref.startswith(PROFILE_PREFIX):
            return session.get(ProfileAssignment, uuid.UUID(ref.removeprefix(PROFILE_PREFIX)))
        return session.get(Assignment, uuid.UUID(ref))
    return None
