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

"""The Reports section.

Each report is a small function over the database returning ``(columns, rows)``.
One generic template renders any of them and one route serves any of them as CSV,
so adding a report is a single entry in ``REPORTS`` and nothing else (OCP).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services import clock

from app.db.models import (
    AppPackage,
    Assignment,
    Device,
    DeviceCommand,
    DeviceFileSelection,
    ManagedFile,
    Policy,
    PolicyProfile,
    ProfileAssignment,
)

Rows = tuple[list[str], list[list[object]]]


@dataclass(frozen=True)
class Report:
    key: str
    title: str
    description: str
    build: Callable[[Session], Rows]


def _dt(value, tz) -> str:
    """One timestamp, in the console's configured zone.

    ⚠️ `tz` is required rather than defaulted (W165). Every report renders
    through here, and a default would let a new report be written that silently
    prints UTC beside five others printing local — the same failure that reached
    an operator through the location-history map. A missing argument is a
    TypeError at import of the report, which is a failure somebody sees.
    """
    return clock.format(value, tz, "%Y-%m-%d %H:%M")


# --------------------------------------------------------------------------- #
# Individual reports
# --------------------------------------------------------------------------- #


def _fleet_inventory(session: Session) -> Rows:
    tz = clock.configured(session)
    columns = [
        "Name", "Serial", "Model", "OS", "Agent", "State", "Last check-in", "Enrolled",
    ]
    rows = []
    for d in session.scalars(select(Device).order_by(Device.serial_number)):
        rows.append([
            d.name or "",
            d.serial_number,
            d.model or "",
            d.os_version or "",
            d.agent_version or "",
            d.enrollment_state.value,
            _dt(d.last_checkin_at, tz),
            _dt(d.created_at, tz),
        ])
    return columns, rows


def _convergence_and_compliance(session: Session) -> Rows:
    tz = clock.configured(session)
    columns = [
        "Name", "Serial", "Server version", "Applied version", "Lag",
        "Compliance", "Detail", "Last check-in",
    ]
    rows = []
    for d in session.scalars(select(Device).order_by(Device.serial_number)):
        rows.append([
            d.name or "",
            d.serial_number,
            d.state_version,
            d.acked_state_version,
            d.state_version - d.acked_state_version,
            d.compliance_status.value,
            (d.compliance_detail or "").replace("\n", " ")[:200],
            _dt(d.last_checkin_at, tz),
        ])
    return columns, rows


def _policy_deployment(session: Session) -> Rows:
    columns = ["Policy", "Kind", "Latest version", "Device targets", "Group targets"]
    rows: list[list[object]] = []

    for p in session.scalars(
        select(Policy).where(Policy.profile_id.is_(None), Policy.is_template.is_(False))
        .order_by(Policy.name)
    ):
        counts = {"device": 0, "group": 0, "tag": 0}
        for a in session.scalars(select(Assignment).where(Assignment.policy_id == p.id)):
            counts[a.scope.value] += 1
        rows.append([
            p.name,
            "archived policy" if p.archived_at else "policy",
            p.latest_version.version if p.latest_version else 0,
            counts["device"], counts["group"], counts["tag"],
        ])

    for pr in session.scalars(select(PolicyProfile).order_by(PolicyProfile.name)):
        counts = {"device": 0, "group": 0, "tag": 0}
        for a in session.scalars(
            select(ProfileAssignment).where(ProfileAssignment.profile_id == pr.id)
        ):
            counts[a.scope.value] += 1
        rows.append([
            pr.name,
            "archived profile" if pr.archived_at else "profile",
            len(pr.sections),
            counts["device"], counts["group"], counts["tag"],
        ])
    return columns, rows


def _command_history(session: Session) -> Rows:
    tz = clock.configured(session)
    columns = ["Serial", "Command", "Status", "Attempts", "Created", "Completed", "Error"]
    rows = []
    q = (
        select(DeviceCommand, Device.serial_number)
        .join(Device, DeviceCommand.device_id == Device.id)
        .order_by(DeviceCommand.created_at.desc())
    )
    for command, serial in session.execute(q):
        rows.append([
            serial,
            command.command_type.value,
            command.status.value,
            f"{command.attempts}/{command.max_attempts}",
            _dt(command.created_at, tz),
            _dt(command.completed_at, tz),
            (command.error or "")[:200],
        ])
    return columns, rows


def _app_inventory(session: Session) -> Rows:
    columns = ["Package", "Label", "Latest version", "Parts", "Versions"]
    rows = []
    for p in session.scalars(select(AppPackage).order_by(AppPackage.package_name)):
        lv = p.latest_version
        rows.append([
            p.package_name,
            p.label or "",
            (f"{lv.version_code}" + (f" ({lv.version_name})" if lv.version_name else "")) if lv else "",
            len(lv.files) if lv else 0,
            len(p.versions),
        ])
    return columns, rows


def _file_selections(session: Session) -> Rows:
    tz = clock.configured(session)
    columns = ["Serial", "File", "Chosen at"]
    rows = []
    q = (
        select(DeviceFileSelection, Device.serial_number, ManagedFile.name)
        .join(Device, DeviceFileSelection.device_id == Device.id)
        .join(ManagedFile, DeviceFileSelection.file_id == ManagedFile.id)
        .order_by(DeviceFileSelection.applied_at.desc())
    )
    for selection, serial, file_name in session.execute(q):
        rows.append([serial, file_name, _dt(selection.applied_at, tz)])
    return columns, rows


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

REPORTS: dict[str, Report] = {
    r.key: r
    for r in (
        Report("fleet-inventory", "Fleet inventory",
               "Every device with its model, OS, agent build and enrolment.",
               _fleet_inventory),
        Report("convergence", "Convergence & compliance",
               "Server-intended vs device-applied policy version, and compliance state.",
               _convergence_and_compliance),
        Report("policy-deployment", "Policy deployment",
               "Policies and profiles, their latest version, and how many targets each reaches.",
               _policy_deployment),
        Report("command-history", "Command history",
               "Every transient command dispatched to a device, newest first.",
               _command_history),
        Report("app-inventory", "App inventory",
               "Uploaded packages, their latest version, and whether the ATLAS store lists them.",
               _app_inventory),
        Report("file-selections", "Marketplace selections",
               "Optional files each device's user chose to install (F4).",
               _file_selections),
    )
}

#: Physical telemetry (battery, storage, network) is not in this list: the agent
#: does not report those fields yet. Adding them is an agent + schema change, not a
#: reporting one. The Fleet inventory report covers what the device does send.


def get(key: str) -> Report | None:
    return REPORTS.get(key)


def to_csv(columns: list[str], rows: list[list[object]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    writer.writerows(rows)
    return buffer.getvalue()
