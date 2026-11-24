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

"""Web activity: the sites each app on a device looked up (W501).

The ATLAS filter sees every DNS lookup that reaches it and names the app behind
it (platform reference, "The filter can name the app behind each lookup"); the
agent uploads what it recorded. This module stores those uploads, keeps them
for the retention window, and answers the console's questions about them.

Site names only. The filter never sees a full address, a page, or content.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import Device, DeviceAppUsage, DeviceWebEvent

logger = logging.getLogger(__name__)

#: How long web activity is kept when nobody has said otherwise (operator, W501).
DEFAULT_RETENTION_DAYS = 30

#: The setting that overrides it.
RETENTION_KEY = "web_activity.retention_days"

#: "Never delete": the same fail-safe polarity as location history (see
#: `locations.KEEP_FOR_EVER`). Misread as "keep for ever" it costs disk;
#: misread the other way it would empty the table on a timer.
KEEP_FOR_EVER = 0

#: The most events one upload may carry. The agent sends pages of this size.
MAX_BATCH = 1000

#: Reverse lookups name an address, not a site: noise in a list of sites.
_REVERSE_SUFFIXES = (".in-addr.arpa", ".ip6.arpa")

#: What a looked-up name may contain. ⚠️ Not cosmetic: a name is written into the
#: CSV export, and one starting with `=`, `+` or `@` is a formula to a
#: spreadsheet. DNS names are letters, digits, hyphens, dots and (in practice)
#: underscores; anything else an app sent is dropped, never stored.
_HOST_CHARS = re.compile(r"^[a-z0-9_][a-z0-9_.-]*$")
#: An Android package, or a shared-uid name such as `android.uid.system:1000`.
_PACKAGE_CHARS = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.:]*$")


@dataclass(frozen=True)
class Incoming:
    """One event as the agent sent it, already validated by the schema."""

    stream: int
    seq: int
    hostname: str
    package_name: str | None
    looked_up_at: datetime
    lookups: int
    blocked: bool


@dataclass(frozen=True)
class StoreResult:
    accepted: int
    duplicates: int
    dropped: int


def normalize_host(name: str) -> str | None:
    """Lower case, no trailing dot; None for a reverse lookup or an empty name."""
    host = (name or "").strip().lower().rstrip(".")
    if not host or host.endswith(_REVERSE_SUFFIXES) or not _HOST_CHARS.match(host):
        return None
    return host


def clean_package(name: str | None) -> str | None:
    """The package as sent, or None when it is not a package-shaped name."""
    name = (name or "").strip()
    return name if name and _PACKAGE_CHARS.match(name) else None


def store(session: Session, device: Device, events: Iterable[Incoming]) -> StoreResult:
    """Add a device's events, skipping any (stream, seq) already stored.

    ⚠️ The duplicate check is by select-then-insert, not by catching the unique
    violation: one device uploads one page at a time, and a violation would
    abort the whole transaction, taking the page's new events with it. The
    unique constraint still stands behind it.
    """
    events = list(events)
    keys = {(e.stream, e.seq) for e in events}
    existing: set[tuple[int, int]] = set()
    for stream in {k[0] for k in keys}:
        seqs = [k[1] for k in keys if k[0] == stream]
        existing.update(
            (stream, seq)
            for seq in session.scalars(
                select(DeviceWebEvent.seq).where(
                    DeviceWebEvent.device_id == device.id,
                    DeviceWebEvent.stream == stream,
                    DeviceWebEvent.seq.in_(seqs),
                )
            )
        )
    accepted = duplicates = dropped = 0
    seen: set[tuple[int, int]] = set()
    for e in events:
        key = (e.stream, e.seq)
        if key in existing or key in seen:
            duplicates += 1
            continue
        seen.add(key)
        host = normalize_host(e.hostname)
        if host is None:
            dropped += 1
            continue
        session.add(DeviceWebEvent(
            device_id=device.id, stream=e.stream, seq=e.seq, hostname=host,
            package_name=clean_package(e.package_name), looked_up_at=e.looked_up_at,
            lookups=max(1, e.lookups), blocked=e.blocked,
        ))
        accepted += 1
    session.flush()
    return StoreResult(accepted=accepted, duplicates=duplicates, dropped=dropped)


def retention_days(session: Session) -> int:
    """The configured window in days; anything unparseable or negative is the
    default, never "keep nothing" (the reasoning in `locations.retention_days`)."""
    from app.services import settings_store

    raw = settings_store.get(session, RETENTION_KEY, "").strip()
    if not raw:
        return DEFAULT_RETENTION_DAYS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_RETENTION_DAYS
    return value if value >= 0 else DEFAULT_RETENTION_DAYS


def purge(session: Session, days: int | None = None, now: datetime | None = None) -> int:
    """Delete web activity older than the window. Returns the count.

    Always bounded by an age filter (a window of 0 returns early), and it touches
    `device_web_event` only. By `looked_up_at`, the time the operator sees.
    """
    window = retention_days(session) if days is None else days
    if window <= KEEP_FOR_EVER:
        return 0
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=window)
    removed = session.execute(
        delete(DeviceWebEvent).where(DeviceWebEvent.looked_up_at < cutoff)
    ).rowcount or 0
    # Screen time goes with it, by day (the whole day must have passed).
    session.execute(delete(DeviceAppUsage).where(DeviceAppUsage.day < (cutoff - timedelta(days=1)).date()))
    if removed:
        logger.info("web activity retention: removed %d event(s) before %s (%d day window)",
                    removed, cutoff.isoformat(), window)
    return removed


# --------------------------------------------------------------------------- #
# Reading it back (W501 chunk 5)
# --------------------------------------------------------------------------- #

#: Web browsers, for the "Browsers only" view (the default, operator W501).
#: Known packages rather than a device's intent resolution: the server has no
#: way to ask a device which apps open links, and a missing browser here only
#: means its sites appear under "All apps".
BROWSERS: frozenset[str] = frozenset({
    "com.android.chrome", "com.chrome.beta", "com.chrome.dev", "com.chrome.canary",
    "com.sec.android.app.sbrowser", "com.sec.android.app.sbrowser.beta",
    "org.mozilla.firefox", "org.mozilla.firefox_beta", "org.mozilla.fenix", "org.mozilla.focus",
    "com.microsoft.emmx", "com.brave.browser", "com.opera.browser", "com.opera.mini.native",
    "com.duckduckgo.mobile.android", "com.vivaldi.browser", "com.kiwibrowser.browser",
    "com.android.browser", "org.chromium.chrome", "com.ecosia.android",
})


@dataclass
class SiteRow:
    """One site on one device over a window: its names grouped together."""

    site: str
    first: datetime
    last: datetime
    lookups: int = 0
    apps: set[str] | None = None
    hosts: set[str] | None = None
    blocked: bool = False
    #: Estimated visits, as (start, end): lookups closer than VISIT_GAP joined.
    visits: list[tuple[datetime, datetime]] | None = None


def site_of(host: str) -> str:
    """The registrable site of a hostname (`news.bbc.co.uk` → `bbc.co.uk`).

    An address, a single label, or a name the Public Suffix List cannot place
    is its own site.
    """
    import ipaddress

    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    return _psl().privatesuffix(host) or host


_PSL = None


def _psl():
    global _PSL
    if _PSL is None:
        from publicsuffixlist import PublicSuffixList

        _PSL = PublicSuffixList()
    return _PSL


def events(session: Session, device_id, *, oldest: datetime | None = None,
           newest: datetime | None = None) -> list[DeviceWebEvent]:
    """A device's events in a window, oldest first."""
    query = select(DeviceWebEvent).where(DeviceWebEvent.device_id == device_id)
    if oldest is not None:
        query = query.where(DeviceWebEvent.looked_up_at >= oldest)
    if newest is not None:
        query = query.where(DeviceWebEvent.looked_up_at < newest)
    return list(session.scalars(query.order_by(DeviceWebEvent.looked_up_at, DeviceWebEvent.id)))


