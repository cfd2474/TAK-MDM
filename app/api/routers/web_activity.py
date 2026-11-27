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

"""Web activity uploads from enrolled devices (W501).

Separate from check-in, for the reason device logs are: a busy device can have
hundreds of events waiting, and check-in must stay small on a thin link.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import authenticated_device, get_db
from app.api.schemas import WebEventUploadRequest, WebEventUploadResponse
from app.db.models import Device
from app.services import web_activity

router = APIRouter(prefix="/api/v1/device", tags=["device"])


@router.post("/web-events", response_model=WebEventUploadResponse)
def upload_web_events(
    payload: WebEventUploadRequest,
    device: Device = Depends(authenticated_device),
    session: Session = Depends(get_db),
) -> WebEventUploadResponse:
    """Store a page of the device's web activity.

    Idempotent: a page sent again after a lost reply is counted as duplicates,
    so the agent may delete what it sent once it has any 200 for it.
    """
    result = web_activity.store(session, device, (
        web_activity.Incoming(
            stream=e.stream, seq=e.seq, hostname=e.host, package_name=e.package,
            looked_up_at=e.at, lookups=e.lookups, blocked=e.blocked,
        )
        for e in payload.events
    ))
    session.commit()
    return WebEventUploadResponse(
        accepted=result.accepted, duplicates=result.duplicates, dropped=result.dropped,
    )
