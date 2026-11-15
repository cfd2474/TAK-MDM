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

"""The device side of an ATAK pref extract (W433): the agent brings the file back.

Separate from check-in for the reason log bundles are: a file is uploaded a
handful of times in a device's life, and check-in runs every couple of minutes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import authenticated_device, get_db
from app.api.schemas import AtakPrefUploadRequest, AtakPrefUploadResponse
from app.db.models import Device
from app.services import atak_pref_extracts as extracts

router = APIRouter(prefix="/api/v1/device", tags=["device"])


@router.post("/atak-prefs", response_model=AtakPrefUploadResponse)
def upload_atak_prefs(
    payload: AtakPrefUploadRequest,
    device: Device = Depends(authenticated_device),
    session: Session = Depends(get_db),
) -> AtakPrefUploadResponse:
    """Store the plugin's export, or its error, for one request."""
    try:
        extract = extracts.receive(
            session, device, command_id=payload.command_id, ok=payload.ok,
            content=payload.content, error=payload.error, atak_version=payload.atak_version,
        )
    except extracts.ExtractTooLarge as exc:
        # 413, as for logs: the agent should stop retrying a file it can't shrink.
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(exc)) from exc
    except extracts.UnknownRequest as exc:
        # 410: deleted (or never made). The agent drops its files and stops.
        raise HTTPException(status.HTTP_410_GONE, str(exc)) from exc
    except extracts.ExtractError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()
    return AtakPrefUploadResponse(id=extract.id, status=extract.status, file_name=extract.file_name)
