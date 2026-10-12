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

"""Re-rank a policy or profile from the device page (W383).

Rank was set only when assigning, and a profile's Assign gives every target one
rank, so a single device could not be re-ranked on its own.

⚠️ **Only an assignment made directly to this device**, the same rule as Remove
(W118). A group or tag assignment belongs to the group or the tag: re-ranking it
from a page that looks per-device would reorder the policy on every device
sharing it. The check is here, not only in the template, because a hidden input
is not a control.

The reference is the assignment's id for a policy, or `profile:{id}` for a
profile assignment, which is what the device page's rows carry.
"""

from __future__ import annotations

import uuid
from contextlib import suppress

from sqlalchemy.orm import Session

from app.db.models import Assignment, Device, ProfileAssignment
from app.services import effective_policy as eff

#: Generous, and inside a 32-bit column. Ranks in practice are small numbers.
RANK_LIMIT = 1_000_000

PROFILE_PREFIX = "profile:"


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


def rerank(session: Session, device: Device, ref: str, raw_rank: str) -> str:
    """Set the rank of one of this device's direct assignments; returns its name.

    Invalidates every device the assignment reaches (only this one, by
    construction) and commits. Raises `RerankRefused` and changes nothing
    otherwise.
    """
    rank = parse_rank(raw_rank)
    assignment = _direct_assignment(session, device, ref)
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


def _direct_assignment(
    session: Session, device: Device, ref: str
) -> Assignment | ProfileAssignment:
    ref = str(ref)
    assignment: Assignment | ProfileAssignment | None = None
    with suppress(ValueError):
        if ref.startswith(PROFILE_PREFIX):
            assignment = session.get(
                ProfileAssignment, uuid.UUID(ref.removeprefix(PROFILE_PREFIX))
            )
        else:
            assignment = session.get(Assignment, uuid.UUID(ref))
    if assignment is None:
        raise RerankRefused("that assignment no longer exists")
    if assignment.device_id != device.id:
        raise RerankRefused(
            "that policy is inherited from a group or tag; "
            "change its rank there rather than on this device"
        )
    return assignment
