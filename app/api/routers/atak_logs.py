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

"""ATAK session logs: the agent uploads them, the console lists them (W416).

One session per request, gzip, as a multipart file beside its description. One
per request so a session that fails to arrive costs only itself, and a retry
resends one file rather than a bundle.

Split into a device router and an admin router for the same reason
`device_logs` is (D71): one must stay open to a tablet presenting its
certificate, the other must sit behind admin authentication.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.deps import authenticated_device, fetch_or_404, get_atak_log_store, get_db
from app.artifacts.atak_log_store import AtakLogStore
from app.db.models import Device
from app.services import atak_log_archive as archive

router = APIRouter(prefix="/api/v1/device", tags=["device"])
admin_router = APIRouter(prefix="/api/v1/devices", tags=["atak-logs"])


class AtakLogUploaded(BaseModel):
    id: uuid.UUID
    #: False when a finished copy of this session was already held.
    kept: bool
    complete: bool


class AtakLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    file_name: str
    started_at: datetime | None
    complete: bool
    size_bytes: int
    stored_bytes: int
    atak_version: str | None
    uploaded_at: datetime


@router.post("/atak-logs", response_model=AtakLogUploaded, status_code=status.HTTP_201_CREATED)
def upload_atak_log(
    file: UploadFile = File(...),
    file_name: str = Form(...),
    started_at: str | None = Form(None),
    complete: bool = Form(False),
    atak_version: str | None = Form(None),
    device: Device = Depends(authenticated_device),
    session: Session = Depends(get_db),
    store: AtakLogStore = Depends(get_atak_log_store),
) -> AtakLogUploaded:
    """Keep one ATAK session log from an enrolled device."""
    try:
        row, kept = archive.store(
            session, store, device, file.file,
            file_name=file_name,
            started_at=archive.parse_started_at(started_at),
            complete=complete,
            atak_version=atak_version,
        )
    except archive.UploadTooLarge as exc:
        # 413: the agent should stop retrying a file it cannot shrink.
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(exc)) from exc
    except archive.UploadRefused as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()
    return AtakLogUploaded(id=row.id, kept=kept, complete=row.complete)


@admin_router.get("/{device_id}/atak-logs", response_model=list[AtakLogRead])
def list_atak_logs(device_id: uuid.UUID, session: Session = Depends(get_db)) -> list[AtakLogRead]:
    """One device's ATAK sessions, newest first. Metadata only."""
    fetch_or_404(session, Device, device_id, "device")
    return [AtakLogRead.model_validate(row) for row in archive.list_for_device(session, device_id)]
