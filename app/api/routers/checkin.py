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

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import (
    authenticated_device,
    get_bundle_signer,
    get_ca,
    get_db,
    get_storage,
    presented_certificate,
)
from app.api.schemas import (
    CertificatePolicy,
    CertificateRenewalRequest,
    CertificateRenewalResponse,
    CheckinRequest,
    CheckinResponse,
    CommandEnvelope,
)
from cryptography import x509

from app.artifacts.storage import ArtifactStorage
from app.config import Settings, get_settings
from app.db.models import ComplianceStatus, Device
from app.security.bundle import BundleSigner
from app.security.ca import CertificateAuthority
from app.services import alerts
from app.services import breach
from app.services import commands as command_service
from app.services import disenroll
from app.services import desired_state as desired_state_service
from app.services import effective_policy as eff
from app.services import agent_update as agent_update_service
from app.services import files as file_service
from app.services import fleet as fleet_service
from app.services import locations as location_service
from app.services import certificate_renewal

router = APIRouter(prefix="/api/v1/device", tags=["device"])


def _next_checkin_seconds(settings: Settings) -> int:
    """Jittered interval, so a fleet restored together does not return in lockstep."""
    base = settings.checkin_interval_seconds
    spread = base * settings.checkin_jitter_ratio
    return max(60, int(random.uniform(base - spread, base + spread)))


def _record_convergence(
    device: Device, payload: CheckinRequest, session: Session | None = None
) -> None:
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

    # ⚠️ Captured **before** the new verdict is written, because the alert
    # fires on the *transition* into a bad state and not on being in one
    # (W195). A device that has been failing for a week sets FAILED on every
    # single check-in; alerting on the value rather than the change would email
    # the operator every few minutes about a fault they already know about —
    # which is the fastest possible way to make them stop reading.
    was = device.compliance_status

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

    if session is not None:
        _alert_on_compliance_change(session, device, was)


#: The verdicts that mean a device is not doing what it was told.
_BAD_COMPLIANCE = (ComplianceStatus.DEGRADED, ComplianceStatus.FAILED)


