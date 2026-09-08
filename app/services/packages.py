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

import json

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


@dataclass(frozen=True)
class VersionComparison:
    """How an upload relates to what the library already deploys.

    Built *before* the upload is committed so the console can say what will happen
    rather than what has happened — uploading used to deploy to the whole fleet
    with no confirmation anywhere.
    """

    #: "first" | "newer" | "older" | "same"
    relation: str
    package_name: str
    version_code: int
    version_name: str | None
    #: The build currently deployed for this package, if any.
    deployed_version_code: int | None = None
    deployed_version_name: str | None = None
    #: Names of policies whose required_apps mention this package.
    policy_names: tuple[str, ...] = ()
    #: How many enrolled devices those policies reach.
    device_count: int = 0

    @property
    def would_deploy(self) -> bool:
        """True when publishing this build changes what devices install."""
        return self.relation in ("first", "newer")


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
    session: Session,
    storage: ArtifactStorage,
    data: bytes,
    *,
    label: str | None = None,
    publish: bool | None = None,
) -> IngestResult:
    """Inspect an APK or XAPK/APKS upload, store its parts, and record the version.

    ``publish`` decides whether the new build is eligible for automatic selection.
    Left as None it defaults by comparison: a build **newer** than everything
    published is published, and an **older** one is held. That keeps an upload from
    quietly moving a fleet backwards, and matches what the operator almost always
    means by uploading an old build — keeping it available, not deploying it.
    """
    try:
        bundle = inspect(data)
    except ApkError as exc:
        raise PackageError(str(exc)) from exc

    package = _validate(session, bundle)

    if package is None:
        package = AppPackage(
            package_name=bundle.package_name,
            label=label or bundle.label,
            signature_sha256=bundle.signature_sha256,
            signature_scheme=bundle.signature_scheme,
        )
        _apply_icon(package, bundle)
        session.add(package)
        session.flush()
    else:
        # First upload may predate signature extraction; adopt it once known.
        package.signature_sha256 = package.signature_sha256 or bundle.signature_sha256
        package.signature_scheme = package.signature_scheme or bundle.signature_scheme
        # An explicit label always wins; otherwise adopt the app's own name if
        # this package never got one (W51) — a build uploaded before the name
        # could be read should not stay called by its package id forever.
        package.label = label or package.label or bundle.label
        # A newer build may ship a redesigned icon, and the app list should show
        # what the device will actually draw — so this one does replace.
        _apply_icon(package, bundle)

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

    if publish is None:
        # Never let an upload move a fleet backwards by accident: an older build is
        # held, a newer one (or the first) is published.
        #
        # ⚠️ Only compared **within one ATAK line**. Two builds of a plugin
        # targeting different ATAK versions are alternatives, not a sequence, and
        # their versionCodes do not order — UAS Tool for ATAK 5.8.0 carries a
        # *lower* code than the 5.5.0 build (D45). Ranking across lines would
        # publish whichever number happened to be bigger.
        deployed = latest_published(session, package)
        if deployed is None:
            publish = True
        elif deployed.plugin_api != bundle.plugin_api:
            publish = False
        else:
            publish = bundle.version_code > deployed.version_code

    version = AppPackageVersion(
        package_id=package.id,
        version_code=bundle.version_code,
        version_name=bundle.version_name,
        min_sdk=bundle.min_sdk,
        target_sdk=bundle.target_sdk,
        plugin_api=bundle.plugin_api,
        # "" is a real answer — no native code, so it runs anywhere. See the
        # column's note on why that is not the same as NULL.
        abis=",".join(bundle.abis),
        published=publish,
        # Scanned once, here, from the base part (W49). The device needs each key's
        # declared type to build a Bundle the app can actually read.
        # Read during inspection, while the resource table was already in hand
        # (W54). Falls back to a scan only for a bundle that predates that.
        declared_config=json.dumps(
            bundle.base.info.declared_config
            if bundle.base.info is not None and bundle.base.info.declared_config
            else _declared_config_of(bundle.base.data)
        ),
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
    """Best **published** version satisfying a policy's floor, or None.

    Held builds are skipped here and only here. This is the *automatic* selection
    path — "latest", or "newest above the floor" — and publishing is what an
    operator uses to say a build may be chosen automatically. An explicit
    `artifact_sha256` pin names one exact build and bypasses this entirely (W31).
    """
    package = session.scalar(
        select(AppPackage).where(AppPackage.package_name == package_name)
    )
    if package is None:
        return None

    candidates = [
        version
        for version in package.versions
        if version.published
        and (min_version_code is None or version.version_code >= min_version_code)
    ]
    return max(candidates, key=lambda v: v.version_code, default=None)


def latest_published(session: Session, package: AppPackage) -> AppPackageVersion | None:
    """The build this package currently deploys, or None if every one is held."""
    return max(
        (v for v in package.versions if v.published),
        key=lambda v: v.version_code,
        default=None,
    )


def compare_upload(session: Session, data: bytes) -> VersionComparison:
    """What this upload would do, without committing anything.

    Inspects the bytes and reads the library, so the console can present the
    decision *before* it is taken. Raises the same `PackageError`s `ingest` would,
    so an upload that cannot be accepted is rejected here rather than after the
    operator has answered a question about it.
    """
    try:
        bundle = inspect(data)
    except ApkError as exc:
        raise PackageError(str(exc)) from exc

    package = _validate(session, bundle)
    if package is None:
        return VersionComparison(
            relation="first",
            package_name=bundle.package_name,
            version_code=bundle.version_code,
            version_name=bundle.version_name,
        )

    duplicate = any(v.version_code == bundle.version_code for v in package.versions)
    deployed = latest_published(session, package)
    if duplicate:
        relation = "same"
    elif deployed is None or bundle.version_code > deployed.version_code:
        relation = "newer"
    else:
        relation = "older"

    policy_names, device_count = _reach_of(session, bundle.package_name)
    return VersionComparison(
        relation=relation,
        package_name=bundle.package_name,
        version_code=bundle.version_code,
        version_name=bundle.version_name,
        deployed_version_code=deployed.version_code if deployed else None,
        deployed_version_name=deployed.version_name if deployed else None,
        policy_names=policy_names,
        device_count=device_count,
    )


def _reach_of(session: Session, package_name: str) -> tuple[tuple[str, ...], int]:
    """Policies naming this package, and how many devices they reach.

    Read from each policy's **current** version only. Older PolicyVersions are kept
    for the audit trail (D2) but are not what any device is running, so counting
    them would inflate the number an operator is asked to act on.
    """
    from app.db.models import Assignment, Policy
    from app.services import effective_policy as eff

    names: list[str] = []
    device_ids: set[uuid.UUID] = set()

    for policy in session.scalars(
        select(Policy).where(Policy.archived_at.is_(None), Policy.is_template.is_(False))
    ):
        latest = policy.latest_version
        required = ((latest.spec if latest else None) or {}).get("required_apps") or []
        if not any(entry.get("package_name") == package_name for entry in required):
            continue

        # A profile section is reached through its profile, never assigned directly
        # (W21). Naming the profile is what an operator recognises.
        names.append(policy.profile.name if policy.profile else policy.name)

        if policy.profile_id is not None:
            device_ids |= eff.devices_affected_by_profile(session, policy.profile_id)
        else:
            for assignment in session.scalars(
                select(Assignment).where(Assignment.policy_id == policy.id)
            ):
                device_ids |= eff.devices_targeted_by(session, assignment)

    return tuple(sorted(set(names))), len(device_ids)


def _declared_config_of(base_apk: bytes) -> dict[str, int]:
    """`{key: restrictionType}` for a base APK's top-level managed configuration.

    Types only — titles and defaults are for the editor, but the device needs the
    type and nothing else: it is what turns the operator's "300" into an int the
    app can read rather than a string it silently ignores.
    """
    from app.artifacts.app_restrictions import discover

    found = discover(base_apk, "")
    return {key.key: key.restriction_type for key in found.keys}


def declared_config(
    session: Session, version: AppPackageVersion, storage: ArtifactStorage
) -> dict[str, int]:
    """The version's declared configuration, scanning once if it predates W49.

    NULL means never scanned, which is not the same as "declares nothing" — an app
    that genuinely declares nothing stores an empty object. Without that
    distinction every un-scanned build would look like an app with no
    configuration, and the difference is invisible from the outside.
    """
    if version.declared_config is not None:
        try:
            return json.loads(version.declared_config)
        except ValueError:
            return {}

    base = next((f for f in version.files if f.role is PartRole.BASE), None)
    if base is None:
        return {}
    try:
        with storage.open(base.artifact_sha256) as handle:
            declared = _declared_config_of(handle.read())
    except Exception:  # noqa: BLE001 — a missing blob must not fail a check-in
        return {}

    version.declared_config = json.dumps(declared)
    session.flush()
    return declared


def _apply_icon(package: AppPackage, bundle: InspectedBundle) -> None:
    """Record an extracted launcher icon on the package.

    ⚠️ Only when one was found. An APK whose icon is a vector drawable yields
    None, and that must leave an existing icon alone rather than blanking it —
    otherwise re-uploading a build with an unreadable icon would erase a good one.
    """
    if bundle.icon is None:
        return
    package.icon_data = bundle.icon.data
    package.icon_media_type = bundle.icon.media_type
    package.icon_adaptive = bundle.icon.adaptive


def backfill_labels(session: Session, storage: ArtifactStorage) -> int:
    """Give a display name and icon to packages uploaded before either was read.

    Chrome went in as `com.android.chrome` because the name was never looked for
    (W51), and nothing had an icon until W53. Re-reading the base APK fixes both
    without asking the operator to upload 130 MB again — and reads it **once**,
    because the name and the icon are two questions about the same file.

    ⚠️ Only fills a **missing** label. An operator who typed their own name meant
    it, and a convenience pass must not overwrite a deliberate choice. The icon
    has no such rule: it is never operator-supplied, so a package missing one
    simply gets it.

    A version whose blob has gone is skipped rather than failing the run — this is
    a convenience pass, not a migration.
    """
    from app.artifacts.bundles import inspect_single_apk
    from app.artifacts.storage import ArtifactNotFound

    filled = 0
    needs_label = (AppPackage.label.is_(None)) | (AppPackage.label == AppPackage.package_name)
    # Filtering on `icon_media_type` rather than `icon_data`: both are equivalent
    # as SQL, but the small column is also what the loop below tests, and that one
    # would otherwise load a deferred blob per package just to see if it is there.
    candidates = session.scalars(
        select(AppPackage).where(needs_label | AppPackage.icon_media_type.is_(None))
    ).all()
    for package in candidates:
        version = latest_published(session, package)
        if version is None:
            continue
        # ⚠️ Before the read, not after. This APK has already given up everything
        # it has; an app whose icon is a vector drawable can never satisfy the
        # `icon_media_type IS NULL` clause above, so without this check its base
        # APK is re-read in full at every boot, forever, to produce nothing.
        # Outlook is 172 MB and costs 1.4 s and 356 MB of heap per attempt.
        if package.icon_source_version_id == version.id:
            continue
        base = next((f for f in version.files if f.role is PartRole.BASE), None)
        if base is None:
            continue
        try:
            with storage.open(base.artifact_sha256) as handle:
                found = inspect_single_apk(handle.read())
        except (ArtifactNotFound, ApkError, OSError):
            continue

        # Recorded whatever the outcome — the point is that it was attempted.
        package.icon_source_version_id = version.id

        changed = False
        # ⚠️ The base APK alone. A *referenced* label now resolves through the
        # resource table, but an XAPK whose name lived only in the container's
        # manifest.json still cannot be recovered — that file is not kept after
        # ingest — so such a package keeps its package name until re-uploaded.
        if found.label and (not package.label or package.label == package.package_name):
            package.label = found.label
            changed = True
        if package.icon_media_type is None and found.icon is not None:
            _apply_icon(package, found)
            changed = True
        if changed:
            filled += 1

    session.flush()
    return filled


def backfill_plugin_api(session: Session, storage: ArtifactStorage) -> int:
    """Fill `plugin_api` on versions uploaded before it was recorded.

    Re-reads each base APK's manifest. A version whose artifact has gone is skipped
    rather than failing the run — this is a convenience pass, not a migration, and
    one missing blob should not stop the rest.
    """
    from app.artifacts.apk import ApkError, inspect_apk
    from app.artifacts.storage import ArtifactNotFound

    filled = 0
    for version in session.scalars(
        select(AppPackageVersion).where(AppPackageVersion.plugin_api.is_(None))
    ):
        base = next((f for f in version.files if f.role is PartRole.BASE), None)
        if base is None:
            continue
        try:
            with storage.open(base.artifact_sha256) as handle:
                info = inspect_apk(handle.read())
        except (ArtifactNotFound, ApkError, OSError):
            # A blob that has been deleted, or an archive that no longer parses.
            # This is a convenience pass, not a migration: one bad row must not
            # stop the rest.
            continue
        if info.plugin_api:
            version.plugin_api = info.plugin_api
            filled += 1
    session.flush()
    return filled


def backfill_abis(session: Session, storage: ArtifactStorage) -> int:
    """Fill `abis` on versions uploaded before anything read `lib/` (W96).

    ⚠️ **Reads every part, not just the base.** A split app often keeps all its
    native code in a split — the operator's Chrome bundle is exactly that — so a
    base-only pass would write "" and claim the whole app runs anywhere, which is
    the failure this column exists to prevent.

    ⚠️ **A version whose blobs are all unreadable is left NULL.** Writing "" there
    would turn "the file is gone" into "it installs on any device". Skipping a
    row costs nothing; the console keeps saying *not scanned*, which is true.
    """
    import io as _io
    import zipfile as _zipfile

    from app.artifacts.apk import native_abis
    from app.artifacts.storage import ArtifactNotFound

    filled = 0
    for version in session.scalars(
        select(AppPackageVersion).where(AppPackageVersion.abis.is_(None))
    ):
        found: set[str] = set()
        read_any = False
        for part in version.files:
            # An OBB is data, not code; it has no manifest and no lib/.
            if part.role is PartRole.OBB:
                continue
            try:
                with storage.open(part.artifact_sha256) as handle:
                    data = handle.read()
                with _zipfile.ZipFile(_io.BytesIO(data)) as archive:
                    found |= set(native_abis(data, archive))
                read_any = True
            except (ArtifactNotFound, _zipfile.BadZipFile, OSError):
                continue

        if read_any:
            version.abis = ",".join(sorted(found))
            filled += 1

    session.flush()
    return filled


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


def declared_activities(
    session: Session, storage: ArtifactStorage, package_name: str
) -> list[dict[str, object]]:
    """Every activity a package's published build declares, launchers first (W62).

    ⚠️ **Scans every part, not just the base.** Chrome's base APK declares three
    activities and none of them is its launcher — the rest live in its splits. A
    base-only scan would offer an operator a dropdown that silently omits the very
    screen they were looking for, which is worse than the text box it replaces.

    Returns `[{"name": ..., "launcher": bool}]`. Launchable activities sort first
    because a kiosk almost always wants the screen a user would normally arrive
    at; the rest follow, since some kiosk screens are deliberately not launchers.
    """
    from app.artifacts.apk import inspect_apk
    from app.artifacts.storage import ArtifactNotFound

    package = session.scalar(
        select(AppPackage).where(AppPackage.package_name == package_name)
    )
    version = latest_published(session, package) if package else None
    if version is None:
        return []

    names: dict[str, bool] = {}
    for part in version.files:
        if part.role is DbPartRole.OBB:
            continue  # not an APK; it has no manifest
        try:
            with storage.open(part.artifact_sha256) as handle:
                info = inspect_apk(handle.read())
        except (ArtifactNotFound, ApkError, OSError):
            continue
        for name in info.activities:
            names.setdefault(name, False)
        for name in info.launcher_activities:
            names[name] = True

    return sorted(
        ({"name": n, "launcher": is_launcher} for n, is_launcher in names.items()),
        key=lambda a: (not a["launcher"], a["name"]),
    )
