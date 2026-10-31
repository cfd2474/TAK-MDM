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

"""The daily check behind a plugin-updates alert rule (W422).

Operator: "if a newer release is found than the one in the library, it can
trigger an email alert … don't keep sending it each day unless an even newer
version is detected."

One rule reads one catalog at one ATAK version and compares it with the
library by `catalog_status.status_for`, the rule both catalog tabs use for
their "update" pill, so the email and the tab can never disagree.

⚠️ **Each build is reported once, ever.** The occurrence's `subject` is
`package@versionCode`, and a subject a rule has already raised is never raised
again by it: tomorrow's check finds the same build and says nothing; a newer
build is a new subject and one new email. Importing the update stops it being
found at all.

⚠️ **A check that cannot run says so once.** One open "unreachable"
occurrence while it keeps failing; a successful check closes it, so the next
failure is news again.

⚠️ **It informs; it never acts** (W281's rule): no import, no policy edit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AlertOccurrence, AlertRule, TakGovLinkStatus
from app.services import alert_rules, catalog_status

log = logging.getLogger(__name__)

#: The subject of the one "this check cannot run" occurrence a rule keeps open.
UNREACHABLE = "unreachable"


@dataclass(frozen=True)
class CatalogBuild:
    """One build a catalog offers, whichever catalog it came from."""

    package_name: str
    label: str
    version_name: str
    version_code: int | None


class CatalogUnavailable(Exception):
    """The catalog could not be read; the message is for the operator."""


#: Reads one rule's catalog. Injected, so no test opens a socket.
Fetch = Callable[[Session, dict], list[CatalogBuild]]


@dataclass(frozen=True)
class Newer:
    """A build the catalog has that is newer than anything the library holds."""

    build: CatalogBuild
    held: catalog_status.Held

    @property
    def subject(self) -> str:
        return f"{self.build.package_name}@{self.build.version_code}"

    @property
    def detail(self) -> str:
        """One line of the email. The rule's name, before it, says which catalog."""
        name = self.build.label or self.build.package_name
        return (f"{name} ({self.build.package_name}): {self.build.version_name} "
                f"({self.build.version_code}) is available; the library has "
                f"{self.held.version_name} ({self.held.version_code})")


def newer_builds(session: Session, builds: list[CatalogBuild], atak_version: str) -> list[Newer]:
    """The catalog builds that would read "update" on the catalog's own tab."""
    found = catalog_status.statuses(session, builds, code_of=lambda b: b.version_code,
                                    viewing_atak=atak_version)
    # ⚠️ The newest per package only: a catalog listing 13 and 14 of a plugin
    # held at 12 is one piece of news, and 14 is the build worth importing.
    best: dict[str, Newer] = {}
    for build in builds:
        status = found.get((build.package_name, build.version_code))
        if status is None or status.kind != catalog_status.UPDATE:
            continue
        current = best.get(build.package_name)
        if current is None or (build.version_code or 0) > (current.build.version_code or 0):
            best[build.package_name] = Newer(build, status.held)
    return sorted(best.values(), key=lambda n: (n.build.label or n.build.package_name).lower())


# --------------------------------------------------------------------------- #
# The two catalogs
# --------------------------------------------------------------------------- #


def fetch_takwerx(session: Session, config: dict, *, client=None) -> list[CatalogBuild]:
    from app.services.app_sources.base import SourceError
    from app.services.app_sources.takwerx import TakwerxSource

    try:
        entries = TakwerxSource(config["atak_version"], client=client).catalog()
    except SourceError as exc:
        raise CatalogUnavailable(str(exc)) from exc
    return [CatalogBuild(e.package_name, e.label, e.display_version or e.version, e.version_code)
            for e in entries]


def tpc_fetcher(vault, *, client=None) -> Fetch:
    """TAK.gov needs the linked account, so its fetch carries the vault."""

    def fetch(session: Session, config: dict) -> list[CatalogBuild]:
        from app.services import tak_gov_link

        plugins, error = tak_gov_link.catalog(
            session, vault, product=config["product"], product_version=config["atak_version"], client=client,
        )
        if error:
            raise CatalogUnavailable(f"TAK.gov refused the catalog: {error}")
        if not plugins:
            link = tak_gov_link.get(session)
            if link.status is TakGovLinkStatus.BROKEN:
                raise CatalogUnavailable(f"the TAK.gov link is broken ({link.last_error or 'no detail'}); "
                                         "re-link it on Admin › TAK.gov")
            if link.status is not TakGovLinkStatus.LINKED:
                raise CatalogUnavailable("no TAK.gov account is linked; link one on Admin › TAK.gov")
        return [CatalogBuild(p.package_name, p.display_name or "", p.version or "", p.revision_code)
                for p in plugins]

    return fetch


