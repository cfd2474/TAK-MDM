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

"""Checking a device against its COMPLIANCE rules (W323).

Two halves. :func:`evaluate` is pure: rules, the device's facts and a clock in;
one result per rule out. :func:`record` stores the outcome on the device and
raises the alert when the verdict changes. The check-in calls both; so does the
periodic sweep, because "checked in within N hours" can only fail while the
device is *not* checking in.

⚠️ **Separate from `Device.compliance_status` (W323 D-a).** That one means "applied
its policy", and the agent-update gate refuses a device that hasn't. A device
failing a rule must still get the agent update that may be what fixes it.

⚠️ **Unreported is not failing (W323 D-c).** A fact an older agent doesn't send,
or one the device couldn't read, gives "not reported", which never makes a
device non-compliant by itself.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Device, EffectivePolicyCache, EnrollmentState
from app.services import atak_compat, plugin_status

log = logging.getLogger(__name__)

PASS = "pass"
FAIL = "fail"
UNREPORTED = "unreported"

#: Device verdicts.
NONE = "none"                    # no rules apply
COMPLIANT = "compliant"          # nothing fails, at least one rule checked
NON_COMPLIANT = "non_compliant"  # at least one rule fails
UNKNOWN = "unknown"              # nothing could be checked yet

POLICY_TYPE = "COMPLIANCE"


@dataclass(frozen=True)
class RuleResult:
    key: str
    label: str
    outcome: str
    detail: str


def _version_tuple(value: str | None) -> tuple[int, ...] | None:
    if not value:
        return None
    try:
        return tuple(int(part) for part in value.split("."))
    except ValueError:
        return None


def _android_major(os_version: str | None) -> int | None:
    head = (os_version or "").strip().split(".")[0]
    return int(head) if head.isdigit() else None


def _patch_date(posture: dict) -> date | None:
    try:
        return date.fromisoformat(posture.get("security_patch") or "")
    except ValueError:
        return None


def _flag(posture: dict, key: str) -> bool | None:
    value = posture.get(key)
    return value if isinstance(value, bool) else None


def evaluate(rules: dict[str, Any] | None, device: Device, now: datetime) -> list[RuleResult]:
    """One result per rule that is set, in a fixed order."""
    rules = rules or {}
    posture = device.posture or {}
    out: list[RuleResult] = []

    def add(key: str, label: str, outcome: str, detail: str) -> None:
        out.append(RuleResult(key, label, outcome, detail))

    if (minimum := rules.get("min_android_version")) is not None:
        major = _android_major(device.os_version)
        label = f"Android {minimum} or later"
        if major is None:
            add("min_android_version", label, UNREPORTED, "Android version not reported")
        else:
            add("min_android_version", label, PASS if major >= minimum else FAIL,
                f"Android {device.os_version}")

    if (days := rules.get("max_patch_age_days")) is not None:
        patch = _patch_date(posture)
        label = f"Security patch at most {days} days old"
        if patch is None:
            add("max_patch_age_days", label, UNREPORTED, "Security patch not reported")
        else:
            age = (now.date() - patch).days
            add("max_patch_age_days", label, PASS if age <= days else FAIL,
                f"Patch {patch.isoformat()}, {age} days old")

    for key, label, fact, wanted, yes, no in (
        ("require_encryption", "Storage encrypted", "encrypted", True,
         "Encrypted", "Not encrypted"),
        ("require_password_sufficient", "Passcode meets the Password policy",
         "password_sufficient", True, "Meets the policy", "Does not meet the policy"),
        ("require_usb_debugging_off", "USB debugging off", "usb_debugging", False,
         "USB debugging is on", "USB debugging is off"),
        ("require_developer_options_off", "Developer options off", "developer_options", False,
         "Developer options are on", "Developer options are off"),
        ("require_unknown_sources_blocked", "Unknown-source installs blocked",
         "unknown_sources_blocked", True, "Blocked", "Allowed"),
    ):
        if not rules.get(key):
            continue
        value = _flag(posture, fact)
        if value is None:
            add(key, label, UNREPORTED, "Not reported")
        else:
            # `yes`/`no` describe the fact's True/False, whichever one passes.
            add(key, label, PASS if value is wanted else FAIL, yes if value else no)

    if rules.get("require_device_integrity"):
        _integrity(device, now, add)

    if (minimum := rules.get("min_atak_version")) is not None:
        label = f"ATAK {minimum} or later"
        line = atak_compat.atak_line(device.atak_version) if device.atak_version else None
        have, want = _version_tuple(line), _version_tuple(minimum)
        if have is None or want is None:
            add("min_atak_version", label, UNREPORTED, "ATAK version not reported")
        else:
            # `atak_line` always gives three parts, and tuples compare part by
            # part, so "5.9" as a minimum still reads 5.9.x correctly.
            add("min_atak_version", label, PASS if have >= want else FAIL,
                f"ATAK {device.atak_version}")

    if rules.get("require_atlas_plugin_running"):
        label = "ATLAS plugin running"
        view = plugin_status.read(device.atlas_plugin_report, device.atlas_plugin_reported_at)
        if view is None:
            add("require_atlas_plugin_running", label, UNREPORTED, "Plugin status not reported")
        else:
            add("require_atlas_plugin_running", label, PASS if view.running else FAIL,
                view.summary)

    if (hours := rules.get("max_checkin_age_hours")) is not None:
        label = f"Checked in within {hours} hours"
        if device.last_checkin_at is None:
            add("max_checkin_age_hours", label, UNREPORTED, "Never checked in")
        else:
            age = (now - device.last_checkin_at).total_seconds() / 3600
            add("max_checkin_age_hours", label, PASS if age <= hours else FAIL,
                f"Last check-in {age:.1f} hours ago")

    return out


#: An attestation older than this proves nothing about now (W323 D-j).
ATTESTATION_FRESH_FOR = timedelta(days=7)


def _integrity(device: Device, now: datetime, add) -> None:
    from app.services import device_attestation

    key, label = "require_device_integrity", "Device integrity verified"
    record = device.attestation
    if not record or device.attested_at is None:
        add(key, label, UNREPORTED, "Not attested yet")
    elif now - device.attested_at > ATTESTATION_FRESH_FOR:
        days = (now - device.attested_at).days
        add(key, label, UNREPORTED, f"Last attested {days} days ago")
    elif record.get("problems"):
        add(key, label, FAIL, "; ".join(record["problems"]))
    elif record.get("ok"):
        add(key, label, PASS, device_attestation.summary(record))
    else:
        # Nothing wrong found, but the revocation list couldn't be checked (D-i).
        add(key, label, UNREPORTED, "Google's revocation list was unavailable")


def verdict(results: list[RuleResult]) -> str:
    if not results:
        return NONE
    if any(r.outcome == FAIL for r in results):
        return NON_COMPLIANT
    if any(r.outcome == PASS for r in results):
        return COMPLIANT
    return UNKNOWN


def rules_for(payload: dict[str, Any] | None) -> dict[str, Any]:
    """The COMPLIANCE section of a device's effective policy payload."""
    values = (payload or {}).get("values") or {}
    return values.get(POLICY_TYPE) or {}


