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

"""Companion apps carried inside ATAK plugins (W407).

Some plugins ship the app they work with inside themselves: TAK Beacon carries
`assets/takbeacon.apk` and, when ATAK loads it, offers to install it. That
install runs as ATAK, so Android asks the user to confirm it, and only after
the user has let ATAK "install unknown apps" in Settings and only where no
policy blocks unknown sources. There is no delegation that lets ATAK install
silently. (Whether a kiosk also stops the confirmation was assumed and is not
verified: see the platform reference, W407.)

ATLAS can: it is the Device Owner. So each embedded APK becomes a library app
of its own, linked to the plugin build that carried it, and is delivered
beside the plugin. The plugin compares the installed versionCode with its own
copy and, finding it already there, never asks.

⚠️ **A companion never fails its plugin's upload.** A wrong signer, a damaged
APK, or a clash with a build already in the library skips the companion and
says why; the plugin is what the operator uploaded, and it goes in either way.
Every check runs **before** anything is written, so a skipped companion leaves
nothing behind in the session.

⚠️ **One level only.** A companion's own assets are not scanned: what this
reads is attacker-chosen content, and "an APK inside an APK inside an APK" has
no use worth the work it can cause. It follows from two rules here rather than
a flag: only a plugin is scanned, and a plugin found inside one is skipped.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artifacts.apk import ApkError
from app.artifacts.bundles import InspectedBundle, inspect_single_apk
from app.db.models import AppPackage, AppPackageCompanion, AppPackageVersion
from app.services import reserved_packages

#: Where a plugin keeps payloads. Other plugins nest deeper than TAK Beacon:
#: `ATAK-Plugin-uastool` carries `assets/apks/DJI/ATAKGo.apk`.
_ASSETS = "assets/"

#: Caps on what one plugin may make this read. An entry's declared size can
#: lie, so the read itself is bounded too (`_read_bounded`).
MAX_COMPANIONS = 8
MAX_COMPANION_BYTES = 512 * 1024 * 1024

ADDED = "added"
LINKED = "linked"
SKIPPED = "skipped"


@dataclass(frozen=True)
class CompanionOutcome:
    """What happened to one APK found inside a plugin."""

    asset_path: str
    #: "added" (new to the library), "linked" (already there, same build),
    #: or "skipped" (with `reason`).
    status: str
    package_name: str | None = None
    version_code: int | None = None
    version_name: str | None = None
    label: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class _Embedded:
    path: str
    data: bytes | None
    problem: str | None = None


def _read_bounded(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes | None:
    with archive.open(info) as handle:
        data = handle.read(MAX_COMPANION_BYTES + 1)
    return None if len(data) > MAX_COMPANION_BYTES else data


def embedded_apks(plugin_base: bytes) -> list[_Embedded]:
    """Every `assets/**/*.apk` in a plugin's base APK, read within the caps."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(plugin_base))
    except zipfile.BadZipFile:
        return []
    found: list[_Embedded] = []
    with archive:
        entries = sorted(
            (i for i in archive.infolist()
             if not i.is_dir()
             and i.filename.startswith(_ASSETS)
             and i.filename.lower().endswith(".apk")),
            key=lambda i: i.filename,
        )
        for info in entries:
            if len(found) >= MAX_COMPANIONS:
                found.append(_Embedded(info.filename, None,
                                       f"more than {MAX_COMPANIONS} embedded apps; the rest were not read"))
                break
            if info.file_size > MAX_COMPANION_BYTES:
                found.append(_Embedded(info.filename, None, "larger than ATLAS reads from inside a plugin"))
                continue
            try:
                data = _read_bounded(archive, info)
            except (zipfile.BadZipFile, OSError, RuntimeError, EOFError) as exc:
                found.append(_Embedded(info.filename, None, f"could not be read ({exc})"))
                continue
            if data is None:
                found.append(_Embedded(info.filename, None, "larger than ATLAS reads from inside a plugin"))
                continue
            found.append(_Embedded(info.filename, data))
    return found


def _base_sha(version: AppPackageVersion) -> str | None:
    return next((f.artifact_sha256 for f in version.files if f.role.value == "base"), None)


