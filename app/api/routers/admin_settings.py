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

"""Admin API: custom attributes and per-device values."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_device
from app.api.schemas import (
    CustomAttributeCreate,
    CustomAttributeRead,
    DeviceAttributeRead,
    DeviceAttributeSet,
)
from app.db.models import CustomAttribute, Device
from app.services import custom_attributes as service

router = APIRouter(prefix="/api/v1/custom-attributes", tags=["admin"])


@router.get("", response_model=list[CustomAttributeRead])
def list_attributes(session: Session = Depends(get_db)) -> list[CustomAttribute]:
    return service.list_attributes(session)


@router.post("", response_model=CustomAttributeRead, status_code=status.HTTP_201_CREATED)
def create_attribute(
    payload: CustomAttributeCreate, session: Session = Depends(get_db)
) -> CustomAttribute:
    try:
        attribute = service.create(
            session,
            name=payload.name,
            attr_type=payload.attr_type,
            description=payload.description,
        )
    except service.AttributeError_ as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"an attribute named {payload.name!r} already exists"
        ) from exc
    return attribute


@router.delete(
    "/{attribute_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    response_class=Response,
)
def delete_attribute(attribute_id: uuid.UUID, session: Session = Depends(get_db)) -> None:
    attribute = session.get(CustomAttribute, attribute_id)
    if attribute is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "attribute not found")
    service.delete(session, attribute)
    session.commit()


device_router = APIRouter(prefix="/api/v1/devices", tags=["admin"])


@device_router.get(
    "/{device_id}/attributes", response_model=list[DeviceAttributeRead]
)
def device_attributes(
    device: Device = Depends(require_device), session: Session = Depends(get_db)
) -> list[DeviceAttributeRead]:
    return [
        DeviceAttributeRead(
            attribute_id=attr.id, name=attr.name, attr_type=attr.attr_type, value=value
        )
        for attr, value in service.values_for_device(session, device.id)
    ]


@device_router.put(
    "/{device_id}/attributes", response_model=list[DeviceAttributeRead]
)
def set_device_attribute(
    payload: DeviceAttributeSet,
    device: Device = Depends(require_device),
    session: Session = Depends(get_db),
) -> list[DeviceAttributeRead]:
    if session.get(CustomAttribute, payload.attribute_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "attribute not found")
    service.set_value(session, device.id, payload.attribute_id, payload.value)
    session.commit()
    return [
        DeviceAttributeRead(
            attribute_id=attr.id, name=attr.name, attr_type=attr.attr_type, value=value
        )
        for attr, value in service.values_for_device(session, device.id)
    ]
