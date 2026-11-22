"""Device-facing upload of the Device Package List Report (W335).

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

Separate from check-in for the reason logs are: a few hundred packages is tens
of kilobytes, produced when an operator asks, and every routine check-in would
otherwise carry it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import authenticated_device, get_db
from app.api.schemas import PackageReportUpload, PackageReportUploadResponse
from app.db.models import Device
from app.services import package_reports

router = APIRouter(prefix="/api/v1/device", tags=["device"])


@router.post(
    "/package-report",
    response_model=PackageReportUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_package_report(
    payload: PackageReportUpload,
    device: Device = Depends(authenticated_device),
    session: Session = Depends(get_db),
) -> PackageReportUploadResponse:
    try:
        report = package_reports.store(
            session,
            device,
            [p.model_dump() for p in payload.packages],
            command_id=payload.command_id,
            agent_version=payload.agent_version,
        )
    except package_reports.ReportTooLarge as exc:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(exc)) from exc
    session.commit()
    return PackageReportUploadResponse(
        package_count=report.package_count, collected_at=report.collected_at
    )
