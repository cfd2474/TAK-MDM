"""Web shortcuts: links the console turns into apps (W336).

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

Operator: *"can we have a process on the portal that allows the user to enter the
desired shortcut link and an icon, and the portal background process can build
and sign an app that creates that as a clickable 'app' shortcut"*.

A shortcut is built by `app.artifacts.shortcut_builder` and then **ingested into
the Library like any upload**, so everything downstream (policies, app groups,
the device's install path) is the existing one.

⚠️ **Saving deploys nothing** (W139). An edit builds a new version into the
Library; a policy that names the old build keeps it until someone chooses the
new one. :func:`policies_using` lists them so the page can say so.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artifacts import shortcut_builder as builder
from app.artifacts.storage import ArtifactStorage
from app.db.models import AppPackage, Policy, WebShortcut
from app.services import packages as package_service


class ShortcutError(ValueError):
    """A shortcut that cannot be saved, in a sentence for the operator."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def list_all(session: Session) -> list[WebShortcut]:
    return sorted(session.scalars(select(WebShortcut)),
                  key=lambda s: (s.label.casefold(), s.package_name))


def get(session: Session, shortcut_id: uuid.UUID) -> WebShortcut | None:
    return session.get(WebShortcut, shortcut_id)


def library_package(session: Session, shortcut: WebShortcut) -> AppPackage | None:
    return session.scalar(select(AppPackage).where(AppPackage.package_name == shortcut.package_name))


def create(
    session: Session,
    storage: ArtifactStorage,
    key_dir: Path,
    *,
    label: str,
    url: str,
    icon_png: bytes,
    created_by: str | None = None,
) -> WebShortcut:
    """Build version 1 and add it to the Library."""
    if not icon_png:
        raise ShortcutError("choose an icon image")
    shortcut = WebShortcut(
        package_name=builder.new_package_name(),
        label=label.strip(),
        url=url.strip(),
        icon_png=icon_png,
        version_code=1,
        created_by=created_by,
    )
    _build_and_ingest(session, storage, key_dir, shortcut)
    session.add(shortcut)
    session.flush()
    return shortcut


def update(
    session: Session,
    storage: ArtifactStorage,
    key_dir: Path,
    shortcut: WebShortcut,
    *,
    label: str,
    url: str,
    icon_png: bytes | None = None,
) -> WebShortcut:
    """Build the next version with the new name, address or icon.

    The package name never changes: that is what lets devices update in place.
    An edit that changes nothing builds nothing.
    """
    label, url = label.strip(), url.strip()
    icon = icon_png or shortcut.icon_png
    if (label, url, icon) == (shortcut.label, shortcut.url, shortcut.icon_png):
        return shortcut
    candidate = WebShortcut(
        package_name=shortcut.package_name, label=label, url=url, icon_png=icon,
        version_code=shortcut.version_code + 1,
    )
    _build_and_ingest(session, storage, key_dir, candidate)
    shortcut.label, shortcut.url, shortcut.icon_png = label, url, icon
    shortcut.version_code = candidate.version_code
    shortcut.updated_at = _now()
    session.flush()
    return shortcut


def delete(session: Session, storage: ArtifactStorage, shortcut: WebShortcut) -> None:
    """Remove the shortcut and its app from the Library.

    ⚠️ **Refused while a policy names it.** Removing the app under a policy that
    still requires it leaves the policy asking for something the Library cannot
    supply; the operator takes it out of those policies first.
    """
    using = policies_using(session, shortcut.package_name)
    if using:
        names = ", ".join(u.name for u in using)
        raise ShortcutError(f"remove {shortcut.label} from these policies first: {names}")
    package = library_package(session, shortcut)
    if package is not None:
        package_service.delete_package(session, storage, package)
    session.delete(shortcut)
    session.flush()


@dataclass(frozen=True)
class PolicyUse:
    policy_id: uuid.UUID
    #: Where an operator edits it: the profile when it is one (W21).
    href: str
    name: str
    #: True when it names a build other than the newest.
    outdated: bool


def policies_using(session: Session, package_name: str) -> list[PolicyUse]:
    """Current policies whose Required apps name this package."""
    newest = _newest_build_sha(session, package_name)
    uses: list[PolicyUse] = []
    for policy in session.scalars(
        select(Policy).where(Policy.archived_at.is_(None), Policy.is_template.is_(False))
    ):
        latest = policy.latest_version
        required = ((latest.spec if latest else None) or {}).get("required_apps") or []
        entries = [e for e in required if e.get("package_name") == package_name]
        if not entries:
            continue
        pinned = {e.get("artifact_sha256") for e in entries}
        outdated = bool(pinned - {None, newest})
        if policy.profile_id is not None and policy.profile is not None:
            uses.append(PolicyUse(policy.id, f"/profiles/{policy.profile_id}", policy.profile.name, outdated))
        else:
            uses.append(PolicyUse(policy.id, f"/policies/{policy.id}", policy.name, outdated))
    return sorted(uses, key=lambda u: u.name.casefold())


def _newest_build_sha(session: Session, package_name: str) -> str | None:
    """The newest build's base APK, **only to say a policy is behind it**.

    ⚠️ Not `packages.newest_base_sha`, whose docstring keeps it to the launcher
    because choosing a build for an operator is what W139 removed. Nothing here
    chooses: the answer only decides whether the page says "outdated".
    """
    package = session.scalar(select(AppPackage).where(AppPackage.package_name == package_name))
    version = package.latest_version if package is not None else None
    if version is None:
        return None
    base = [f for f in version.files if f.role.value == "base"]
    return base[0].artifact_sha256 if base else None


def _build_and_ingest(
    session: Session, storage: ArtifactStorage, key_dir: Path, shortcut: WebShortcut
) -> None:
    spec = builder.ShortcutSpec(
        package_name=shortcut.package_name,
        label=shortcut.label,
        url=shortcut.url,
        version_code=shortcut.version_code,
        version_name=str(shortcut.version_code),
        icon_png=shortcut.icon_png,
    )
    try:
        apk = builder.build(spec, builder.load_or_create_key(key_dir))
        package_service.ingest(session, storage, apk, label=shortcut.label)
    except (builder.ShortcutBuildError, package_service.PackageError) as exc:
        raise ShortcutError(str(exc)) from exc
