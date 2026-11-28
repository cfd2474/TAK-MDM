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

"""Which build Google Play served to which device model, and what a device gets (W519).

Operator: "when we download an app on play store, it grabs all variants based on
our models, then install the appropriate one based on the device that the policy
is attached to."

Google Play picks a build and its parts per device model: the screen density, the
CPU type, the languages, sometimes a different versionCode. W312 downloads as a
model; W517 proved on two models (SM-X520, SM-G736U) that one versionCode can
carry both models' parts, and that each installs. This module keeps the record
and answers the two questions a device's desired state needs:

- **Which parts of a build does this device get?** Only the ones Play served to
  its model, when that is recorded (`files_for`). Otherwise every part, which is
  what every device got before W519: a manual upload, a single-profile download,
  a model nobody downloaded as.
- **Which build does a pin mean for this device?** A pin names one build. When
  this device's model got a *different* build in the same fleet download, that
  sibling (`sibling`). Otherwise the pinned build, unchanged.

⚠️ **The record only narrows what a device is sent; it never widens it.** A
device is never sent a part Play did not serve to some model of the build, and
a fact that is not recorded falls back to today's behaviour.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Iterable
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AppPackage, AppPackageFile, AppPackageVersion, Device, ModelBuild, PlayDeviceProfile
from app.services import device_type, newest_build, play_profiles

logger = logging.getLogger(__name__)

_TRAILING_MODEL = re.compile(r"\(([^()]+)\)\s*$")


# --- the record --------------------------------------------------------------

def model_label(model: str | None) -> str:
    """How a Google Play download as this model is labeled (`downloaded_as`)."""
    return device_type.display_name(model) or (model or "")


def downloaded_for(version: AppPackageVersion, model: str | None) -> bool:
    """True when this build was downloaded from Google Play as `model`.

    `downloaded_as` holds the label of the profile it was fetched as: the model's
    display name ("Galaxy Tab S10 FE (SM-X520)"), or the bare model when the
    catalog does not know it. Both forms are matched, by the same model key the
    profiles use. A build from before W519 has no `ModelBuild` row, so this is
    how it is still found.
    """
    label = (version.downloaded_as or "").strip()
    key = play_profiles.model_key(model or "")
    if not label or not key:
        return False
    if label == model_label(model):
        return True
    found = _TRAILING_MODEL.search(label)
    candidate = found.group(1) if found else label
    return play_profiles.model_key(candidate) == key


def link(session: Session, model: str, version: AppPackageVersion, *,
         parts: Iterable[str] | None = None, fetch_id: uuid.UUID | None = None,
         now: datetime | None = None) -> ModelBuild:
    """Record that Google Play served `version` to `model`, with these parts.

    `parts` are the split names of that download (empty: the base alone). Given
    again for the same model and build, the newer download's answer replaces the
    older one. None leaves what is recorded.
    """
    key = play_profiles.model_key(model)
    row = session.get(ModelBuild, (key, version.id))
    if row is None:
        row = ModelBuild(model_key=key, version_id=version.id)
        session.add(row)
    if parts is not None:
        row.parts = json.dumps(sorted(set(parts)))
    if fetch_id is not None:
        row.fetch_id = fetch_id
        row.fetched_at = now or datetime.now(timezone.utc)
    session.flush()
    return row


def parts_of(row: ModelBuild | None) -> set[str] | None:
    """The split names recorded on `row`; None when not known."""
    if row is None or row.parts is None:
        return None
    try:
        names = json.loads(row.parts)
    except ValueError:
        return None
    return {str(n) for n in names} if isinstance(names, list) else None


def served(session: Session, version: AppPackageVersion, model: str | None) -> ModelBuild | None:
    """The record that Play served `version` to `model`, if there is one."""
    if not model:
        return None
    return session.get(ModelBuild, (play_profiles.model_key(model), version.id))


def builds_for_model(session: Session, model: str | None,
                     package: AppPackage | None) -> list[AppPackageVersion]:
    """The package's builds Google Play served to `model`, newest first."""
    if package is None or not model:
        return []
    linked = set(session.scalars(
        select(ModelBuild.version_id).where(ModelBuild.model_key == play_profiles.model_key(model))
    ))
    return sorted(
        (v for v in package.versions if v.id in linked or downloaded_for(v, model)),
        key=lambda v: v.version_code,
        reverse=True,
    )