def play_fetcher(vault, *, details=None) -> Fetch:
    """Google Play, as one fleet device (W435).

    Asks only for the packages whose library builds came from Play: an app
    imported from F-Droid or uploaded by hand has its own source of truth,
    and Play offering the same package name says nothing about that build.
    One bulk call for all of them. `details` builds the client; a test passes
    one that never reaches Google.
    """

    def fetch(session: Session, config: dict) -> list[CatalogBuild]:
        from app.db.models import AppPackage, AppPackageVersion
        from app.services import google_play_link, play_profiles
        from app.services.app_sources.base import SourceError
        from app.services.app_sources.play_details import PlayDetails

        properties = play_profiles.fleet_properties(session, config.get("device_profile"))
        if properties is None:
            raise CatalogUnavailable(
                f"no device has reported the {config.get('device_profile', '').split(':', 1)[-1]} "
                "profile any more; choose another device for this alert")
        linked = google_play_link.credentials(session, vault)
        if linked is None:
            raise CatalogUnavailable("no Google account is linked; link one on Admin › Google Play")
        labels = dict(session.execute(
            select(AppPackage.package_name, AppPackage.label)
            .join(AppPackageVersion, AppPackageVersion.package_id == AppPackage.id)
            .where(AppPackageVersion.source == "google-play")
        ).all())
        if not labels:
            return []
        email, token, _stored = linked
        try:
            found = (details or PlayDetails)(email, token, properties).lookup(sorted(labels))
        except SourceError as exc:
            raise CatalogUnavailable(str(exc)) from exc   # already redacted
        return [CatalogBuild(b.package_name, labels.get(b.package_name) or "", b.version_name, b.version_code)
                for b in found.values() if b is not None]

    return fetch


# --------------------------------------------------------------------------- #
# The check
# --------------------------------------------------------------------------- #


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def _said(session: Session, rule: AlertRule, subject: str) -> bool:
    return session.scalar(
        select(AlertOccurrence.id).where(AlertOccurrence.rule_id == rule.id,
                                         AlertOccurrence.subject == subject).limit(1)
    ) is not None


def _open_unreachable(session: Session, rule: AlertRule) -> AlertOccurrence | None:
    return session.scalar(
        select(AlertOccurrence).where(AlertOccurrence.rule_id == rule.id,
                                      AlertOccurrence.subject == UNREACHABLE,
                                      AlertOccurrence.cleared_at.is_(None))
    )


def check(session: Session, rule: AlertRule, fetch: Fetch, *, now: datetime | None = None) -> list[AlertOccurrence]:
    """Run one rule's check. Returns what it newly raised. Flushes, never commits."""
    moment = _now(now)
    rule.last_checked_at = moment
    try:
        builds = fetch(session, rule.config)
    except CatalogUnavailable as exc:
        rule.last_result = f"Could not check: {exc}"
        if _open_unreachable(session, rule) is not None:
            session.flush()
            return []
        failure = AlertOccurrence(rule_id=rule.id, raised_at=moment, subject=UNREACHABLE,
                                  detail=f"Could not check: {exc}")
        session.add(failure)
        session.flush()
        return [failure]

    stuck = _open_unreachable(session, rule)
    if stuck is not None:
        stuck.cleared_at = moment   # it works again, so the next failure is news

    newer = newer_builds(session, builds, rule.config.get("atak_version", ""))
    raised = []
    for item in newer:
        if _said(session, rule, item.subject):
            continue
        # ⚠️ Written closed, like an event: the build being available is the
        # news, and suppression is by subject, not by an open interval.
        occurrence = AlertOccurrence(rule_id=rule.id, raised_at=moment, cleared_at=moment,
                                     subject=item.subject, detail=item.detail)
        session.add(occurrence)
        raised.append(occurrence)
    rule.last_result = (
        f"{len(builds)} build{'' if len(builds) == 1 else 's'} in the catalog; "
        + (f"{len(newer)} newer than the library" if newer else "nothing newer than the library")
        + (f", {len(raised)} new since the last alert" if newer else "")
    )
    session.flush()
    return raised


def check_due(session: Session, fetchers: dict[str, Fetch], *, now: datetime | None = None,
              tz=None) -> list[AlertOccurrence]:
    """The enabled rules whose scheduled slot has come round (W436).

    ⚠️ A rule is marked as run for the slot whatever came of it: a check that
    could not run already says so once, and retrying it every minute would be
    a minute-by-minute load on someone else's server.
    """
    from app.services import alert_schedule, clock

    moment = _now(now)
    zone = tz if tz is not None else clock.configured(session)
    raised: list[AlertOccurrence] = []
    rules = session.scalars(select(AlertRule).where(AlertRule.kind == alert_rules.PLUGIN_UPDATES,
                                                    AlertRule.enabled.is_(True)))
    for rule in list(rules):
        if not alert_schedule.is_due(rule.schedule, rule.last_scheduled_run_at, moment, zone):
            continue
        rule.last_scheduled_run_at = alert_schedule.previous_slot(rule.schedule, moment, zone)
        fetch = fetchers.get(rule.config.get("source", ""))
        if fetch is None:
            continue
        try:
            raised.extend(check(session, rule, fetch, now=moment))
        except Exception:
            log.warning("plugin update check failed for %s", rule.name, exc_info=True)
    session.flush()
    return raised


def default_fetchers(vault) -> dict[str, Fetch]:
    return {"takwerx": fetch_takwerx, "tpc": tpc_fetcher(vault), "google-play": play_fetcher(vault)}
