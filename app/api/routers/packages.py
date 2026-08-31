"""App package upload and catalog administration."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import fetch_or_404, get_db, get_storage
from app.api.schemas import PackageRead, PackageUploadResult, PackageVersionRead
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
