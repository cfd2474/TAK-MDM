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

"""Managed file catalog: upload, list, delete, and per-device selections."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import fetch_or_404, get_db, get_storage, require_device
from app.api.schemas import FileSelectionRead, ManagedFileRead, ManagedFileUpdate
from app.artifacts.storage import ArtifactStorage
from app.config import Settings, get_settings
from app.db.models import Device, ManagedFile
from app.services import effective_policy as eff
from app.services import files as file_service

router = APIRouter(prefix="/api/v1/files", tags=["files"])


@router.post("", response_model=ManagedFileRead, status_code=status.HTTP_201_CREATED)
def upload_file(
    file: UploadFile = File(..., description="any file: zip, .pref, cert, map source"),
    name: str | None = Form(default=None),
    description: str | None = Form(default=None),
    session: Session = Depends(get_db),
    storage: ArtifactStorage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
) -> ManagedFile:
    data = file.file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"upload exceeds {settings.max_upload_bytes} bytes",
        )

    try:
        managed = file_service.ingest_file(
            session,
            storage,
            data,
            name=name or file.filename or "unnamed",
            original_filename=file.filename or "unnamed",
            description=description,
            media_type=file.content_type or "application/octet-stream",
        )
    except file_service.FileError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    session.commit()
    return managed


@router.get("", response_model=list[ManagedFileRead])
def list_files(session: Session = Depends(get_db)) -> list[ManagedFile]:
    return list(session.scalars(select(ManagedFile).order_by(ManagedFile.name)))


@router.get("/{file_id}", response_model=ManagedFileRead)
def get_file(file_id: uuid.UUID, session: Session = Depends(get_db)) -> ManagedFile:
    return fetch_or_404(session, ManagedFile, file_id, "file")


@router.patch("/{file_id}", response_model=ManagedFileRead)
def update_file(
    file_id: uuid.UUID,
    payload: ManagedFileUpdate,
    session: Session = Depends(get_db),
) -> ManagedFile:
    """Edit a file's name/description and its suggested deployment defaults. The
    file's bytes and detected archive status are not editable."""
    managed: ManagedFile = fetch_or_404(session, ManagedFile, file_id, "file")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "name" and not value:
            continue
        setattr(managed, field, value)
    session.commit()
    return managed


@router.delete(
    "/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    response_class=Response,
)
def delete_file(
    file_id: uuid.UUID,
    session: Session = Depends(get_db),
    storage: ArtifactStorage = Depends(get_storage),
) -> None:
    managed: ManagedFile = fetch_or_404(session, ManagedFile, file_id, "file")
    file_service.delete_file(session, storage, managed)
    # Any policy referencing it now resolves differently.
    eff.invalidate_all(session)
    session.commit()


selections_router = APIRouter(prefix="/api/v1/devices", tags=["files"])


@selections_router.get("/{device_id}/file-selections", response_model=list[FileSelectionRead])
def list_device_selections(
    device: Device = Depends(require_device), session: Session = Depends(get_db)
) -> list[FileSelectionRead]:
    """Which optional files this device's user actually chose to install."""
    return [
        FileSelectionRead(
            file_id=selection.file_id,
            name=selection.file.name if selection.file else "(deleted)",
            applied_at=selection.applied_at,
        )
        for selection in file_service.list_selections(session, device.id)
    ]
