"""Devices, groups, tags, and membership."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import fetch_or_404, get_db, require_device
from app.api.schemas import (
    DeviceCreate,
    DeviceRead,
    GroupRead,
    MembershipUpdate,
    NamedCreate,
    TagCreate,
    TagRead,
)
from app.db.models import Device, DeviceGroup, EnrollmentState, Tag
from app.services import effective_policy as eff
from app.services.enrollment import revoke_device_certificates

router = APIRouter(prefix="/api/v1", tags=["inventory"])


def _commit(session: Session, conflict_message: str) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, conflict_message) from exc


# --------------------------------------------------------------------------- #
# Devices
# --------------------------------------------------------------------------- #


@router.post("/devices", response_model=DeviceRead, status_code=status.HTTP_201_CREATED)
def create_device(payload: DeviceCreate, session: Session = Depends(get_db)) -> Device:
    device = Device(**payload.model_dump())
    session.add(device)
    _commit(session, f"device {payload.serial_number!r} already exists")
    return device


@router.get("/devices", response_model=list[DeviceRead])
def list_devices(session: Session = Depends(get_db)) -> list[Device]:
    return list(session.scalars(select(Device).order_by(Device.serial_number)))


@router.get("/devices/{device_id}", response_model=DeviceRead)
def get_device(device: Device = Depends(require_device)) -> Device:
    return device


@router.post("/devices/{device_id}/retire", response_model=DeviceRead)
def retire_device(
    device: Device = Depends(require_device), session: Session = Depends(get_db)
) -> Device:
    """Retire a device and revoke its certificates, ending its access immediately."""
    device.enrollment_state = EnrollmentState.RETIRED
    revoke_device_certificates(session, device, reason="device retired")
    session.commit()
    return device


# --------------------------------------------------------------------------- #
# Groups and tags
# --------------------------------------------------------------------------- #


@router.post("/groups", response_model=GroupRead, status_code=status.HTTP_201_CREATED)
def create_group(payload: NamedCreate, session: Session = Depends(get_db)) -> DeviceGroup:
    group = DeviceGroup(name=payload.name, description=payload.description)
    session.add(group)
    _commit(session, f"group {payload.name!r} already exists")
    return group


@router.get("/groups", response_model=list[GroupRead])
def list_groups(session: Session = Depends(get_db)) -> list[DeviceGroup]:
    return list(session.scalars(select(DeviceGroup).order_by(DeviceGroup.name)))


@router.post("/tags", response_model=TagRead, status_code=status.HTTP_201_CREATED)
def create_tag(payload: TagCreate, session: Session = Depends(get_db)) -> Tag:
    tag = Tag(name=payload.name)
    session.add(tag)
    _commit(session, f"tag {payload.name!r} already exists")
    return tag


@router.get("/tags", response_model=list[TagRead])
def list_tags(session: Session = Depends(get_db)) -> list[Tag]:
    return list(session.scalars(select(Tag).order_by(Tag.name)))


# --------------------------------------------------------------------------- #
# Membership
#
# Membership changes alter which assignments reach a device, so both the devices
# joining and the devices leaving must have their cache dropped.
# --------------------------------------------------------------------------- #


def _apply_membership(
    session: Session, container: DeviceGroup | Tag, device_ids: list[uuid.UUID]
) -> list[Device]:
    devices = list(session.scalars(select(Device).where(Device.id.in_(device_ids))))
    found = {d.id for d in devices}
    missing = set(device_ids) - found
    if missing:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"unknown device ids: {', '.join(str(m) for m in sorted(missing, key=str))}",
        )

    previous = {d.id for d in container.devices}
    container.devices = devices
    session.flush()

    eff.invalidate(session, previous | found)
    session.commit()
    return devices


@router.put("/groups/{group_id}/devices", response_model=list[DeviceRead])
def set_group_devices(
    group_id: uuid.UUID, payload: MembershipUpdate, session: Session = Depends(get_db)
) -> list[Device]:
    group = fetch_or_404(session, DeviceGroup, group_id, "group")
    return _apply_membership(session, group, payload.device_ids)


@router.put("/tags/{tag_id}/devices", response_model=list[DeviceRead])
def set_tag_devices(
    tag_id: uuid.UUID, payload: MembershipUpdate, session: Session = Depends(get_db)
) -> list[Device]:
    tag = fetch_or_404(session, Tag, tag_id, "tag")
    return _apply_membership(session, tag, payload.device_ids)
