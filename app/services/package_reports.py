"""The Device Package List Report: storage and the CSV (W335).

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

The device lists every package it has, on request (`PACKAGE_REPORT`), and the
latest list per device is kept. The console offers it as a CSV and as a page
the browser prints to PDF.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from zoneinfo import ZoneInfo

from app.db.models import Device, DevicePackageReport
from app.services import clock

#: A tablet has 300 to 500 packages. Ten times that is a broken or hostile agent.
MAX_PACKAGES = 3000

#: The report's columns: (key in a stored row, CSV heading).
COLUMNS: tuple[tuple[str, str], ...] = (
    ("label", "App name"),
    ("package_name", "Package"),
    ("version_name", "Version"),
    ("version_code", "Version code"),
    ("system", "System app"),
    ("enabled", "Enabled"),
    ("hidden", "Hidden by ATLAS"),
    ("installer", "Installed by"),
    ("first_installed", "First installed"),
    ("last_updated", "Last updated"),
)

#: The time columns. The CSV gives them in UTC and says so in the heading; the
#: page gives them in the console's zone (W163).
TIME_COLUMNS = frozenset({"first_installed", "last_updated"})


#: The first agent that answers PACKAGE_REPORT. An older one reports the
#: command as unsupported, so the page says so before the button is pressed.
MIN_AGENT = (0, 82, 0)


def agent_supports(agent_version: str | None) -> bool | None:
    """True or False, or None when the agent hasn't said which version it is."""
    head = (agent_version or "").split("-")[0].split("+")[0]
    try:
        parts = tuple(int(p) for p in head.split("."))
    except ValueError:
        return None
    return parts >= MIN_AGENT if parts else None


class ReportTooLarge(ValueError):
    """More packages than any real device has."""


def store(
    session: Session,
    device: Device,
    packages: list[dict[str, Any]],
    *,
    command_id: uuid.UUID | None = None,
    agent_version: str | None = None,
) -> DevicePackageReport:
    """Replace the device's report with this one."""
    if len(packages) > MAX_PACKAGES:
        raise ReportTooLarge(
            f"{len(packages)} packages; the limit is {MAX_PACKAGES}"
        )
    rows = sorted(packages, key=lambda p: ((p.get("label") or "").casefold(), p["package_name"]))
    report = latest(session, device.id)
    if report is None:
        report = DevicePackageReport(device_id=device.id)
        session.add(report)
    report.packages = rows
    report.package_count = len(rows)
    report.command_id = command_id
    report.agent_version = agent_version or device.agent_version
    report.collected_at = datetime.now(timezone.utc)
    session.flush()
    return report


def latest(session: Session, device_id: uuid.UUID) -> DevicePackageReport | None:
    return session.scalar(
        select(DevicePackageReport).where(DevicePackageReport.device_id == device_id)
    )


def display_rows(report: DevicePackageReport, tz: ZoneInfo | timezone) -> list[dict[str, str]]:
    """Each package as the text the report shows, keyed like COLUMNS."""
    return [{key: _text(key, row.get(key), tz) for key, _ in COLUMNS} for row in report.packages]


def to_csv(report: DevicePackageReport) -> str:
    """⚠️ Times in UTC, by design, and the headings say so: an export outlives
    the console setting that produced it (the location-history CSV's rule)."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [f"{heading} (UTC)" if key in TIME_COLUMNS else heading for key, heading in COLUMNS]
    )
    for row in display_rows(report, timezone.utc):
        writer.writerow([_cell(row[key]) for key, _ in COLUMNS])
    return out.getvalue()


def _text(key: str, value: Any, tz: ZoneInfo | timezone) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if key in TIME_COLUMNS and isinstance(value, int):
        if value <= 0:
            return ""
        return clock.format(datetime.fromtimestamp(value / 1000, tz=timezone.utc), tz,
                            "%Y-%m-%d %H:%M")
    return str(value)


def _cell(text: str) -> str:
    """⚠️ **Neutralise a formula.** App names come from the device, and a
    spreadsheet runs a cell starting `=`, `+`, `-`, `@` (or a tab or carriage
    return) as a formula. Prefixing `'` makes it text, which is OWASP's advice."""
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text
