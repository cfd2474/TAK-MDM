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

"""Device-facing check-in, authenticated by mTLS.

The protocol is **desired state, not a command stream**. The device says which
version it holds; the server replies with the current declarative state only if that
differs, and the agent diffs and converges locally. A device dark for three weeks
receives one document and catches up — it never replays an ordered backlog whose
intermediate steps have been overtaken (D5).

A small imperative queue survives alongside it, for the genuinely momentary actions
that cannot be expressed as state: reboot, lock, wipe, locate.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import authenticated_device, get_bundle_signer, get_db, get_storage
from app.api.schemas import CheckinRequest, CheckinResponse, CommandEnvelope
from app.artifacts.storage import ArtifactStorage
from app.config import Settings, get_settings
from app.db.models import ComplianceStatus, Device
from app.security.bundle import BundleSigner
from app.services import commands as command_service
from app.services import desired_state as desired_state_service
from app.services import effective_policy as eff
from app.services import agent_update as agent_update_service
from app.services import files as file_service
from app.services import fleet as fleet_service

router = APIRouter(prefix="/api/v1/device", tags=["device"])


def _next_checkin_seconds(settings: Settings) -> int:
    """Jittered interval, so a fleet restored together does not return in lockstep."""
    base = settings.checkin_interval_seconds
    spread = base * settings.checkin_jitter_ratio
    return max(60, int(random.uniform(base - spread, base + spread)))


def _record_convergence(device: Device, payload: CheckinRequest) -> None:
    """Update what the device has actually applied, and how well.

    Kept separate from ``state_version``: the server's intent and the device's
    reality are different facts, and conflating them is how a fleet dashboard ends
    up reporting compliance it never verified (D28).
    """
    if (
        payload.applied_state_version is None
        and not payload.apply_errors
        and not payload.apply_warnings
    ):
        return  # nothing reported; leave the previous verdict standing

    if payload.applied_state_version is not None:
        # Monotonic: a stale duplicate check-in must not walk the value backwards.
        device.acked_state_version = max(
            device.acked_state_version, payload.applied_state_version
        )

    # Warnings are recorded on every report, including a clean one, so a mismatch
    # that has been resolved stops being shown (W50).
    device.compliance_warnings = (
        "; ".join(payload.apply_warnings)[:2000] if payload.apply_warnings else None
    )

    if payload.apply_errors:
        device.compliance_status = (
            ComplianceStatus.FAILED
            if payload.applied_state_version is None
            else ComplianceStatus.DEGRADED
        )
        device.compliance_detail = "; ".join(payload.apply_errors)[:2000]
    else:
        # ⚠️ Warnings deliberately do not appear here. A device carrying a newer
        # build than its policy names *has* converged — the operator's own rule is
        # that the newer build satisfies the requirement — so calling it DEGRADED
        # would both misreport it and, because the agent-update gate refuses a
        # DEGRADED device, quietly stop it ever receiving another agent build.
        device.compliance_status = ComplianceStatus.COMPLIANT
        device.compliance_detail = None


@router.post("/checkin", response_model=CheckinResponse)
def checkin(
    payload: CheckinRequest,
    device: Device = Depends(authenticated_device),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    signer: BundleSigner = Depends(get_bundle_signer),
    # Only for the one-off scan of a build uploaded before its declared
    # configuration was recorded (W49); the common path is a DB read.
    storage: ArtifactStorage = Depends(get_storage),
) -> CheckinResponse:
    device.last_checkin_at = datetime.now(timezone.utc)
    device.agent_version = payload.agent_version or device.agent_version
    device.os_version = payload.os_version or device.os_version
    # Only overwritten when reported. An agent too old to send these would
    # otherwise erase a perfectly good record on every check-in.
    if payload.atak_version:
        device.atak_package = payload.atak_package
        device.atak_version = payload.atak_version

    # "Settled" means this device has already checked in at least once on the
    # agent build it is running. Computed *before* the column is overwritten, so
    # the first check-in after an update never counts — which is what stops a
    # crash-looping build being handed another update on every relaunch (W27).
    reported_code = payload.agent_version_code
    agent_settled = reported_code is not None and device.agent_version_code == reported_code
    if reported_code is not None:
        device.agent_version_code = reported_code

    # Results first: a command finished this cycle should not be handed back below.
    _, unknown_command_ids = command_service.record_results(session, device, payload.results)
    _record_convergence(device, payload)

    # The device's report of which optional items its user has applied is
    # authoritative; omitting the field leaves the record untouched (F4).
    if payload.applied_optional_files is not None:
        file_service.record_selections(session, device, payload.applied_optional_files)

    # Settle any pending recompute so state_version is current before comparison.
    eff.get_effective(session, device)

    policy_changed = payload.state_version != device.state_version
    send_bundle = policy_changed or payload.force_full

    bundle = (
        desired_state_service.build_signed(session, device, signer, storage)
        if send_bundle
        else None
    )
    live_commands = command_service.claim_for_delivery(session, device)
    policy_names = fleet_service.policy_names_for_device(session, device)
    # After _record_convergence, so the eligibility gate sees the compliance this
    # very check-in reported rather than the previous one's.
    agent_offer = agent_update_service.offer_for(
        session, device, package_name=settings.agent_package_name, settled=agent_settled
    )

    session.commit()

    return CheckinResponse(
        device_id=device.id,
        state_version=device.state_version,
        generated_at=datetime.now(timezone.utc),
        policy_changed=policy_changed,
        name=device.name,
        policy_names=policy_names,
        agent_update=agent_offer,
        desired_state=bundle["desired_state"] if bundle else None,
        signature=bundle["signature"] if bundle else None,
        commands=[
            CommandEnvelope(
                id=command.id,
                command_type=command.command_type,
                params=command.params or {},
                expires_at=command.expires_at,
            )
            for command in live_commands
        ],
        next_checkin_seconds=_next_checkin_seconds(settings),
        unknown_command_ids=unknown_command_ids,
    )
