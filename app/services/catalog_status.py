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

"""What the library already holds of a catalog row's plugin (W281).

Operator: how does the catalog handle "a newer version of a previously
imported app"? It did not notice: a row said *imported* for the exact build
and nothing otherwise, so an upgrade looked like a plugin never seen. One rule
here, used by both the TAK.gov and the TAKWERX tabs.

⚠️ **It informs; it never acts.** No import, no policy change: a device
installs the build its policy names (W139), so an upgrade is still an import
and then a policy edit, both by the operator.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AppPackage, AppPackageVersion
from app.services import atak_compat
from app.services.app_sources.takwerx import display_version_of

IMPORTED = "imported"
UPDATE = "update"
NEWER = "newer"


@dataclass(frozen=True)
class Held:
    """One build of the package already in the library."""

    version_code: int
    version_name: str
    #: The ATAK line it was built for ("5.7.0"), from its `plugin-api`; None
    #: when the build declares none or was never scanned.
    atak_line: str | None


@dataclass(frozen=True)
class RowStatus:
    kind: str
    #: The build the pill names: the exact one, the highest above, or the
    #: highest below.
    held: Held
    #: The ATAK line of `held` when it differs from the one being viewed --
    #: "you have 0.7" means less if that 0.7 is for another ATAK.
    other_atak: str | None = None


def library_builds(session: Session, package_names) -> dict[str, list[Held]]:
    """Every held build of each named package, highest versionCode first."""
    wanted = {name for name in package_names if name}
    if not wanted:
        return {}
    rows = session.execute(
        select(
            AppPackage.package_name,
            AppPackageVersion.version_code,
            AppPackageVersion.version_name,
            AppPackageVersion.plugin_api,
        )
        .join(AppPackageVersion, AppPackageVersion.package_id == AppPackage.id)
        .where(AppPackage.package_name.in_(wanted))
    )
    out: dict[str, list[Held]] = {}
    for name, code, version_name, plugin_api in rows:
        out.setdefault(name, []).append(
            Held(
                version_code=code,
                version_name=display_version_of(version_name) or str(code),
                atak_line=atak_compat.plugin_target(plugin_api),
            )
        )
    for builds in out.values():
        builds.sort(key=lambda h: h.version_code, reverse=True)
    return out


def atak_line_of(value: str | None) -> str | None:
    """"5.8.0.CIV" or "5.8.0" -> "5.8.0": how both tabs name the ATAK viewed."""
    return atak_compat.atak_line(value)


def status_for(
    held: list[Held], version_code: int | None, viewing_atak: str | None = None
) -> RowStatus | None:
    """The pill for one catalog row, or None when the library holds nothing.

    Exact beats newer beats update. ⚠️ A higher build held wins over a lower
    one: offering "update · you have 0.6" while 0.9 sits in the library would
    invite a downgrade presented as an upgrade.
    """
    if not held or version_code is None:
        return None
    exact = next((h for h in held if h.version_code == version_code), None)
    if exact is not None:
        return RowStatus(IMPORTED, exact)
    above = [h for h in held if h.version_code > version_code]
    cited, kind = (above[0], NEWER) if above else (held[0], UPDATE)
    other = cited.atak_line if cited.atak_line and viewing_atak and cited.atak_line != viewing_atak else None
    return RowStatus(kind, cited, other)


def statuses(session: Session, rows, *, code_of, viewing_atak: str | None) -> dict:
    """(package, versionCode) -> RowStatus for every row the library touches.

    `code_of` reads a row's versionCode: TPC calls it `revision_code`, TAKWERX
    `version_code`, and neither tab should have to rename its catalog for this.
    """
    rows = list(rows)
    builds = library_builds(session, (r.package_name for r in rows))
    line = atak_line_of(viewing_atak)
    out = {}
    for row in rows:
        status = status_for(builds.get(row.package_name, []), code_of(row), line)
        if status is not None:
            out[(row.package_name, code_of(row))] = status
    return out
