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

"""App package ingestion.

The server inspects what it is handed rather than trusting the uploader: package
name, version, SDK levels, and signing certificate all come from the file itself.

Two checks are enforced here specifically because the alternative is an opaque
failure on a tablet in the field:

* **Signature pinning.** Android rejects an update whose signing certificate
  differs from the installed app. Catch it at upload, where the message can say so.
* **`targetSdk` floor.** Android 16 refuses to install anything targeting below
  API 24. On device that surfaces as `INSTALL_FAILED_DEPRECATED_SDK_VERSION`.
"""

from __future__ import annotations

import io
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artifacts.apk import ApkError, inspect_apk
from app.artifacts.bundles import InspectedBundle, PartRole, inspect
from app.artifacts.storage import ArtifactStorage
from app.db.models import (
    AppPackage,
    AppPackageFile,
    AppPackageVersion,
    Artifact,
    PartRole as DbPartRole,
)

# Android 16 holds the minimum installable targetSdk at API 24, unchanged from
# Android 15. Verified 2026-08-30; revisit when the fleet moves to Android 17.
MINIMUM_TARGET_SDK = 24

_MEDIA_TYPES = {
    PartRole.BASE: "application/vnd.android.package-archive",
    PartRole.SPLIT: "application/vnd.android.package-archive",
    PartRole.OBB: "application/octet-stream",
}


class PackageError(ValueError):
    """Raised when an upload cannot be accepted."""


@dataclass(frozen=True)
class IngestResult:
    package: AppPackage
    version: AppPackageVersion
    created: bool
    signature_sha256: str | None
    provisioning_checksum: str | None


def _validate(session: Session, bundle: InspectedBundle) -> AppPackage | None:
    if bundle.target_sdk is not None and bundle.target_sdk < MINIMUM_TARGET_SDK:
        raise PackageError(
            f"{bundle.package_name} targets SDK {bundle.target_sdk}; Android refuses "
            f"to install anything below API {MINIMUM_TARGET_SDK} "
            f"(INSTALL_FAILED_DEPRECATED_SDK_VERSION)"
        )

    if not bundle.signature_sha256:
        raise PackageError(
            f"{bundle.package_name} has no readable signing certificate (v1, v2, or "
            "v3); an unsigned APK cannot be installed"
        )

    existing = session.scalar(
        select(AppPackage).where(AppPackage.package_name == bundle.package_name)
    )
    if (
        existing
        and existing.signature_sha256
        and existing.signature_sha256 != bundle.signature_sha256
    ):
        raise PackageError(
            f"signing certificate for {bundle.package_name} does not match the "
            f"stored one (have {existing.signature_sha256[:16]}..., got "
            f"{bundle.signature_sha256[:16]}...). Android would reject this update "
            "on device; upload it under a different package or remove the existing "
            "package first."
        )
    return existing


def ingest(
    session: Session, storage: ArtifactStorage, data: bytes, *, label: str | None = None
) -> IngestResult:
    """Inspect an APK or XAPK/APKS upload, store its parts, and record the version."""
    try:
        bundle = inspect(data)
    except ApkError as exc:
        raise PackageError(str(exc)) from exc

    package = _validate(session, bundle)

    if package is None:
        package = AppPackage(
            package_name=bundle.package_name,
            label=label,
            signature_sha256=bundle.signature_sha256,
            signature_scheme=bundle.signature_scheme,
        )
        session.add(package)
        session.flush()
    else:
        # First upload may predate signature extraction; adopt it once known.
        package.signature_sha256 = package.signature_sha256 or bundle.signature_sha256
        package.signature_scheme = package.signature_scheme or bundle.signature_scheme
        package.label = label or package.label

    existing_version = session.scalar(
        select(AppPackageVersion).where(
            AppPackageVersion.package_id == package.id,
            AppPackageVersion.version_code == bundle.version_code,
        )
    )
    if existing_version is not None:
        raise PackageError(
            f"{bundle.package_name} version code {bundle.version_code} is already "
            "uploaded; bump versionCode to publish a new build"
        )

    version = AppPackageVersion(
        package_id=package.id,
        version_code=bundle.version_code,
        version_name=bundle.version_name,
        min_sdk=bundle.min_sdk,
        target_sdk=bundle.target_sdk,
    )
    session.add(version)
    session.flush()

    for part in bundle.parts:
        digest, size = storage.put(io.BytesIO(part.data))

        if session.get(Artifact, digest) is None:
            session.add(
                Artifact(
                    sha256=digest,
                    size_bytes=size,
                    media_type=_MEDIA_TYPES[part.role],
                )
            )
            session.flush()

        session.add(
            AppPackageFile(
                version_id=version.id,
                role=DbPartRole(part.role.value),
                file_name=part.file_name,
                split_name=part.info.split_name if part.info else None,
                artifact_sha256=digest,
            )
        )

    session.flush()
    # The versions collection was loaded before this one existed, and the new row was
    # added by foreign key rather than through the relationship. Reload so callers
    # see the full, correctly ordered set.
    session.refresh(package)

    return IngestResult(
        package=package,
        version=version,
        created=True,
        signature_sha256=bundle.signature_sha256,
        provisioning_checksum=bundle.base.info.provisioning_checksum if bundle.base.info else None,
    )


