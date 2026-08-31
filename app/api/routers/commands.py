"""Admin endpoints for the transient command queue and device convergence."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import fetch_or_404, get_bundle_signer, get_db, require_device
from app.api.schemas import CommandCreate, CommandRead
from app.db.models import Device, DeviceCommand
from app.security.bundle import BundleSigner
from app.services import commands as command_service
from app.services import desired_state as desired_state_service

router = APIRouter(prefix="/api/v1", tags=["commands"])


@router.post(
    "/devices/{device_id}/commands",
    response_model=CommandRead,
    status_code=status.HTTP_201_CREATED,
)
def enqueue_command(
    payload: CommandCreate,
    device: Device = Depends(require_device),
    session: Session = Depends(get_db),
) -> DeviceCommand:
    """Queue a one-shot action. It is delivered on the device's next check-in."""
    try:
        command = command_service.enqueue(
            session,
            device,
            command_type=payload.command_type,
            params=payload.params,
            ttl_hours=payload.ttl_hours,
            max_attempts=payload.max_attempts,
        )
    except command_service.CommandError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    session.commit()
    return command


@router.get("/devices/{device_id}/commands", response_model=list[CommandRead])
def list_commands(
    include_finished: bool = True,
    device: Device = Depends(require_device),
    session: Session = Depends(get_db),
) -> list[DeviceCommand]:
    # Expire on read so the console never shows a stale command as deliverable.
    command_service.expire_stale(session, device)
    session.commit()
    return command_service.list_for_device(
        session, device.id, include_finished=include_finished
    )


@router.post("/commands/{command_id}/cancel", response_model=CommandRead)
def cancel_command(
    command_id: uuid.UUID, session: Session = Depends(get_db)
) -> DeviceCommand:
    command = fetch_or_404(session, DeviceCommand, command_id, "command")
    command_service.cancel(session, command)
    session.commit()
    return command


@router.get("/devices/{device_id}/desired-state")
def get_desired_state(
    device: Device = Depends(require_device),
    session: Session = Depends(get_db),
    signer: BundleSigner = Depends(get_bundle_signer),
) -> dict[str, Any]:
    """Exactly what the device would receive, for debugging a divergence."""
    bundle = desired_state_service.build_signed(session, device, signer)
    session.commit()
    return {
        **bundle,
        "acked_state_version": device.acked_state_version,
        "compliance_status": device.compliance_status.value,
        "compliance_detail": device.compliance_detail,
    }


@router.get("/bundle-signing-key")
def get_bundle_signing_key(signer: BundleSigner = Depends(get_bundle_signer)) -> dict[str, str]:
    """Public key agents pin to verify desired-state bundles."""
    return {"algorithm": "ed25519", "public_key": signer.public_key_base64()}
