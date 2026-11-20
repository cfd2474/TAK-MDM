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

"""The updates the alert checks found and the library still lacks (W454).

Operator: a badge on the library's apps "if the scan was initiated by the
admin alerts", which "clear[s] itself when the app gets updated", and a
dashboard card that "mirrors the email alerts" and "grow[s]/shrink[s] with
each check and app updated". Updated means a newer build is in the library;
the card lists every update still waiting, not only what is new since the
last email.

⚠️ **Only an update-check rule writes here.** Browsing a catalog tab shows its
own "update" pill and records nothing, so the badge means "an alert found it".

⚠️ **Written by the check, read against the library.** `record` replaces a
rule's rows with what its check found; `outstanding` compares each row with
the library again, by the same `catalog_status.status_for` the check and both
catalog tabs use. So importing the build clears it on the next page load,
without waiting for the next check, and the three can never disagree.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import urlencode
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AlertRule, AppUpdateFinding
from app.services import catalog_status
from app.services.plugin_updates import CatalogBuild, Newer


@dataclass(frozen=True)
class Outstanding:
    """One update an alert found that the library still lacks."""

    rule_id: str
    #: The rule's name, which the email puts above its lines.
    rule_name: str
    package_name: str
    label: str
    version_name: str
    version_code: int
    #: The email's line, against what the library holds *now*.
    detail: str
    held: catalog_status.Held
    found_at: datetime
    #: The catalog tab to import it from, at the rule's ATAK version.
    import_href: str


def record(session: Session, rule: AlertRule, newer: Iterable[Newer], *,
           now: datetime | None = None) -> None:
    """Replace `rule`'s findings with what its check just found. Flushes.

    ⚠️ Called only for a check that ran. One that could not reach its catalog
    learned nothing, so the last list stands rather than emptying the card.
    """
    moment = now or datetime.now(timezone.utc)
    found = {item.build.package_name: item for item in newer}
    existing = {row.package_name: row for row in session.scalars(
        select(AppUpdateFinding).where(AppUpdateFinding.rule_id == rule.id))}
    for package, row in existing.items():
        if package not in found:
            session.delete(row)
    for package, item in found.items():
        row = existing.get(package)
        if row is None:
            row = AppUpdateFinding(rule_id=rule.id, package_name=package)
            session.add(row)
        if row.version_code != item.build.version_code:
            row.found_at = moment   # a newer build is a new finding
        row.version_code = item.build.version_code
        row.version_name = item.build.version_name or ""
        row.label = item.build.label or ""
        row.detail = item.detail
    session.flush()


def outstanding(session: Session) -> list[Outstanding]:
    """Every finding of an enabled rule that the library still lacks.

    Sorted by app, then rule, so one app found by two rules (two ATAK
    versions) reads as two adjacent lines.
    """
    rows = session.execute(
        select(AppUpdateFinding, AlertRule)
        .join(AlertRule, AlertRule.id == AppUpdateFinding.rule_id)
        .where(AlertRule.enabled.is_(True))
    ).all()
    if not rows:
        return []
    held = catalog_status.library_builds(session, (f.package_name for f, _rule in rows))
    out = []
    for finding, rule in rows:
        status = catalog_status.status_for(
            held.get(finding.package_name, []), finding.version_code,
            catalog_status.atak_line_of(rule.config.get("atak_version")),
        )
        # Not UPDATE: the build (or a newer one) is in the library now, or the
        # package has left it. Either way there is nothing left to import.
        if status is None or status.kind != catalog_status.UPDATE:
            continue
        build = CatalogBuild(finding.package_name, finding.label, finding.version_name, finding.version_code)
        out.append(Outstanding(
            rule_id=str(rule.id), rule_name=rule.name, package_name=finding.package_name,
            label=finding.label, version_name=finding.version_name, version_code=finding.version_code,
            detail=Newer(build, status.held).detail, held=status.held, found_at=finding.found_at,
            import_href=import_href(rule.config),
        ))
    return sorted(out, key=lambda o: ((o.label or o.package_name).lower(), o.rule_name.lower()))


def import_href(config: dict) -> str:
    """The Apps tab that lists the rule's catalog, as the rule reads it.

    Each tab's own query parameters, so the tab opens on the ATAK version the
    rule checked rather than its default.
    """
    source = config.get("source")
    if source == "takwerx":
        query = {"tab": "takwerx", "atak_version": config.get("atak_version", "")}
    elif source == "tpc":
        query = {"tab": "tpc", "product": config.get("product", ""),
                 "product_version": config.get("atak_version", "")}
    elif source == "google-play":
        query = {"tab": "play"}
    else:
        query = {"tab": "local"}
    return "/apps?" + urlencode(query) + "#tab-" + query["tab"]


def by_package(session: Session) -> dict[str, list[Outstanding]]:
    """`outstanding`, keyed by package, for the library's badges."""
    out: dict[str, list[Outstanding]] = {}
    for item in outstanding(session):
        out.setdefault(item.package_name, []).append(item)
    return out