#: Lookups of one site closer than this are one visit (an estimate, W501). Ten
#: minutes: twice the filter's five-minute grouping window, so steady use of a
#: site, which looks a name up again at least every window, stays one visit.
VISIT_GAP = timedelta(minutes=10)


def visits(times: Iterable[datetime], gap: timedelta = VISIT_GAP) -> list[tuple[datetime, datetime]]:
    """Join sorted lookup times into (start, end) spans; an estimate, not a
    measurement. A lone lookup is a span of zero length."""
    spans: list[tuple[datetime, datetime]] = []
    for t in sorted(times):
        if spans and t - spans[-1][1] <= gap:
            spans[-1] = (spans[-1][0], t)
        else:
            spans.append((t, t))
    return spans


def summarize(rows: Iterable[DeviceWebEvent], *, browsers_only: bool) -> list[SiteRow]:
    """Group events by site, busiest first. Pure, for the page and its tests."""
    sites: dict[str, SiteRow] = {}
    times: dict[str, list[datetime]] = {}
    for e in rows:
        if browsers_only and e.package_name not in BROWSERS:
            continue
        site = site_of(e.hostname)
        row = sites.get(site)
        if row is None:
            row = sites[site] = SiteRow(site, e.looked_up_at, e.looked_up_at, apps=set(), hosts=set())
        row.first = min(row.first, e.looked_up_at)
        row.last = max(row.last, e.looked_up_at)
        row.lookups += e.lookups
        row.apps.add(e.package_name or "unknown app")
        row.hosts.add(e.hostname)
        row.blocked = row.blocked or e.blocked
        times.setdefault(site, []).append(e.looked_up_at)
    for site, row in sites.items():
        row.visits = visits(times[site])
    return sorted(sites.values(), key=lambda r: (-r.lookups, r.site))