#: Admits a bundle to the library or raises `ValueError` saying why not
#: (`packages.validate`); injected so this module does not import the one
#: that calls it.
Admit = Callable[[Session, InspectedBundle], object]
#: Ingests bytes as a library app (`packages.ingest`).
Ingest = Callable[[bytes], AppPackageVersion]


def attach(
    session: Session,
    plugin_version: AppPackageVersion,
    plugin_package_name: str,
    plugin_base: bytes,
    *,
    admit: Admit,
    ingest: Ingest,
) -> tuple[CompanionOutcome, ...]:
    """Bring each companion inside a plugin build into the library and link it."""
    outcomes = []
    for embedded in embedded_apks(plugin_base):
        if embedded.problem is not None or embedded.data is None:
            outcomes.append(CompanionOutcome(embedded.path, SKIPPED, reason=embedded.problem))
            continue
        outcomes.append(
            _attach_one(session, plugin_version, plugin_package_name, embedded, admit, ingest)
        )
    return tuple(outcomes)


def _attach_one(
    session: Session,
    plugin_version: AppPackageVersion,
    plugin_package_name: str,
    embedded: _Embedded,
    admit: Admit,
    ingest: Ingest,
) -> CompanionOutcome:
    path, data = embedded.path, embedded.data
    assert data is not None
    try:
        bundle = inspect_single_apk(data)
    except (ApkError, ValueError) as exc:
        return CompanionOutcome(path, SKIPPED, reason=f"not a readable app ({exc})")

    def skipped(reason: str) -> CompanionOutcome:
        return CompanionOutcome(
            path, SKIPPED, bundle.package_name, bundle.version_code,
            bundle.version_name, bundle.label, reason,
        )

    if bundle.package_name == plugin_package_name:
        return skipped("it is the plugin itself")
    if bundle.plugin_api:
        return skipped("it is an ATAK plugin, not a companion app")
    if reserved_packages.is_reserved(bundle.package_name):
        return skipped("it is one of ATLAS's own apps")

    launchable = bool(bundle.base.info and bundle.base.info.launcher_activities)
    existing = session.scalar(
        select(AppPackageVersion)
        .join(AppPackage, AppPackage.id == AppPackageVersion.package_id)
        .where(
            AppPackage.package_name == bundle.package_name,
            AppPackageVersion.version_code == bundle.version_code,
        )
    )
    if existing is not None:
        if _base_sha(existing) != hashlib.sha256(data).hexdigest():
            return skipped(
                f"the library already has {bundle.package_name} build "
                f"{bundle.version_code} with different contents"
            )
        _link(session, plugin_version, existing, path, launchable)
        return CompanionOutcome(
            path, LINKED, bundle.package_name, bundle.version_code,
            bundle.version_name, existing.package.label or bundle.label,
        )

    try:
        admit(session, bundle)
    except ValueError as exc:
        return skipped(str(exc))
    version = ingest(data)
    _link(session, plugin_version, version, path, launchable)
    return CompanionOutcome(
        path, ADDED, bundle.package_name, bundle.version_code,
        bundle.version_name, version.package.label or bundle.label,
    )


def _link(
    session: Session,
    plugin_version: AppPackageVersion,
    companion_version: AppPackageVersion,
    path: str,
    launchable: bool,
) -> None:
    already = session.scalar(
        select(AppPackageCompanion).where(
            AppPackageCompanion.plugin_version_id == plugin_version.id,
            AppPackageCompanion.companion_version_id == companion_version.id,
        )
    )
    if already is None:
        session.add(
            AppPackageCompanion(
                plugin_version_id=plugin_version.id,
                companion_version_id=companion_version.id,
                asset_path=path,
                launchable=launchable,
            )
        )
        session.flush()


def companions_of(session: Session, plugin_version_id) -> list[AppPackageCompanion]:
    """The companion builds a plugin build carries, in asset order."""
    return list(
        session.scalars(
            select(AppPackageCompanion)
            .where(AppPackageCompanion.plugin_version_id == plugin_version_id)
            .order_by(AppPackageCompanion.asset_path)
        )
    )


