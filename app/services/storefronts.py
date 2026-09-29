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

"""Storefronts — named versions of the ATLAS store a policy can assign (W140).

A storefront is a shelf: the apps a *user* may choose to install, as opposed to
the apps a policy installs for them. Each entry names a build, for the same
reason a required app does (W139) — nothing picks a version on an operator's
behalf any more, and a shelf is no exception.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AppPackageVersion, Storefront, StorefrontItem
from app.services import effective_policy as eff


class StorefrontError(Exception):
    """A storefront operation cannot be completed."""


def list_all(session: Session) -> list[Storefront]:
    return list(session.scalars(select(Storefront).order_by(Storefront.name)))


def get(session: Session, storefront_id: uuid.UUID) -> Storefront | None:
    return session.get(Storefront, storefront_id)


def create(
    session: Session, *, name: str, description: str | None = None
) -> Storefront:
    name = (name or "").strip()
    if not name:
        raise StorefrontError("a storefront needs a name")
    if session.scalar(select(Storefront).where(Storefront.name == name)) is not None:
        raise StorefrontError(f"a storefront named {name!r} already exists")

    storefront = Storefront(name=name, description=(description or "").strip() or None)
    session.add(storefront)
    session.flush()
    return storefront


def rename(
    session: Session,
    storefront: Storefront,
    *,
    name: str,
    description: str | None = None,
) -> Storefront:
    name = (name or "").strip()
    if not name:
        raise StorefrontError("a storefront needs a name")
    clash = session.scalar(select(Storefront).where(Storefront.name == name))
    if clash is not None and clash.id != storefront.id:
        raise StorefrontError(f"a storefront named {name!r} already exists")

    storefront.name = name
    storefront.description = (description or "").strip() or None
    session.flush()
    return storefront


def delete(session: Session, storefront: Storefront) -> None:
    """Destroy a storefront and its shelf.

    ⚠️ **Deliberately no "is it assigned?" gate**, unlike a policy or a device.
    A policy naming a storefront that has gone resolves to an empty shelf and
    says so — the device loses an offer, not a configuration, and nothing it has
    already installed is touched. Blocking the delete would mean hunting through
    policies to retire a shelf nobody wants.
    """
    session.delete(storefront)
    _tell_the_fleet(session)
    session.flush()


def set_items(
    session: Session, storefront: Storefront, version_ids: list[uuid.UUID]
) -> Storefront:
    """Replace the shelf with these builds, in the order given.

    ⚠️ **One entry per package.** Android installs one build of a package, so
    two entries for the same app are not a choice between builds — they are the
    same slot filled twice, which is what `AppCatalogSpec` rejects for required
    apps for the same reason. Refused rather than silently de-duplicated: the
    operator picked two things and needs to know only one can stand.
    """
    found = {
        v.id: v
        for v in session.scalars(
            select(AppPackageVersion).where(AppPackageVersion.id.in_(version_ids))
        )
    }
    missing = [str(v) for v in version_ids if v not in found]
    if missing:
        raise StorefrontError(f"unknown builds: {', '.join(missing)}")

    seen: dict[uuid.UUID, uuid.UUID] = {}
    for version_id in version_ids:
        package_id = found[version_id].package_id
        if package_id in seen and seen[package_id] != version_id:
            name = found[version_id].package.package_name
            raise StorefrontError(
                f"{name} appears twice on this storefront, at different builds. "
                "A device can install only one build of an app, so the second "
                "entry could not take effect — pick the one you want offered."
            )
        seen[package_id] = version_id

    storefront.items = [
        StorefrontItem(
            package_id=found[version_id].package_id,
            version_id=version_id,
            position=position,
        )
        for position, version_id in enumerate(dict.fromkeys(version_ids))
    ]
    _tell_the_fleet(session)
    session.flush()
    return storefront


def _tell_the_fleet(session: Session) -> None:
    """Recompute every device, because editing a shelf is not a policy edit.

    ⚠️ **The trap the server-wide store had, inherited whole.** No policy row
    changes when a storefront's items do, so nothing else recomputes anybody:
    the shelf changes in the console and the fleet is never told. The boolean
    this replaced invalidated from its route for exactly this reason, and there
    is a test that catches its absence through the cache-aware path rather than
    through `refresh`, which would pass either way.

    ⚠️ **In the service rather than the route**, which is the opposite of this
    codebase's usual split. Invalidation here is not a view concern a caller may
    reasonably skip — it is part of what "the shelf changed" means, and a second
    caller that forgot it would leave a fleet serving a stale shelf with nothing
    to see in the console.

    Fleet-wide rather than only the devices whose policies name this storefront:
    working that out means resolving every policy's merged value, which is what
    the recompute does anyway.
    """
    eff.invalidate_all(session)
