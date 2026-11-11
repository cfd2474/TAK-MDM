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

"""The dashboard's "Updates available" card (W454).

Operator: "a card near the top of the dashboard that shows apps available for
update with a count and list that mirrors the email alerts", plus "notes ...
that show which alerts are currently configured, as well as a note when none
are setup, instructing the user to set alerts for this function to work".

Plain data, for the page and its 60 s refresh alike (W440): the list comes
from `app_update_findings.outstanding`, so it is the library badges' list.

⚠️ **An empty list is only good news when a check is watching.** With no
update-check rule, or every one turned off, nothing would ever appear here,
and "nothing waiting" would be a claim the card cannot make. So the card's
note says which of the three it is.
"""

from __future__ import annotations

from datetime import tzinfo
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AlertRule
from app.services import alert_rules, alert_schedule, app_update_findings, clock

#: Where an update-check alert is added.
ALERTS_HREF = "/admin#tab-general"

#: No update-check rule exists.
NONE = "none"
#: Rules exist, and every one is turned off.
OFF = "off"
#: At least one rule is on.
WATCHING = "watching"

_TIME = "%Y-%m-%d %H:%M"


def _rule_row(rule: AlertRule, tz: tzinfo) -> dict[str, Any]:
    if rule.last_checked_at is None:
        last = "Not checked yet"
    else:
        last = f"Last checked {clock.format(rule.last_checked_at, tz, _TIME)}: {rule.last_result or ''}".rstrip(": ")
    what = alert_rules.describe(rule.kind, rule.config)
    return {
        "name": rule.name,
        # A rule's name defaults to its description; saying it twice says nothing.
        "what": "" if what == rule.name else what,
        "schedule": alert_schedule.describe(rule.schedule),
        "enabled": rule.enabled,
        "last": last,
    }


def _note(state: str, count: int, newest_check: str) -> str:
    if state == NONE:
        return ("No update-check alert is set up, so nothing is checked and this card stays empty. "
                "Add an update-check alert on Admin › General for this card and the library badges to work.")
    if state == OFF:
        return ("Every update-check alert is turned off, so nothing is checked and this card stays empty. "
                "Turn one on, or add one, on Admin › General for this card and the library badges to work.")
    if count:
        return ""
    if not newest_check:
        return "No check has run yet. Press Check now on Admin › General, or wait for the next scheduled check."
    return f"The library is up to date with what the checks found. Last check {newest_check}."


def read(session: Session, tz: tzinfo) -> dict[str, Any]:
    """Everything the card shows."""
    rules = list(session.scalars(
        select(AlertRule).where(AlertRule.kind == alert_rules.PLUGIN_UPDATES).order_by(AlertRule.name)))
    state = NONE if not rules else WATCHING if any(r.enabled for r in rules) else OFF
    found = app_update_findings.outstanding(session) if state == WATCHING else []
    checked = [r.last_checked_at for r in rules if r.enabled and r.last_checked_at is not None]
    newest_check = clock.format(max(checked), tz, _TIME) if checked else ""
    return {
        "state": state,
        # Apps, not lines: one app found by two rules (two ATAK versions) is
        # one app to update, though each rule keeps its own line, as in its email.
        "count": len({item.package_name for item in found}),
        "found": [
            {
                "label": item.label or item.package_name,
                "package_name": item.package_name,
                "version": f"{item.version_name} ({item.version_code})" if item.version_name else str(item.version_code),
                "detail": item.detail,
                "rule": item.rule_name,
                "href": item.import_href,
            }
            for item in found
        ],
        "rules": [_rule_row(rule, tz) for rule in rules],
        "note": _note(state, len(found), newest_check),
        "alerts_href": ALERTS_HREF,
    }
