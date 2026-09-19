"""Device-facing diagnostic log upload.

Copyright 2026 TAK-Solutions LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

Separate from check-in on purpose. A log bundle is up to half a megabyte and is
produced a handful of times in a device's life; check-in runs every couple of
minutes on a link this fleet is assumed to have very little of. Folding one into
the other would make every routine check-in carry the worst case.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import authenticated_device, fetch_or_404, get_db
from app.api.schemas import (
    DeviceLogBundleDetail,
    DeviceLogBundleRead,
    DeviceLogUploadRequest,
    DeviceLogUploadResponse,
)
from app.db.models import Device
from app.services import device_logs as log_service

router = APIRouter(prefix="/api/v1/device", tags=["device"])

# Split from the device router for the same reason enrollment is (D71): one half
# must stay open to a tablet presenting a certificate, the other must be behind
# admin authentication. Separate routers make that boundary structural.
admin_router = APIRouter(prefix="/api/v1/devices", tags=["device-logs"])


@router.post("/logs", response_model=DeviceLogUploadResponse, status_code=status.HTTP_201_CREATED)
def upload_logs(
    payload: DeviceLogUploadRequest,
    device: Device = Depends(authenticated_device),
    session: Session = Depends(get_db),
) -> DeviceLogUploadResponse:
    """Accept one diagnostic bundle from an enrolled device."""
    try:
        bundle = log_service.store(
            session,
            device,
            content=payload.content,
            command_id=payload.command_id,
            agent_version=payload.agent_version,
            truncated=payload.truncated,
        )
    except log_service.LogBundleTooLarge as exc:
        # 413 rather than 400: the agent should stop retrying a bundle it cannot
        # shrink, and the status says which of the two problems it has.
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc)
        ) from exc

    session.commit()
    return DeviceLogUploadResponse(
        id=bundle.id, size_bytes=bundle.size_bytes, collected_at=bundle.collected_at
    )


@admin_router.get("/{device_id}/logs", response_model=list[DeviceLogBundleRead])
def list_logs(
    device_id: uuid.UUID, session: Session = Depends(get_db)
) -> list[DeviceLogBundleRead]:
    """Captures for one device, newest first.

    Metadata only. A listing that inlined every bundle would ship megabytes of log
    text to render a page showing when they arrived.
    """
    fetch_or_404(session, Device, device_id, "device")
    return [
        DeviceLogBundleRead.model_validate(bundle)
        for bundle in log_service.list_for_device(session, device_id)
    ]


@admin_router.get("/{device_id}/logs/{bundle_id}", response_model=DeviceLogBundleDetail)
def read_log(
    device_id: uuid.UUID, bundle_id: uuid.UUID, session: Session = Depends(get_db)
) -> DeviceLogBundleDetail:
    """One capture, with its contents."""
    bundle = log_service.get(session, bundle_id)
    # Matched against the device as well as the id, so a bundle id cannot be used
    # to read another device's logs by guessing (the same rule as D34).
    if bundle is None or bundle.device_id != device_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="log bundle not found"
        )
    return DeviceLogBundleDetail.model_validate(bundle)
