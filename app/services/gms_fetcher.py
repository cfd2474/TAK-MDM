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

"""The job behind "Keep Google Play services updated by ATLAS" (W517).

Once a day per device model, for every model with a device whose policy has the
switch on:

1. ask Google Play which Play services build it serves **as that model** (the
   W312 profile the model's own devices reported);
2. when that is newer than the newest build the library holds for the model,
   download it as the model and add it to the library (all its parts);
3. keep the newest `KEEP` builds per model and delete older ones no policy
   pins.

`gms_updates.choose` then gives each device its own model's build. Every step
writes the model's `GmsUpdateStatus` row, which is what the console shows.

⚠️ **One model at a time, in one thread.** A build is ~220 MB; two at once would
only compete for the same link. A failure is recorded on that model's row and
the others still run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AppPackage,
    AppPackageVersion,
    Device,
    EnrollmentState,
    GmsUpdateStatus,
    PlayDeviceProfile,
    Policy,
)
from app.services import build_compat, gms_updates, play_profiles

logger = logging.getLogger(__name__)

#: Operator decision 1: once a day.
INTERVAL = timedelta(days=1)
#: Operator decision 2: the current build and the one before it.
KEEP = 2

WAITING_FOR_PROFILE = (
    "Waiting: no device of this model has reported how Google Play sees it yet. "
    "It does at its next check-in."
)


@dataclass(frozen=True)
class PlayOffer:
    version_code: int
    version_name: str = ""


@dataclass(frozen=True)
class Fetchers:
    """How the job reaches Google Play. Tests pass ones that never leave the box."""

    #: `(session, model_key)` → what Play serves as that model.
    lookup: Callable[[Session, str], PlayOffer]
    #: `(session, model_key)` → the build, downloaded as that model and imported.
    download: Callable[[Session, str], AppPackageVersion]


def models_in_scope(session: Session) -> dict[str, str]:
    """`{model_key: model}` for every enrolled device with the switch on."""
    from app.services import effective_policy as eff

    found: dict[str, str] = {}
    devices = session.scalars(
        select(Device).where(Device.enrollment_state == EnrollmentState.ENROLLED)
    )
    for device in devices:
        if not device.model:
            continue
        key = play_profiles.model_key(device.model)
        if key in found:
            continue
        values = eff.compute(session, device).values
        if (values.get("APP_CATALOG") or {}).get("gms_managed"):
            found[key] = device.model
    return found


def library_builds(session: Session, model: str) -> list[AppPackageVersion]:
    """The library's Play services builds served to `model`, newest first."""
    return gms_updates.builds_for_model(session, model)


def _status(session: Session, key: str) -> GmsUpdateStatus:
    row = session.get(GmsUpdateStatus, key)
    if row is None:
        row = GmsUpdateStatus(model_key=key)
        session.add(row)
    return row


def check_due(session: Session, storage, fetchers: Fetchers, now: datetime | None = None) -> list[str]:
    """Check every model in scope whose last check is `INTERVAL` old. Returns
    the models a new build was imported for."""
    now = now or datetime.now(timezone.utc)
    imported = []
    for key, model in models_in_scope(session).items():
        row = session.get(GmsUpdateStatus, key)
        if row is not None and row.checked_at is not None and now - row.checked_at < INTERVAL:
            continue
        if check_model(session, storage, key, model, fetchers, now):
            imported.append(model)
        session.commit()
    if imported:
        from app.services import effective_policy as eff

        eff.invalidate_all(session)
        session.commit()
    return imported


def check_model(session: Session, storage, key: str, model: str, fetchers: Fetchers,
                now: datetime) -> bool:
    """One model's check. True when a new build was imported."""
    row = _status(session, key)
    row.checked_at = now
    row.error = None
    if session.scalar(select(PlayDeviceProfile).where(PlayDeviceProfile.model_key == key)) is None:
        row.error = WAITING_FOR_PROFILE
        return False
    try:
        offer = fetchers.lookup(session, key)
    except Exception as exc:  # a Play failure is this model's, not the job's
        row.error = f"Google Play could not be asked: {str(exc)[:300]}"
        logger.warning("gms check for %s: lookup failed", key, exc_info=True)
        return False
    row.play_version_code = offer.version_code
    row.play_version_name = offer.version_name or None

    held = library_builds(session, model)
    newest = held[0].version_code if held else 0
    imported = False
    if offer.version_code > newest:
        try:
            version = fetchers.download(session, key)
        except Exception as exc:
            session.rollback()
            row = _status(session, key)
            row.checked_at, row.play_version_code = now, offer.version_code
            row.play_version_name = offer.version_name or None
            row.error = f"The download failed: {str(exc)[:300]}"
            logger.warning("gms check for %s: download failed", key, exc_info=True)
            return False
        problem = _refuse(session, version, model)
        if problem:
            row.error = problem
            logger.warning("gms check for %s: %s", key, problem)
            return False
        row.imported_version_code = version.version_code
        row.imported_at = now
        imported = True
        logger.info("gms: imported %s for %s", version.version_code, model)
    prune(session, storage, model)
    return imported


