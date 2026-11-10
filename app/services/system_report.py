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

"""What devices say about their OS updates and fonts (W465 K2b).

The agent reports, at every check-in: a pending OS update (standard Android),
the fonts and font sizes the device has and which are active (Knox), Samsung's
two OS update switches (Knox), and the answer to the boot animation probe.

Two readers: the device page (`view`), and the SYSTEM_CONFIG policy editor's font picker
(`reported_fonts`), which can only offer fonts some device has said it has.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Device


@dataclass(frozen=True)
class View:
    pending_update_since: datetime | None
    active_font: str | None
    active_font_size: float | None
    ota_allowed: bool | None
    firmware_auto_update: bool | None
    boot_animation_probe: str | None
    reported_at: datetime | None


def view(report: dict | None, reported_at: datetime | None) -> View | None:
    """None when the device never reported (an older agent)."""
    if not report:
        return None
    millis = report.get("pending_update_since")
    pending = None
    if isinstance(millis, (int, float)) and millis > 0:
        try:
            pending = datetime.fromtimestamp(millis / 1000, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            pending = None
    return View(
        pending_update_since=pending,
        active_font=report.get("active_font") or None,
        active_font_size=report.get("active_font_size"),
        ota_allowed=report.get("ota_allowed"),
        firmware_auto_update=report.get("firmware_auto_update"),
        boot_animation_probe=report.get("boot_animation_probe") or None,
        reported_at=reported_at,
    )


def reported_fonts(session: Session) -> list[str]:
    """Every font name any device reported, sorted, each once."""
    names: set[str] = set()
    for report in session.scalars(select(Device.system_report).where(Device.system_report.is_not(None))):
        for name in (report or {}).get("fonts") or []:
            if isinstance(name, str) and name.strip():
                names.add(name.strip())
    return sorted(names, key=str.lower)
