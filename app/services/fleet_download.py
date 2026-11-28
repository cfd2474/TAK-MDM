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

"""Download a Google Play app for every model in the fleet (W519).

Operator: "when we download an app on play store, it grabs all variants based on
our models", and an **Update All Play Apps** button that "will query all the
library apps acquired from the google play store and get updates for all device
models".

**The fleet** is every model with a captured Google Play profile (W312) and at
least one enrolled device. Play serves each its current build, so a fleet
download is that build for each model, stored by `model_builds.store`: the same
versionCode becomes one build with every model's parts, a different one its own
build. All builds of one app from one run share a fetch id, which is how a pin on
one of them finds the others (`model_builds.sibling`).

⚠️ **One model at a time, with a pause between downloads.** A Play build can be
hundreds of MB, and many requests in a row from one account is the pattern most
likely to be flagged (assumption, not observed). A model's failure is that
model's: it is reported, and the others still run.

⚠️ **A download reaches no device by itself.** A pin still names its build (and
a same-version download only adds parts to it). Devices whose policy says
"Always the newest build" get a newer build, which is what that setting means.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AppPackage, AppPackageVersion, Device, EnrollmentState, PlayDeviceProfile
from app.services import model_builds, play_profiles

logger = logging.getLogger(__name__)

#: The Apps page's profile choice meaning "every model in the fleet".
ALL_MODELS = f"{play_profiles.FLEET_PREFIX}*"
#: Seconds between two downloads from Google Play.
PAUSE_SECONDS = 3.0
#: The source name Google Play builds carry (`AppPackageVersion.source`).
PLAY_SOURCE = "google-play"
#: Packages per Play lookup (`play_versions.MAX_PACKAGES`).
LOOKUP_BATCH = 50

#: `(session, model_key, package_name)` → the APK/XAPK bytes Play serves that model.
Download = Callable[[Session, str, str], tuple[bytes, str | None, str | None]]
#: `(session, model_key, package_names)` → `{package_name: versionCode}` Play serves it.
Lookup = Callable[[Session, str, list[str]], dict[str, int]]


@dataclass(frozen=True)
class Play:
    """How the downloads reach Google Play. Tests pass ones that never leave the box."""

    download: Download
    lookup: Lookup | None = None


@dataclass
class ModelResult:
    """What one model got in one run."""

    model_key: str
    label: str
    version_code: int | None = None
    version_name: str | None = None
    new_build: bool = False
    added: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def line(self) -> str:
        if self.error:
            return f"{self.label}: failed. {self.error}"
        version = f"{self.version_name or ''} ({self.version_code})".strip()
        if self.new_build:
            return f"{self.label}: {version}, new build"
        if self.added:
            return f"{self.label}: {version}, its parts added ({', '.join(self.added)})"
        return f"{self.label}: {version}, already held"


@dataclass
class AppResult:
    """One app in an Update All run."""

    package_name: str
    label: str
    models: list[ModelResult] = field(default_factory=list)
    #: Why nothing was downloaded, when nothing was ("up to date for every model").
    note: str | None = None

    @property
    def imported(self) -> bool:
        return any(m.ok and (m.new_build or m.added) for m in self.models)


# --- scope -------------------------------------------------------------------

def fleet_models(session: Session) -> dict[str, str]:
    """`{model_key: model}`: captured profiles with at least one enrolled device."""
    enrolled = {
        play_profiles.model_key(m)
        for m in session.scalars(
            select(Device.model).where(Device.enrollment_state == EnrollmentState.ENROLLED)
        )
        if m
    }
    return {
        row.model_key: row.model
        for row in session.scalars(select(PlayDeviceProfile).order_by(PlayDeviceProfile.model_key))
        if row.model_key in enrolled
    }


def play_packages(session: Session) -> list[AppPackage]:
    """Library apps with at least one build downloaded from Google Play."""
    ids = set(session.scalars(
        select(AppPackageVersion.package_id).where(AppPackageVersion.source == PLAY_SOURCE)
    ))
    if not ids:
        return []
    return list(session.scalars(
        select(AppPackage).where(AppPackage.id.in_(ids)).order_by(AppPackage.package_name)
    ))


def needs_download(session: Session, package: AppPackage | None, model: str, offered: int) -> bool:
    """True when Play's build for `model` is newer than what the library holds for
    it, or is a build the library holds without this model's parts."""
    if package is None:
        return True
    held = model_builds.builds_for_model(session, model, package)
    if held and offered < held[0].version_code:
        return False  # Play serves an older build than the model already has
    same = next((v for v in package.versions if v.version_code == offered), None)
    if same is None:
        return True
    return model_builds.served(session, same, model) is None and not model_builds.downloaded_for(same, model)


# --- one app, every model ----------------------------------------------------