def record(session: Session, device: Device, results: list[RuleResult], now: datetime) -> bool:
    """Store the outcome, and alert when the device starts or stops failing.

    Returns True when the device started or stopped failing, which moves the
    actions due (chunk 2), so its desired state needs resolving again.
    """
    was = device.rules_status
    now_status = verdict(results)
    device.rules_status = now_status
    device.rules_results = [asdict(r) for r in results]
    device.rules_checked_at = now

    if now_status == NON_COMPLIANT and was != NON_COMPLIANT:
        device.rules_failing_since = now
        failing = ", ".join(r.label for r in results if r.outcome == FAIL)
        _note(session, "device_fails_compliance_rules", device, failing)
        return True
    if now_status != NON_COMPLIANT and was == NON_COMPLIANT:
        device.rules_failing_since = None
        _note(session, "device_meets_compliance_rules", device, None)
        return True
    return False


def _note(session: Session, event: str, device: Device, detail: str | None) -> None:
    from app.services import alerts

    alerts.note_event(session, event, device, detail)


def check(session: Session, device: Device, payload: dict[str, Any] | None,
          now: datetime | None = None) -> bool:
    """Evaluate, record, and queue or cancel the compliance wipe.

    Returns True when the verdict flipped (see :func:`record`). Never raises: a
    broken rule must not break a check-in.
    """
    from app.services import compliance_actions

    now = now or datetime.now(timezone.utc)
    try:
        changed = record(session, device, evaluate(rules_for(payload), device, now), now)
        values = (payload or {}).get("values") or {}
        compliance_actions.sync_wipe(
            session, device, compliance_actions.for_device(session, device, values, now)
        )
        return changed
    except Exception:
        log.warning("could not check compliance rules for %s", device.id, exc_info=True)
        return False


def sweep(session: Session, now: datetime | None = None) -> int:
    """Re-check every enrolled device from its cached policy. Returns how many changed.

    ⚠️ **Cached policy only, never a recompute.** The sweep runs on a timer for
    the whole fleet; a device without a cache has never been served a policy, so
    there is nothing to check it against yet.
    """
    now = now or datetime.now(timezone.utc)
    changed = 0
    rows = session.execute(
        select(Device, EffectivePolicyCache)
        .join(EffectivePolicyCache, EffectivePolicyCache.device_id == Device.id)
        .where(Device.enrollment_state == EnrollmentState.ENROLLED)
    )
    from app.services import effective_policy

    for device, cache in rows:
        before = device.rules_status
        if check(session, device, cache.payload, now):
            # The actions due moved: marks the cache stale and wakes the device
            # to fetch the new state.
            effective_policy.request_checkin(session, {device.id})
        changed += device.rules_status != before
    return changed