def _alert_on_compliance_change(
    session: Session, device: Device, was: ComplianceStatus
) -> None:
    """Tell the operator when a device *becomes* non-compliant, and when it stops.

    ⚠️ DEGRADED to FAILED is not a new alert. Both mean "not applying its
    policy", the operator has already been told, and a second message about the
    same broken device saying something slightly different is noise wearing the
    clothes of information.
    """
    now_bad = device.compliance_status in _BAD_COMPLIANCE
    was_bad = was in _BAD_COMPLIANCE
    if now_bad and not was_bad:
        alerts.note_event(
            session, "device_out_of_compliance", device, device.compliance_detail
        )


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
    # Same rule, same reason: only overwrite what was actually reported. An empty
    # list is still a report ("this device claims no ABIs") and is kept distinct
    # from the older agent that says nothing at all.
    if payload.supported_abis is not None:
        device.supported_abis = ",".join(payload.supported_abis)
    if payload.sdk_int is not None:
        device.sdk_int = payload.sdk_int

    # ⚠️ Each guarded separately, and each meaning "only overwrite what we were
    # actually told" (W32). A device that stops reporting a field keeps the last
    # value we had rather than losing it — which for an IMEI is the difference
    # between a record an operator can act on and a blank one.
    if payload.has_telephony is not None:
        device.has_telephony = payload.has_telephony
    if payload.imei is not None:
        device.imei = payload.imei
    if payload.imei2 is not None:
        device.imei2 = payload.imei2
    if payload.phone_number is not None:
        device.phone_number = payload.phone_number
    # ⚠️ Battery is the exception that proves the rule: it is *volatile*, so the
    # newest report always wins, and 0 is a real reading rather than "unsaid" —
    # `is not None` matters here in a way `if payload.battery_level` would get
    # exactly backwards on a flat device, which is the one worth seeing.
    if payload.battery_level is not None:
        device.battery_level = payload.battery_level
    if payload.battery_charging is not None:
        device.battery_charging = payload.battery_charging

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

    # ⚠️ Before anything else reads the device, because this deletes it (W104).
    #
    # The acknowledgement means "received, resetting now" — it arrives from a
    # device that still exists, and no later message ever will. So the record goes
    # here, and the response is deliberately empty: there is nothing to ask of a
    # tablet that is erasing itself, and every field below would be computed from
    # a row that no longer exists.
    if disenroll.acknowledged(session, device):
        device_id = device.id
        state_version = device.state_version
        disenroll.complete(session, device)
        session.commit()
        return CheckinResponse(
            device_id=device_id,
            state_version=state_version,
            generated_at=datetime.now(timezone.utc),
            policy_changed=False,
            next_checkin_seconds=settings.checkin_interval_seconds,
            unknown_command_ids=unknown_command_ids,
        )

    # ⚠️ After the disenroll return, not before it. A device being wiped is about
    # to have its record deleted and its points cascade with it, so storing them
    # here would be work whose only result is a larger transaction.
    #
    # Both sources land in the same place: the batch the device buffered, and any
    # `locate` an operator asked for and the device answered this cycle. The
    # second means history starts filling for devices with no tracking policy at
    # all, which is also what gives C3's map something to draw before C2 ships.
    location_service.record(session, device, payload.locations)
    location_service.record_locate_results(session, device, payload.results)

    _record_convergence(device, payload, session)

    # The device's report of which optional items its user has applied is
    # authoritative; omitting the field leaves the record untouched (F4).
    if payload.applied_optional_files is not None:
        file_service.record_selections(session, device, payload.applied_optional_files)

    # Settle any pending recompute so state_version is current before comparison.
    eff.get_effective(session, device)

    # ⚠️ **Confirmed means "the device acted on it", not "it all worked"**
    # (W193). Apply errors are recorded separately, just above, and shown on the
    # device page; a breach that half-succeeded is still a breach that reached
    # the device, and conflating the two would leave a tablet that obeyed
    # looking identical to one that never heard.
    #
    # Converged while in breach is the signal: the device has applied the state
    # the server is holding, and while breached that state *is* the breach
    # policy. Read after `get_effective` so `state_version` is the current one
    # rather than the value from before this check-in's recompute.
    if (
        breach.is_engaged(device)
        and device.acked_state_version == device.state_version
        and breach.confirm(session, device)
    ):
        session.flush()

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
        # Stated on every check-in rather than at enrolment: a device enrolled a
        # year ago must learn a changed window without being re-provisioned, which
        # is the whole point of the exercise.
        certificate=CertificatePolicy(
            renew_within_days=settings.device_cert_renew_within_days,
            validity_days=settings.device_cert_validity_days,
        ),
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


@router.post("/certificate", response_model=CertificateRenewalResponse)
def renew_certificate(
    payload: CertificateRenewalRequest,
    device: Device = Depends(authenticated_device),
    presented: x509.Certificate = Depends(presented_certificate),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    ca: CertificateAuthority = Depends(get_ca),
) -> CertificateRenewalResponse:
    """Issue this device a fresh certificate over the connection it already has.

    ⚠️ **Authenticated by the certificate being replaced.** That is what makes it
    safe to leave unauthenticated enrolment alone: only a device already holding a
    valid identity can extend it, so this adds no way in.

    ⚠️ **The previous certificate stays valid.** Revoking it here would cut the
    connection carrying this reply, and a device that never received the answer
    would have destroyed the credential it had. It expires on its own.
    """
    try:
        renewal = certificate_renewal.renew(
            session,
            device,
            presented,
            payload.csr_pem,
            ca=ca,
            validity_days=settings.device_cert_validity_days,
        )
    except certificate_renewal.RenewalRefused as exc:
        # 400, not 500: the device asked for something it may not have, and it
        # keeps working with what it holds. Logged by the service.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    session.commit()
    return CertificateRenewalResponse(
        certificate_pem=renewal.certificate_pem,
        ca_pem=renewal.ca_pem,
        serial_hex=renewal.serial_hex,
        not_valid_after=renewal.not_valid_after,
    )
