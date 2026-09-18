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

"""App-group endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.schemas import (
    AppGroupCreate,
    AppGroupMembers,
    AppGroupRead,
    AppGroupUpdate,
)
from app.db.models import AppGroup
from app.services import app_groups as service

router = APIRouter(prefix="/api/v1/app-groups", tags=["app-groups"])


def _get(session: Session, group_id: uuid.UUID) -> AppGroup:
    group = service.get(session, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "app group not found")
    return group


@router.get("", response_model=list[AppGroupRead])
def list_groups(session: Session = Depends(get_db)) -> list[AppGroup]:
    return service.list_groups(session)


@router.post("", response_model=AppGroupRead, status_code=status.HTTP_201_CREATED)
def create_group(payload: AppGroupCreate, session: Session = Depends(get_db)) -> AppGroup:
    try:
        group = service.create(session, name=payload.name, description=payload.description)
        if payload.package_ids:
            service.set_members(session, group, payload.package_ids)
    except service.AppGroupError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"an app group named {payload.name!r} already exists"
        ) from exc
    return group


@router.get("/{group_id}", response_model=AppGroupRead)
def get_group(group_id: uuid.UUID, session: Session = Depends(get_db)) -> AppGroup:
    return _get(session, group_id)


@router.patch("/{group_id}", response_model=AppGroupRead)
def update_group(
    group_id: uuid.UUID, payload: AppGroupUpdate, session: Session = Depends(get_db)
) -> AppGroup:
    group = _get(session, group_id)
    try:
        service.rename(
            session,
            group,
            name=payload.name if payload.name is not None else group.name,
            description=payload.description,
        )
    except service.AppGroupError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()
    return group


@router.put("/{group_id}/members", response_model=AppGroupRead)
def set_members(
    group_id: uuid.UUID, payload: AppGroupMembers, session: Session = Depends(get_db)
) -> AppGroup:
    group = _get(session, group_id)
    try:
        service.set_members(session, group, payload.package_ids)
    except service.AppGroupError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()
    return group


@router.delete(
    "/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    response_class=Response,
)
def delete_group(group_id: uuid.UUID, session: Session = Depends(get_db)) -> None:
    service.delete(session, _get(session, group_id))
    session.commit()