def _refuse(session: Session, version: AppPackageVersion, model: str) -> str | None:
    """Why a fresh download must not be offered, or None."""
    signer = (version.package.signature_sha256 or "").lower() if version.package else ""
    if signer != gms_updates.GMS_SIGNER:
        return "The download is not signed by Google's Play services key; it is not offered."
    if version not in gms_updates.builds_for_model(session, model):
        return f"The download is not recorded as served to {model}; it is not offered."
    return None


def prune(session: Session, storage, model: str) -> list[int]:
    """Delete this model's builds beyond the newest `KEEP` that no policy pins."""
    from app.services import packages as package_service

    pinned = set()
    for policy in session.scalars(select(Policy)):
        if policy.latest_version is not None:
            pinned |= build_compat.pinned_builds(policy.latest_version.spec)
    removed = []
    for version in library_builds(session, model)[KEEP:]:
        hashes = {f.artifact_sha256 for f in version.files}
        if hashes & pinned:
            continue
        code = version.version_code
        package_service.delete_version(session, storage, version)
        removed.append(code)
    if removed:
        logger.info("gms: pruned %s for %s", removed, model)
    return removed


def store(session: Session, storage, key: str, data: bytes, *, source: str | None = None,
          source_url: str | None = None, downloaded_as: str | None = None) -> AppPackageVersion:
    """Add a download for model `key` to the library, and link it to the model.

    A new versionCode becomes a new build. One already in the library (another
    model got the same build) gets this model's missing splits added, but only
    if the base APK is byte-identical (`packages.add_missing_parts`).
    """
    from app.artifacts.bundles import inspect
    from app.services import packages as package_service

    bundle = inspect(data)
    package = session.scalar(select(AppPackage).where(AppPackage.package_name == bundle.package_name))
    existing = None
    if package is not None:
        existing = next((v for v in package.versions if v.version_code == bundle.version_code), None)
    if existing is not None:
        added = package_service.add_missing_parts(session, storage, existing, data)
        logger.info("gms: %s already held; added splits %s for %s", bundle.version_code, added, key)
        version = existing
    else:
        version = package_service.ingest(session, storage, data).version
        version.source = source
        version.source_url = source_url
        version.downloaded_as = (downloaded_as or "")[:128] or None
    model = session.scalar(select(PlayDeviceProfile.model).where(PlayDeviceProfile.model_key == key)) or key
    gms_updates.link(session, model, version)
    session.flush()
    return version


def default_fetchers(vault, storage) -> Fetchers:
    """The real Google Play, through the linked account and W312's profiles."""

    def lookup(session: Session, key: str) -> PlayOffer:
        from app.services import play_versions

        answer = play_versions.lookup(session, vault, f"{play_profiles.FLEET_PREFIX}{key}",
                                      [gms_updates.GMS_PACKAGE])
        offer = answer.offers.get(gms_updates.GMS_PACKAGE)
        if answer.failed or offer is None or offer.build is None:
            raise RuntimeError(answer.note or "Google Play gave no build for it")
        return PlayOffer(offer.build.version_code, offer.build.version_name or "")

    def download(session: Session, key: str) -> AppPackageVersion:
        from pathlib import Path
        import tempfile

        from app.services import google_play_link
        from app.services.app_sources import repos

        linked = google_play_link.credentials(session, vault)
        if linked is None:
            raise RuntimeError("no Google Play account is linked (Admin › Google Play)")
        chosen = play_profiles.resolve(session, f"{play_profiles.FLEET_PREFIX}{key}")
        if chosen is None:
            raise RuntimeError(WAITING_FOR_PROFILE)
        email, token, _stored = linked
        with tempfile.TemporaryDirectory() as cache:
            source = repos.build("google-play", Path(cache), play=(email, token, chosen.device),
                                 play_properties=chosen.properties_ini, play_label=chosen.label)
            wanted = source.versions(gms_updates.GMS_PACKAGE)[0]
            downloaded = source.download(wanted)
        return store(session, storage, key, downloaded.data, source=source.name,
                     source_url=downloaded.source_url, downloaded_as=downloaded.downloaded_as)

    return Fetchers(lookup=lookup, download=download)


@dataclass(frozen=True)
class StatusRow:
    """One model's line in Admin › Google Play › Google Play services updates."""

    model_key: str
    label: str
    checked_at: datetime | None
    play_version: str | None
    library_version_code: int | None
    imported_at: datetime | None
    error: str | None


def status_rows(session: Session) -> list[StatusRow]:
    """What the job last found, one row per model it has checked."""
    from app.services import device_type

    rows = []
    for row in session.scalars(select(GmsUpdateStatus).order_by(GmsUpdateStatus.model_key)):
        model = session.scalar(
            select(PlayDeviceProfile.model).where(PlayDeviceProfile.model_key == row.model_key)
        ) or row.model_key
        held = library_builds(session, model)
        play = None
        if row.play_version_code:
            play = f"{row.play_version_name or ''} ({row.play_version_code})".strip()
        rows.append(StatusRow(
            model_key=row.model_key,
            label=device_type.display_name(model) or model,
            checked_at=row.checked_at,
            play_version=play,
            library_version_code=held[0].version_code if held else None,
            imported_at=row.imported_at,
            error=row.error,
        ))
    return rows