def delete_version(
    session: Session, storage: ArtifactStorage, version: AppPackageVersion
) -> int:
    """Delete a version, removing blobs no other version still references."""
    digests = [file.artifact_sha256 for file in version.files]
    session.delete(version)
    session.flush()

    removed = 0
    for digest in set(digests):
        still_used = session.scalar(
            select(AppPackageFile).where(AppPackageFile.artifact_sha256 == digest).limit(1)
        )
        if still_used is not None:
            continue  # shared with another version — content addressing at work
        artifact = session.get(Artifact, digest)
        if artifact is not None:
            session.delete(artifact)
        if storage.delete(digest):
            removed += 1

    session.flush()
    return removed


def delete_package(
    session: Session, storage: ArtifactStorage, package: AppPackage
) -> int:
    """Delete a package and every version, freeing blobs nothing else references."""
    digests = {
        file.artifact_sha256
        for version in package.versions
        for file in version.files
    }

    # One cascade removes every version and file; looping delete_version() here
    # would delete the same rows twice (the ORM cascade also fires) and warn.
    session.delete(package)
    session.flush()

    removed = 0
    for digest in digests:
        still_used = session.scalar(
            select(AppPackageFile).where(AppPackageFile.artifact_sha256 == digest).limit(1)
        )
        if still_used is not None:
            continue
        artifact = session.get(Artifact, digest)
        if artifact is not None:
            session.delete(artifact)
        if storage.delete(digest):
            removed += 1

    session.flush()
    return removed


def resolve_for_policy(
    session: Session, package_name: str, *, min_version_code: int | None = None
) -> AppPackageVersion | None:
    """Best version satisfying a policy's floor, or None if nothing qualifies."""
    package = session.scalar(
        select(AppPackage).where(AppPackage.package_name == package_name)
    )
    if package is None:
        return None

    candidates = [
        version
        for version in package.versions
        if min_version_code is None or version.version_code >= min_version_code
    ]
    return max(candidates, key=lambda v: v.version_code, default=None)


def get_by_id(session: Session, package_id: uuid.UUID) -> AppPackage | None:
    return session.get(AppPackage, package_id)


def declared_receivers(
    session: Session, storage: ArtifactStorage, package_name: str
) -> tuple[str, ...] | None:
    """Receivers declared by the latest build of a package, or None if unavailable.

    Used to check that a provisioning payload names an admin component the agent
    APK actually contains. Only the manifest entry is read, not the whole archive.
    Returns None rather than raising when nothing is uploaded — the caller then has
    nothing to verify against, which is not an error.
    """
    package = session.scalar(
        select(AppPackage).where(AppPackage.package_name == package_name)
    )
    version = package.latest_version if package else None
    if version is None:
        return None

    base = next((f for f in version.files if f.role is DbPartRole.BASE), None)
    if base is None or not storage.exists(base.artifact_sha256):
        return None

    try:
        with storage.open(base.artifact_sha256) as handle:
            return inspect_apk(handle.read()).receivers
    except (ApkError, OSError):
        return None