def fetch_app(session: Session, storage, package_name: str, play: Play, *,
              models: dict[str, str] | None = None, fetch_id: uuid.UUID | None = None,
              now: datetime | None = None, pause: float = PAUSE_SECONDS,
              on_step: Callable[[str], None] | None = None) -> list[ModelResult]:
    """Download `package_name` as every model and add each to the library.

    Commits after each model, so one model's failure keeps the others' builds.
    """
    models = fleet_models(session) if models is None else models
    fetch_id = fetch_id or uuid.uuid4()
    now = now or datetime.now(timezone.utc)
    results: list[ModelResult] = []
    for index, (key, model) in enumerate(models.items()):
        if index and pause:
            time.sleep(pause)
        result = ModelResult(model_key=key, label=model_builds.model_label(model))
        try:
            data, source_url, downloaded_as = play.download(session, key, package_name)
            existed = _held_codes(session, package_name)
            version, added = model_builds.store(
                session, storage, key, data, source=PLAY_SOURCE, source_url=source_url,
                downloaded_as=downloaded_as, fetch_id=fetch_id, now=now,
            )
            if version.package.package_name != package_name:
                raise ValueError(f"Google Play sent {version.package.package_name}, not {package_name}")
            result.version_code, result.version_name = version.version_code, version.version_name
            result.new_build = version.version_code not in existed
            result.added = added
            session.commit()
        except Exception as exc:  # noqa: BLE001 - a model's failure is that model's
            session.rollback()
            result.error = (str(exc) or exc.__class__.__name__)[:400]
            logger.warning("fleet download of %s as %s failed: %s", package_name, key, result.error)
        results.append(result)
        if on_step is not None:
            on_step(f"{package_name}: {result.line()}")
    return results


def _held_codes(session: Session, package_name: str) -> set[int]:
    return set(session.scalars(
        select(AppPackageVersion.version_code).join(AppPackage)
        .where(AppPackage.package_name == package_name)
    ))


# --- Update All Play Apps ----------------------------------------------------

def update_all(session: Session, storage, play: Play, *, now: datetime | None = None,
               pause: float = PAUSE_SECONDS,
               on_step: Callable[[str], None] | None = None) -> list[AppResult]:
    """Bring every Google Play app in the library up to date for every model.

    One Play lookup per model for all the apps (batched), then a download as each
    model whose offer is newer than the library holds for it, or is a held build
    without its parts.
    """
    if play.lookup is None:
        raise ValueError("no Play lookup")
    now = now or datetime.now(timezone.utc)
    packages = play_packages(session)
    models = fleet_models(session)
    results = {p.package_name: AppResult(p.package_name, p.label or p.package_name) for p in packages}
    if not packages:
        return []
    if not models:
        for r in results.values():
            r.note = "no device model has reported how Google Play sees it yet"
        return list(results.values())
    plan: dict[str, dict[str, str]] = {}
    names = [p.package_name for p in packages]
    by_name = {p.package_name: p for p in packages}
    for key, model in models.items():
        offers: dict[str, int] = {}
        try:
            for start in range(0, len(names), LOOKUP_BATCH):
                offers.update(play.lookup(session, key, names[start:start + LOOKUP_BATCH]))
        except Exception as exc:  # noqa: BLE001
            message = f"Google Play could not be asked: {str(exc)[:300]}"
            for name in names:
                results[name].models.append(ModelResult(key, model_builds.model_label(model), error=message))
            if on_step is not None:
                on_step(f"{model_builds.model_label(model)}: {message}")
            continue
        for name in names:
            offered = offers.get(name)
            if offered and needs_download(session, by_name[name], model, offered):
                plan.setdefault(name, {})[key] = model
    for name in names:
        if name not in plan:
            if not results[name].models:
                results[name].note = "up to date for every model"
            continue
        if on_step is not None:
            on_step(f"{name}: downloading for {len(plan[name])} model(s)")
        results[name].models.extend(
            fetch_app(session, storage, name, play, models=plan[name], now=now, pause=pause, on_step=on_step)
        )
        if pause:
            time.sleep(pause)
    return list(results.values())


# --- the real Google Play ----------------------------------------------------

def play_download(session: Session, vault, key: str, package_name: str) -> tuple[bytes, str | None, str | None]:
    """Download `package_name` from Google Play as model `key` (its W312 profile)."""
    import tempfile
    from pathlib import Path

    from app.services import google_play_link
    from app.services.app_sources import repos

    linked = google_play_link.credentials(session, vault)
    if linked is None:
        raise RuntimeError("no Google Play account is linked (Admin › Google Play)")
    chosen = play_profiles.resolve(session, f"{play_profiles.FLEET_PREFIX}{key}")
    if chosen is None:
        raise RuntimeError("no device of this model has reported how Google Play sees it yet")
    email, token, _stored = linked
    with tempfile.TemporaryDirectory() as cache:
        source = repos.build(PLAY_SOURCE, Path(cache), play=(email, token, chosen.device),
                             play_properties=chosen.properties_ini, play_label=chosen.label)
        wanted = source.versions(package_name)[0]
        downloaded = source.download(wanted)
    return downloaded.data, downloaded.source_url, downloaded.downloaded_as


def play_lookup(session: Session, vault, key: str, names: Iterable[str]) -> dict[str, int]:
    """`{package: versionCode}` Google Play serves model `key`."""
    from app.services import play_versions

    answer = play_versions.lookup(session, vault, f"{play_profiles.FLEET_PREFIX}{key}", list(names))
    if answer.failed or (answer.note and not answer.offers):
        raise RuntimeError(answer.note or "Google Play gave no answer")
    return {
        name: offer.build.version_code
        for name, offer in answer.offers.items()
        if offer is not None and offer.build is not None and offer.build.version_code
    }


def default_play(vault) -> Play:
    """The real Google Play, through the linked account."""
    return Play(
        download=lambda session, key, name: play_download(session, vault, key, name),
        lookup=lambda session, key, names: play_lookup(session, vault, key, names),
    )