def served_to(session: Session, version: AppPackageVersion) -> list[ModelBuild]:
    """Every model this build was recorded as served to, by model."""
    return list(session.scalars(
        select(ModelBuild).where(ModelBuild.version_id == version.id).order_by(ModelBuild.model_key)
    ))


# --- what a device gets ------------------------------------------------------

def files_for(session: Session, version: AppPackageVersion,
              device: Device | None) -> list[AppPackageFile]:
    """The parts of `version` this device is sent.

    The base, any OBB, and the splits Play served to the device's model, when
    they are recorded. Every part otherwise (see the module docstring).
    """
    files = list(version.files)
    wanted = parts_of(served(session, version, device.model if device else None))
    if wanted is None:
        return files
    return [f for f in files if f.role.value != "split" or (f.split_name or "") in wanted]


def sibling(session: Session, version: AppPackageVersion, device: Device | None) -> AppPackageVersion:
    """The build a pin on `version` means for this device.

    When the pinned build came from a fleet download and Play gave this device's
    model a different build in that same download, that build, if it runs on the
    device. Otherwise `version` itself.
    """
    model = device.model if device else None
    if not model or served(session, version, model) is not None:
        return version
    fetches = [r.fetch_id for r in served_to(session, version) if r.fetch_id is not None]
    if not fetches:
        return version
    key = play_profiles.model_key(model)
    candidates = session.scalars(
        select(AppPackageVersion)
        .join(ModelBuild, ModelBuild.version_id == AppPackageVersion.id)
        .where(ModelBuild.fetch_id.in_(fetches), ModelBuild.model_key == key,
               AppPackageVersion.package_id == version.package_id)
    ).all()
    runnable = sorted((v for v in candidates if newest_build.runs_on(v, device)),
                      key=lambda v: v.version_code, reverse=True)
    return runnable[0] if runnable else version


def newest_for_model(session: Session, package: AppPackage | None,
                     device: Device | None) -> AppPackageVersion | None:
    """The newest build Play served to this device's model that runs on it."""
    if device is None or package is None:
        return None
    for version in builds_for_model(session, device.model, package):
        if newest_build.runs_on(version, device):
            return version
    return None


def prefer_model(session: Session, version: AppPackageVersion | None,
                 device: Device | None) -> AppPackageVersion | None:
    """`version`, unless Play served it only to other models and served this
    device's model a build of its own: then the newest of those that runs here.

    For "Always the newest build": a build nobody downloaded as a model (an
    upload, a single-profile download) is never second-guessed.
    """
    if version is None or device is None or not device.model:
        return version
    rows = served_to(session, version)
    key = play_profiles.model_key(device.model)
    if not rows or any(r.model_key == key for r in rows):
        return version
    return newest_for_model(session, version.package, device) or version


# --- adding a download -------------------------------------------------------

def store(session: Session, storage, key: str, data: bytes, *, source: str | None = None,
          source_url: str | None = None, downloaded_as: str | None = None,
          fetch_id: uuid.UUID | None = None,
          now: datetime | None = None) -> tuple[AppPackageVersion, list[str]]:
    """Add a Google Play download as model `key` to the library, and record it.

    A new versionCode becomes a new build. One already in the library (another
    model got the same build) gets this model's missing splits added, but only if
    the base APK is byte-identical (`packages.add_missing_parts`). Either way the
    model is linked to the build with the parts this download had. Returns the
    build and the split names added to an existing one (empty for a new build).
    """
    from app.artifacts.bundles import inspect
    from app.services import packages as package_service

    bundle = inspect(data)
    parts = [p.info.split_name for p in bundle.parts
             if p.role.value == "split" and p.info is not None and p.info.split_name]
    package = session.scalar(select(AppPackage).where(AppPackage.package_name == bundle.package_name))
    existing = None
    if package is not None:
        existing = next((v for v in package.versions if v.version_code == bundle.version_code), None)
    added: list[str] = []
    if existing is not None:
        added = package_service.add_missing_parts(session, storage, existing, data)
        logger.info("%s %s already held; added splits %s for %s",
                    bundle.package_name, bundle.version_code, added, key)
        version = existing
    else:
        version = package_service.ingest(session, storage, data).version
        version.source = source
        version.source_url = source_url
        version.downloaded_as = (downloaded_as or "")[:128] or None
    model = session.scalar(select(PlayDeviceProfile.model).where(PlayDeviceProfile.model_key == key)) or key
    link(session, model, version, parts=parts, fetch_id=fetch_id, now=now)
    session.flush()
    return version, added
