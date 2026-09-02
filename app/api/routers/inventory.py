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

"""Devices, groups, tags, and membership."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import fetch_or_404, get_db, require_device
from app.api.schemas import (
    DeviceCreate,
    DeviceIdentifierRead,
    DeviceRead,
    DeviceUpdate,
    GroupRead,
    MembershipUpdate,
    NamedCreate,
    TagCreate,
    TagRead,
)
from app.db.models import Device, DeviceGroup, EnrollmentState, Tag
from app.services import device_identity
from app.services import effective_policy as eff
from app.services.enrollment import revoke_device_certificates

router = APIRouter(prefix="/api/v1", tags=["inventory"])

logger = logging.getLogger(__name__)


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


@router.patch("/devices/{device_id}", response_model=DeviceRead)
def update_device(
    payload: DeviceUpdate,
    device: Device = Depends(require_device),
    session: Session = Depends(get_db),
) -> Device:
    """Edit operator-owned device fields. Identity and reported attributes are not
    editable here — only the friendly name."""
    fields = payload.model_dump(exclude_unset=True)
    if "name" in fields:
        device.name = (fields["name"] or "").strip() or None
    session.commit()
    return device


@router.get(
    "/devices/{device_id}/identifiers", response_model=list[DeviceIdentifierRead]
)
def list_device_identifiers(
    device: Device = Depends(require_device), session: Session = Depends(get_db)
) -> list[DeviceIdentifierRead]:
    """Every identity this device has reported.

    Worth showing: a device holding only an `android_id` is one factory reset away
    from becoming a duplicate record, and that is invisible from anything else on
    the device page.
    """
    return [
        DeviceIdentifierRead.model_validate(row)
        for row in device_identity.for_device(session, device.id)
    ]


@router.post("/devices/{device_id}/retire", response_model=DeviceRead)
def retire_device(
    device: Device = Depends(require_device), session: Session = Depends(get_db)
) -> Device:
    """Retire a device and revoke its certificates, ending its access immediately."""
    device.enrollment_state = EnrollmentState.RETIRED
    revoke_device_certificates(session, device, reason="device retired")
    session.commit()
    return device


@router.delete(
    "/devices/{device_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    # Explicit: FastAPI would otherwise infer a response model from the `-> None`
    # return annotation, and a 204 is not allowed to carry a body.
    response_model=None,
)
def delete_device(
    device: Device = Depends(require_device), session: Session = Depends(get_db)
) -> None:
    """Permanently remove a device record.

    **Retirement is the normal answer; this is for records that should never have
    existed** — a failed enrolment that registered before erroring, or a test
    device. A device that genuinely served has history worth keeping, and the
    project's standing instinct is to archive rather than delete (D20).

    Requires the device to be retired first. That is what makes deletion two
    deliberate acts rather than one misplaced click on a working tablet, and
    retirement has already revoked the certificates by the time we get here — so
    there is no window where a live identity outlives its record.

    Everything hanging off the device (certificates, commands, log bundles,
    identifiers, group and tag membership, device-scoped assignments, cached
    policy, file selections) is removed by database cascade.
    """
    if device.enrollment_state is not EnrollmentState.RETIRED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "retire the device before deleting it: deletion is permanent and "
            "removes its history, so it is deliberately two steps",
        )

    # Belt and braces. The certificate rows cascade away, but revoking first means
    # the identity is dead even if the delete is rolled back.
    revoke_device_certificates(session, device, reason="device deleted")
    logger.info("deleting device %s (%s)", device.id, device.serial_number)
    session.delete(device)
    session.commit()


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
