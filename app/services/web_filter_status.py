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

"""What the device page says about a device's web filter (W369 F3).

From the agent's last report and the lists the device should be running.
Pure: the route passes in what is stored and what is expected.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class View:
    #: enforcing | out_of_sync | not_running | not_enforced | not_installed |
    #: not_reported | off
    state: str
    label: str
    expected_version: str | None
    running_version: str | None
    blocked: str | None
    queries: str | None
    last_error: str | None
    reported_at: datetime | None


_LABELS = {
    "enforcing": "Filtering",
    "out_of_sync": "Filtering with older lists",
    "not_running": "Filter not running",
    "not_enforced": "Not enforced by the agent",
    "not_installed": "Filter app not installed",
    "not_reported": "No report yet",
    "off": "Web Filtering is not on for this device",
}


def view(report: dict | None, reported_at: datetime | None, expected_version: str | None) -> View | None:
    """None when the device has neither Web Filtering rules nor a report."""
    if expected_version is None and not report:
        return None
    status = (report or {}).get("status") or {}
    if expected_version is None:
        state = "off"
    elif not report:
        state = "not_reported"
    elif not report.get("installed"):
        state = "not_installed"
    elif not report.get("enforced"):
        state = "not_enforced"
    elif status.get("running") != "true":
        state = "not_running"
    elif status.get("config_version") != expected_version:
        state = "out_of_sync"
    else:
        state = "enforcing"
    return View(
        state=state,
        label=_LABELS[state],
        expected_version=expected_version,
        running_version=status.get("config_version") or None,
        blocked=status.get("blocked"),
        queries=status.get("queries"),
        last_error=(report or {}).get("error") or status.get("last_error") or None,
        reported_at=reported_at,
    )