@dataclass(frozen=True)
class DeviceHit:
    device_id: object
    first: datetime
    last: datetime
    lookups: int


def devices_reaching(session: Session, site: str, *, oldest: datetime, newest: datetime,
                     device_ids: Iterable | None = None) -> list[DeviceHit]:
    """Which devices looked up [site] (or any name under it) in a window.

    [device_ids] None means every device (a super admin); a standard admin
    passes their scope, so a device outside it is never counted.
    """
    from sqlalchemy import func, or_

    host = normalize_host(site)
    if host is None:
        return []
    query = (
        select(DeviceWebEvent.device_id, func.min(DeviceWebEvent.looked_up_at),
               func.max(DeviceWebEvent.looked_up_at), func.sum(DeviceWebEvent.lookups))
        .where(or_(DeviceWebEvent.hostname == host,
                   DeviceWebEvent.hostname.like("%." + host.replace("%", "").replace("_", "\\_"),
                                                escape="\\")))
        .where(DeviceWebEvent.looked_up_at >= oldest, DeviceWebEvent.looked_up_at < newest)
        .group_by(DeviceWebEvent.device_id)
    )
    if device_ids is not None:
        ids = list(device_ids)
        if not ids:
            return []
        query = query.where(DeviceWebEvent.device_id.in_(ids))
    hits = [DeviceHit(d, first, last, int(n or 0)) for d, first, last, n in session.execute(query)]
    return sorted(hits, key=lambda h: h.last, reverse=True)


# --------------------------------------------------------------------------- #
# Time in apps (W501 chunk 6)
# --------------------------------------------------------------------------- #


def store_usage(session: Session, device: Device, day_text: str, apps: dict[str, int]) -> None:
    """Replace a device's figures for one day with the agent's running totals."""
    from datetime import date as date_type

    try:
        day = date_type.fromisoformat(day_text)
    except ValueError:
        return
    existing = {
        u.package_name: u
        for u in session.scalars(select(DeviceAppUsage).where(
            DeviceAppUsage.device_id == device.id, DeviceAppUsage.day == day))
    }
    for package, ms in apps.items():
        row = existing.get(package)
        if row is None:
            session.add(DeviceAppUsage(device_id=device.id, day=day, package_name=package, foreground_ms=ms))
        elif row.foreground_ms != ms:
            row.foreground_ms = ms
    # The session does not autoflush: a second report in the same session must
    # see the rows the first one added, or it inserts them twice.
    session.flush()


def usage_for(session: Session, device_id, day, *, browsers_only: bool) -> list[DeviceAppUsage]:
    """One day's time in front per app, longest first."""
    rows = session.scalars(select(DeviceAppUsage).where(
        DeviceAppUsage.device_id == device_id, DeviceAppUsage.day == day))
    rows = [r for r in rows if r.foreground_ms > 0 and (not browsers_only or r.package_name in BROWSERS)]
    return sorted(rows, key=lambda r: -r.foreground_ms)


def duration_text(ms: int) -> str:
    """`2 h 10 min`, `12 min`, `under a minute`."""
    minutes = ms // 60_000
    if minutes < 1:
        return "under a minute"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} min" if hours else f"{minutes} min"
