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

"""Retire the scrolling grid on kiosks saved before W377 (2026-10-12).

Operator: existing scrolling-grid kiosks are converted **now**, not when next
saved. The resolver merges stored specs as they are, so converting means a new
version of each such policy (profile sections included). The spec validator
already turns an undesigned kiosk into a Phone layout
(`KioskSpec._a_kiosk_is_always_designed`); this republishes through it.

A new version, never an edit in place: history stays intact and the change
shows in the policy's Versions list, with its reason in the notes. Idempotent,
because a converted spec has a device type; run at every start, it does
nothing after the first.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Policy, PolicyVersion
from app.policies.registry import PolicyTypeError, registry
from app.policies.specs.kiosk import ATLAS_CONSOLE_PACKAGE
from app.services import effective_policy as eff

log = logging.getLogger(__name__)

KIOSK = "KIOSK"
NOTES = "Converted to a Phone layout: the scrolling grid is retired"
PUBLISHED_BY = "ATLAS"


@dataclass
class Report:
    converted: list[str] = field(default_factory=list)
    #: (policy name, why it was left as it is)
    skipped: list[tuple[str, str]] = field(default_factory=list)


def needs_converting(spec: Any) -> bool:
    """A multi-app kiosk (an app besides the console) with no device type."""
    if not isinstance(spec, dict) or spec.get("launcher_device_type"):
        return False
    tiles = spec.get("multi_app_packages") or []
    return any(isinstance(t, dict) and t.get("package_name") not in (None, ATLAS_CONSOLE_PACKAGE) for t in tiles)


def convert_all(session: Session) -> Report:
    """Publish a Phone version of every stored scrolling-grid kiosk.

    A kiosk the Phone grid cannot hold (more than `MAX_PAGES` pages) is left as
    it is and reported: its devices keep drawing the scrolling grid, which the
    launcher still can, and the operator sees why the next time it is opened.
    """
    report = Report()
    affected: set[uuid.UUID] = set()
    for policy in session.scalars(select(Policy).where(Policy.policy_type == KIOSK)):
        latest = policy.latest_version
        if latest is None or not needs_converting(latest.spec):
            continue
        try:
            converted = registry.validate_spec(KIOSK, latest.spec)
        except PolicyTypeError as exc:
            report.skipped.append((policy.name, str(exc)))
            continue
        # Appended to the policy, not only added to the session: anything
        # reading `latest_version` in this session must see the new one.
        policy.versions.append(
            PolicyVersion(
                version=latest.version + 1,
                spec=converted,
                notes=NOTES,
                published_by=PUBLISHED_BY,
            )
        )
        session.flush()
        affected |= set(eff.devices_affected_by_policy(session, policy.id))
        report.converted.append(policy.name)
    if affected:
        eff.invalidate(session, affected)
    return report
