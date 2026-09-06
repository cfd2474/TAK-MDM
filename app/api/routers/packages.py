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

"""App package upload and catalog administration."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import fetch_or_404, get_db, get_storage
from app.api.schemas import (
    PackageRead,
    PackageUpdate,
    PackageUploadResult,
    PackageVersionRead,
)
from app.artifacts.storage import ArtifactStorage
from app.config import Settings, get_settings
from app.db.models import AppPackage, AppPackageVersion
from app.services import effective_policy as eff
from app.services import packages as package_service

router = APIRouter(prefix="/api/v1/packages", tags=["packages"])


@router.post("", response_model=PackageUploadResult, status_code=status.HTTP_201_CREATED)
def upload_package(
    file: UploadFile = File(..., description="an .apk, .xapk, .apks, or .apkm"),
    label: str | None = Form(default=None),
    session: Session = Depends(get_db),
    storage: ArtifactStorage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
) -> PackageUploadResult:
    """Inspect an upload, store its parts content-addressed, and record the version.

    The server reads identity, version, and signing certificate out of the file
    itself rather than trusting form fields — a caller cannot claim an APK is
    something it is not.
    """
    data = file.file.read()
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "uploaded file is empty")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"upload exceeds {settings.max_upload_bytes} bytes",
        )

    try:
        result = package_service.ingest(session, storage, data, label=label)
    except package_service.PackageError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    # A new build changes what devices requiring this app must do, without any
    # policy text changing. Their resolved desired state has to be recomputed.
    eff.invalidate_all(session)
    session.commit()

    return PackageUploadResult(
        package=PackageRead.model_validate(result.package),
        version=PackageVersionRead.model_validate(result.version),
        signature_sha256=result.signature_sha256,
        provisioning_checksum=result.provisioning_checksum,
    )


@router.get("", response_model=list[PackageRead])
def list_packages(session: Session = Depends(get_db)) -> list[AppPackage]:
    return list(session.scalars(select(AppPackage).order_by(AppPackage.package_name)))


@router.get("/{package_id}", response_model=PackageRead)
def get_package(package_id: uuid.UUID, session: Session = Depends(get_db)) -> AppPackage:
    return fetch_or_404(session, AppPackage, package_id, "package")


@router.get("/{package_id}/icon", include_in_schema=False)
def get_package_icon(
    package_id: uuid.UUID, session: Session = Depends(get_db)
) -> Response:
    """The app's launcher icon, exactly as it was stored in the APK (W53).

    404 when the app has no extractable icon — a vector-drawable icon is a normal
    outcome, and the page falls back to its placeholder. Served from the row
    rather than the artifact store, so there is no blob to have gone missing.

    Cached hard and privately: the bytes only change when a build with a
    redesigned icon is uploaded, and the response is behind the admin guard, so a
    shared cache must not hold it.
    """
    package: AppPackage = fetch_or_404(session, AppPackage, package_id, "package")
    if not package.icon_data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "this app has no stored icon")

    return Response(
        content=package.icon_data,
        media_type=package.icon_media_type or "application/octet-stream",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.patch("/{package_id}", response_model=PackageRead)
def update_package(
    package_id: uuid.UUID,
    payload: PackageUpdate,
    session: Session = Depends(get_db),
) -> AppPackage:
    """Edit operator-owned package fields: its label and whether the ATLAS store
    lists it. Identity and signing details are read from the file, not set here."""
    package: AppPackage = fetch_or_404(session, AppPackage, package_id, "package")
    fields = payload.model_dump(exclude_unset=True)
    if "label" in fields:
        package.label = (fields["label"] or "").strip() or None
    if "store_listed" in fields and fields["store_listed"] is not None:
        if package.store_listed != fields["store_listed"]:
            package.store_listed = fields["store_listed"]
            # The store is offered to every device, and no policy edit accompanies
            # this — so without invalidating, the shelf changes and nobody is told.
            eff.invalidate_all(session)
    session.commit()
    return package


@router.delete(
    "/{package_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    response_class=Response,
)
def delete_package(
    package_id: uuid.UUID,
    session: Session = Depends(get_db),
    storage: ArtifactStorage = Depends(get_storage),
) -> None:
    """Remove a package and all its versions."""
    package: AppPackage = fetch_or_404(session, AppPackage, package_id, "package")
    package_service.delete_package(session, storage, package)
    eff.invalidate_all(session)
    session.commit()


@router.delete(
    "/{package_id}/versions/{version_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    response_class=Response,
)
def delete_package_version(
    package_id: uuid.UUID,
    version_id: uuid.UUID,
    session: Session = Depends(get_db),
    storage: ArtifactStorage = Depends(get_storage),
) -> None:
    version: AppPackageVersion = fetch_or_404(
        session, AppPackageVersion, version_id, "package version"
    )
    if version.package_id != package_id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "that version does not belong to this package"
        )

    package_service.delete_version(session, storage, version)
    eff.invalidate_all(session)
    session.commit()