def with_kiosk_tiles(values: dict, apps: list[dict]) -> dict:
    """Give each delivered companion app a tile on a multi-app kiosk.

    The plugin sends the user into its companion (TAK Beacon: "Approve the
    server in TAK Beacon"), and in a multi-app kiosk the tiles are the
    lock-task allowlist, so a companion without one could not open at all.

    * **Only on a multi-app kiosk**, and only a companion with a launch screen.
    * **Unplaced**: no page, row or column, so the launcher puts it in the
      first free cell, as it does an app installed from the ATLAS store.
    * **A tile the operator placed wins**, at the cell they chose.

    Returns new values; the input is not changed.
    """
    kiosk = values.get("KIOSK") or {}
    tiles = kiosk.get("multi_app_packages") or []
    if not tiles:
        return values
    placed = {tile.get("package_name") for tile in tiles if isinstance(tile, dict)}
    extra = [
        {"package_name": app["package_name"]}
        for app in apps
        if app.get("companion_of")
        and app.get("available")
        and app.get("launchable")
        and app["package_name"] not in placed
    ]
    if not extra:
        return values
    return {**values, "KIOSK": {**kiosk, "multi_app_packages": [*tiles, *extra]}}


# --------------------------------------------------------------------------- #
# Plugins already in the library, and what the console says
# --------------------------------------------------------------------------- #


def backfill(session: Session, storage) -> int:
    """Look for companions in plugin builds uploaded before W407.

    Reads each unscanned plugin build's base APK once and marks it scanned
    whatever it finds, so nothing is re-read at the next boot. A plugin is
    what `atak_compat.plugin_packages` says, which also covers a TAK.gov
    import whose manifest declares no `plugin-api` (ingest scans only by the
    manifest). Returns how many companion links it made.
    """
    from app.artifacts.storage import ArtifactNotFound
    from app.services import atak_compat, packages

    plugins = atak_compat.plugin_packages(session)
    if not plugins:
        return 0
    versions = list(
        session.scalars(
            select(AppPackageVersion)
            .join(AppPackage, AppPackage.id == AppPackageVersion.package_id)
            .where(
                AppPackage.package_name.in_(plugins),
                AppPackageVersion.companions_scanned.is_(False),
            )
        )
    )
    linked = 0
    for version in versions:
        # Marked first: a base APK that cannot be read now will not be readable
        # at the next boot either, and must not cost a read every time.
        version.companions_scanned = True
        sha = _base_sha(version)
        if sha is None:
            continue
        try:
            with storage.open(sha) as handle:
                base = handle.read()
        except (ArtifactNotFound, OSError):
            continue
        outcomes = attach(
            session, version, version.package.package_name, base,
            admit=packages.validate,
            ingest=lambda data: packages.ingest(session, storage, data).version,
        )
        linked += sum(1 for o in outcomes if o.status in (ADDED, LINKED))
    session.flush()
    return linked


@dataclass(frozen=True)
class LibraryView:
    """What the Apps library shows about companions."""

    #: Companion package name -> the plugins carrying it, by name.
    companion_of: dict
    #: Plugin build id -> the companions it carries, as "Name 1.4.5".
    carries: dict


def library_view(session: Session) -> LibraryView:
    companion_of: dict = {}
    carries: dict = {}
    for link in session.scalars(select(AppPackageCompanion)):
        plugin = link.plugin_version.package
        companion = link.companion_version
        companion_of.setdefault(companion.package.package_name, set()).add(
            plugin.label or plugin.package_name
        )
        name = companion.package.label or companion.package.package_name
        carries.setdefault(link.plugin_version_id, []).append(
            f"{name} {companion.version_name or companion.version_code}"
        )
    return LibraryView(
        {name: sorted(plugins) for name, plugins in companion_of.items()},
        {key: sorted(names) for key, names in carries.items()},
    )


def summary(outcomes) -> str:
    """What the upload did with the apps inside a plugin, for the console."""
    parts = []
    for o in outcomes:
        name = o.label or o.package_name or o.asset_path
        build = o.version_name or (str(o.version_code) if o.version_code else "")
        named = f"{name} {build}".strip()
        if o.status == ADDED:
            parts.append(f"Its companion app {named} was added to the library too, "
                         "and is installed with the plugin.")
        elif o.status == LINKED:
            parts.append(f"Its companion app {named} was already in the library, "
                         "and is installed with the plugin.")
        else:
            parts.append(f"The app inside it ({o.asset_path}) was not added: {o.reason}.")
    return " ".join(parts)
