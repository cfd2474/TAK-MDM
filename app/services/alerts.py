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

"""Who gets told when the fleet needs attention (W195).

Chunk 1 is the recipient list. The rules that decide *what* is worth telling
them, and the sending itself, come after — and this file is deliberately usable
before either exists, because a list of addresses is a thing an operator can get
right in advance.

⚠️ **Nothing here sends anything.** ATLAS still has no mail path; see
`app.services.mail`.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AlertOccurrence,
    AlertRecipient,
    AlertRule,
    Device,
    EnrollmentState,
)


log = logging.getLogger(__name__)


class AlertError(Exception):
    """A recipient cannot be added as asked."""


#: What counts as an address worth trying.
#:
#: ⚠️ **Deliberately permissive, and not RFC 5321.** The real grammar allows
#: quoted local parts, comments and address literals, and a validator strict
#: enough to be correct rejects addresses that work — which is the worse
#: failure, because the operator is then arguing with a form about an address
#: their mail already reaches. This refuses what is certainly a mistake: no `@`,
#: nothing before or after it, whitespace, or more than one `@`.
#:
#: ⚠️ The check that actually matters cannot be done here at all. Only a send
#: proves an address receives mail, and a recipient list full of plausible
#: addresses nobody reads looks exactly like a working one.
_ADDRESS = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

#: Longest address the column holds, and the RFC's own limit.
MAX_ADDRESS = 320


def list_recipients(session: Session, *, include_disabled: bool = True) -> list[AlertRecipient]:
    """Everyone on the list, disabled ones last so the live list reads first."""
    rows = session.scalars(
        select(AlertRecipient).order_by(
            AlertRecipient.enabled.desc(), AlertRecipient.address
        )
    ).all()
    return list(rows) if include_disabled else [r for r in rows if r.enabled]


def add(
    session: Session, *, address: str, label: str | None = None, by: str | None = None
) -> AlertRecipient:
    """Put an address on the list.

    ⚠️ Lower-cased, because the local part is case-sensitive in the standard and
    in practice never is. Two rows differing only in case would be one person
    receiving every alert twice — and the duplicate is what teaches them to
    filter the original.
    """
    cleaned = (address or "").strip().lower()
    if not cleaned:
        raise AlertError("a recipient needs an email address")
    if len(cleaned) > MAX_ADDRESS:
        raise AlertError(f"that address is longer than {MAX_ADDRESS} characters")
    if not _ADDRESS.match(cleaned):
        raise AlertError(
            f"{address.strip()!r} does not look like an email address — "
            f"it needs one @ with a domain after it, and no spaces"
        )

    existing = session.scalar(
        select(AlertRecipient).where(AlertRecipient.address == cleaned)
    )
    if existing is not None:
        # ⚠️ Named rather than silently ignored. "Add" that quietly does nothing
        # reads as a broken button, and re-adding a *disabled* address is how an
        # operator tries to turn it back on.
        raise AlertError(
            f"{cleaned} is already on the list"
            + ("" if existing.enabled else " — enable it rather than adding it again")
        )

    recipient = AlertRecipient(
        address=cleaned, label=(label or "").strip() or None, created_by=by
    )
    session.add(recipient)
    session.flush()
    return recipient


# --------------------------------------------------------------------------- #
# Raising, and not raising twice
# --------------------------------------------------------------------------- #


def _now(now: datetime | None) -> datetime:
    return now if now is not None else datetime.now(timezone.utc)


def open_occurrence(
    session: Session, rule: AlertRule, device: Device
) -> AlertOccurrence | None:
    """The occurrence still saying this about this device, if there is one."""
    return session.scalar(
        select(AlertOccurrence).where(
            AlertOccurrence.rule_id == rule.id,
            AlertOccurrence.device_id == device.id,
            AlertOccurrence.cleared_at.is_(None),
        )
    )


def raise_state(
    session: Session,
    rule: AlertRule,
    device: Device,
    detail: str | None = None,
    now: datetime | None = None,
) -> AlertOccurrence | None:
    """Say a condition has started holding for this device. Returns what is new.

    ⚠️ **None means "already said", and that is the feature.** A device with
    no check-in for 72 hours has none for 73, 74 and 75; the condition is true
    on every sweep for as long as it lasts. Raising each time is an email a
    sweep, for every quiet device, for ever — which is how a team learns to file
    alerting somewhere it is not read, and then misses the one that mattered.
    """
    if not rule.enabled:
        return None
    if open_occurrence(session, rule, device) is not None:
        return None

    occurrence = AlertOccurrence(
        rule_id=rule.id, device_id=device.id, raised_at=_now(now), detail=detail
    )
    session.add(occurrence)
    session.flush()
    log.info("alert raised: %s on %s", rule.name, device.serial_number)
    return occurrence


def clear_state(
    session: Session, rule: AlertRule, device: Device, now: datetime | None = None
) -> bool:
    """Say the condition has stopped holding. Returns whether anything was open.

    ⚠️ This is what re-arms the alert. Without it the first 72 hours of
    silence would be the only one ever reported, and a device that went quiet,
    came back, and went quiet again would look like it never left.
    """
    occurrence = open_occurrence(session, rule, device)
    if occurrence is None:
        return False
    occurrence.cleared_at = _now(now)
    session.flush()
    log.info("alert cleared: %s on %s", rule.name, device.serial_number)
    return True


def record_event(
    session: Session, event: str, device: Device, detail: str | None = None,
    now: datetime | None = None,
) -> list[AlertOccurrence]:
    """Note that something happened, for every enabled rule watching for it.

    ⚠️ **Written already closed**, because the thing it describes is over.
    An enrolment is a moment, not a state: leaving it open would suppress the
    *next* enrolment of the same device for ever, so a tablet that was
    disenrolled and re-enrolled would announce itself once and then never
    again.

    ⚠️ **No suppression here, deliberately.** Two enrolments are two events
    and both are worth knowing about. What stops a flood is that the hooks fire
    on transitions rather than on states — see the compliance hook, which would
    otherwise report the same broken device on every check-in.
    """
    moment = _now(now)
    raised: list[AlertOccurrence] = []
    for rule in session.scalars(
        select(AlertRule).where(AlertRule.kind == "event", AlertRule.enabled.is_(True))
    ):
        if rule.config.get("event") != event:
            continue
        occurrence = AlertOccurrence(
            rule_id=rule.id,
            device_id=device.id,
            raised_at=moment,
            cleared_at=moment,
            detail=detail,
        )
        session.add(occurrence)
        raised.append(occurrence)
    if raised:
        session.flush()
        log.info("alert event %s on %s", event, device.serial_number)
    return raised


def note_event(session: Session, event: str, device: Device, detail: str | None = None) -> None:
    """`record_event`, but it never takes the caller down with it.

    ⚠️ **The hooks live inside enrolment, check-in, disenrolment and breach
    mode**, and not one of those may fail because alerting did. A device that
    cannot enrol because a notification rule is malformed is a far worse outcome
    than a notification nobody receives — so this swallows, and says so at
    warning level rather than in silence.
    """
    try:
        record_event(session, event, device, detail)
    except Exception:
        log.warning("could not record the %s alert", event, exc_info=True)


# --------------------------------------------------------------------------- #
# Looking for the conditions that are true now
# --------------------------------------------------------------------------- #


def evaluate(session: Session, now: datetime | None = None) -> list[AlertOccurrence]:
    """Check every state rule against every device it applies to.

    Returns only what is **newly** raised, which is what a sender wants: the
    conditions that were already true have already been reported.

    ⚠️ Clearing happens in the same pass. A rule that only ever raises reports
    the first 72 hours of silence and nothing afterwards, for the life of the
    device — so a tablet that went quiet, came back, and went quiet again would
    look as though it had never left.
    """
    from app.services import alert_rules

    moment = _now(now)
    devices = list(session.scalars(select(Device)))
    raised: list[AlertOccurrence] = []

    for rule in session.scalars(select(AlertRule).where(AlertRule.enabled.is_(True))):
        if rule.kind == "stale":
            def holds(device: Device, rule: AlertRule = rule) -> bool:
                return _is_quiet(device, rule, moment)

            def detail(device: Device) -> str:
                return _quiet_detail(device, moment)

        elif rule.kind == "custom":
            # ⚠️ `rule` is bound as a default argument rather than captured. A
            # closure over the loop variable would have every rule evaluating
            # the *last* one by the time these are called — the classic late
            # binding bug, and here it would alert on the wrong condition
            # silently rather than failing.
            def holds(device: Device, rule: AlertRule = rule) -> bool:
                return alert_rules.matches(device, rule.config)

            def detail(device: Device, rule: AlertRule = rule) -> str:
                return alert_rules.describe(rule.kind, rule.config)

        else:
            # Events are recorded where they happen. There is nothing to look for.
            continue

        for device in devices:
            if holds(device):
                occurrence = raise_state(session, rule, device, detail(device), moment)
                if occurrence is not None:
                    raised.append(occurrence)
            else:
                clear_state(session, rule, device, moment)

    return raised


def _is_quiet(device: Device, rule: AlertRule, now: datetime) -> bool:
    """Has this device been silent for longer than the rule allows?

    ⚠️ **A device that has never checked in is not covered, and that is
    deliberate.** `device_health.enrollment_stalled` already draws this line and
    says why: a device that has *ever* reported is one whose identity works, and
    its silence is a network or power question. One that never has is a
    provisioning failure — a different problem, with a different fix, already
    reported on its own page.

    Conflating them would alert on every device in the fleet the moment a
    threshold was created, because a device that has not enrolled yet has no
    check-in and will not have one until it does.
    """
    from app.services import alert_rules

    if device.enrollment_state is not EnrollmentState.ENROLLED:
        return False
    if device.last_checkin_at is None:
        return False

    last = device.last_checkin_at
    if last.tzinfo is None:
        # Stored naive on some backends. Reading it as what it is beats letting
        # the subtraction raise and take the whole sweep with it.
        last = last.replace(tzinfo=timezone.utc)
    return (now - last) > alert_rules.duration(rule.config)


def _quiet_detail(device: Device, now: datetime) -> str:
    """What to say about a silent device, recorded at the time.

    ⚠️ UTC and absolute, not "3 days ago". The message is read later — possibly
    much later — and a relative age computed when it was written is a number
    that was true once and is misleading for ever after.
    """
    last = device.last_checkin_at
    if last is None:
        return "never checked in"
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    hours = int((now - last).total_seconds() // 3600)
    return f"last checked in {last.isoformat(timespec='minutes')} ({hours}h earlier)"


# --------------------------------------------------------------------------- #
# Telling somebody
# --------------------------------------------------------------------------- #


def pending(session: Session) -> list[AlertOccurrence]:
    """Everything raised that nobody has been told about, oldest first."""
    return list(
        session.scalars(
            select(AlertOccurrence)
            .where(AlertOccurrence.notified_at.is_(None))
            .order_by(AlertOccurrence.raised_at)
        )
    )


def compose(session: Session, occurrences: list[AlertOccurrence]) -> tuple[str, str]:
    """One subject and one body for everything raised. Returns (subject, body).

    ⚠️ **One message, not one per alert, and this is the storm control.** A
    single bad policy push puts two hundred devices out of compliance at once.
    Two hundred emails is the same outcome as none — worse, because the operator
    now has a mailbox to clear before they can start work.
    """
    rules = {
        rule.id: rule
        for rule in session.scalars(select(AlertRule))
    }
    devices = {
        device.id: device
        for device in session.scalars(select(Device))
    }

    lines: list[str] = []
    for occurrence in occurrences:
        rule = rules.get(occurrence.rule_id)
        device = devices.get(occurrence.device_id) if occurrence.device_id else None
        # ⚠️ The serial comes from the occurrence's own detail when the device
        # is gone — which is exactly the disenrolment case, where the record was
        # deleted on purpose and the alert still has to say who it was about.
        who = device.serial_number if device is not None else (occurrence.detail or "a device")
        name = rule.name if rule is not None else "an alert"
        lines.append(f"• {name} — {who}")
        if occurrence.detail and device is not None:
            lines.append(f"    {occurrence.detail}")

    count = len(occurrences)
    subject = f"ATLAS: {count} alert{'' if count == 1 else 's'}"
    body = "\n".join(
        [
            f"{count} alert{'' if count == 1 else 's'} from ATLAS:",
            "",
            *lines,
            "",
            "You are receiving this because your address is on the alert list in",
            "Admin → General.",
        ]
    )
    return subject, body


def notify(
    session: Session,
    settings,
    deliver=None,
    now: datetime | None = None,
) -> int:
    """Tell the recipients about everything raised since last time.

    Returns how many alerts were included. `deliver` is injectable so the suite
    can exercise every path without a mail server — ⚠️ **no test in this
    repository may open a socket to one.**

    ⚠️ **Nothing is marked sent unless the send succeeded.** A mail server
    that is down means the alerts wait for the next sweep. An alert nobody
    received and nobody knows about is worse than no alerting at all, because
    the operator believes they are being watched over.
    """
    from app.services import mail

    outstanding = pending(session)
    if not outstanding:
        return 0

    recipients = [r.address for r in list_recipients(session, include_disabled=False)]
    config = mail.effective_config(session, settings)

    if not recipients or not config.configured:
        # ⚠️ **Discarded, not queued, and the console says so.** The
        # alternative is a backlog that floods the first address ever added with
        # every alert since the deployment was built — a first impression of
        # alerting that teaches somebody to filter it immediately. Admin →
        # General already reads "alerts with nobody to send to are not sent".
        reason = "nobody to send to" if not recipients else "no mail server configured"
        log.warning(
            "discarding %d alert(s): %s", len(outstanding), reason
        )
        _mark_sent(outstanding, _now(now))
        session.flush()
        return 0

    subject, body = compose(session, outstanding)
    send = deliver or mail.deliver
    try:
        send(config, recipients, subject, body)
    except Exception as exc:
        # ⚠️ Left unmarked on purpose, so the next sweep tries again. Logged
        # at warning rather than swallowed: a relay that has been refusing mail
        # for a week is something an operator has to be able to find.
        log.warning("could not send %d alert(s): %s", len(outstanding), exc)
        return 0

    _mark_sent(outstanding, _now(now))
    session.flush()
    log.info("sent %d alert(s) to %d recipient(s)", len(outstanding), len(recipients))
    return len(outstanding)


def _mark_sent(occurrences: list[AlertOccurrence], moment: datetime) -> None:
    for occurrence in occurrences:
        occurrence.notified_at = moment


# --------------------------------------------------------------------------- #
# Rules
# --------------------------------------------------------------------------- #


def list_rules(session: Session) -> list[AlertRule]:
    """Every rule, grouped by kind so the list reads as three sections."""
    return list(
        session.scalars(select(AlertRule).order_by(AlertRule.kind, AlertRule.name))
    )


def add_rule(
    session: Session,
    *,
    kind: str,
    config: dict | None = None,
    name: str = "",
    by: str | None = None,
) -> AlertRule:
    """Save a rule, or explain why it cannot be saved.

    ⚠️ **Duplicates are refused**, and not for tidiness. Two rules watching
    the same thing send two emails about it, which is how a recipient learns
    that ATLAS repeats itself and starts skimming. The duplicate check is on
    what the rule *means* — a 72-hour threshold and a 3-day one are the same
    rule written differently, and both would fire together.
    """
    from app.services import alert_rules

    try:
        cleaned = alert_rules.validate(kind, config)
    except alert_rules.RuleError as exc:
        raise AlertError(str(exc)) from exc

    for existing in list_rules(session):
        if existing.kind != kind:
            continue
        if _same_rule(kind, existing.config, cleaned):
            raise AlertError(
                f"there is already an alert for that: {existing.name!r}"
            )

    label = (name or "").strip() or alert_rules.describe(kind, cleaned)
    rule = AlertRule(kind=kind, name=label[:128], config=cleaned, created_by=by)
    session.add(rule)
    session.flush()
    return rule


def _same_rule(kind: str, left: dict, right: dict) -> bool:
    """Do these two configs watch for the same thing?

    ⚠️ Compared by meaning, not by equality of the stored dict. For a stale
    rule that means the **duration**: 72 hours and 3 days are one rule, and
    saving both would send two emails about one silent tablet.
    """
    from app.services import alert_rules

    if kind == "stale":
        return alert_rules.duration(left) == alert_rules.duration(right)
    if kind == "event":
        return left.get("event") == right.get("event")
    # Custom rules are compared literally: two rules with the same conditions in
    # a different order are, for now, two rules. Ordering them to compare would
    # be a claim that condition order never matters, which is true today and is
    # not the kind of thing to bake in silently.
    return left == right


def set_rule_enabled(session: Session, rule: AlertRule, enabled: bool) -> None:
    """Silence a rule without losing how it was written."""
    rule.enabled = enabled
    session.flush()


def remove_rule(session: Session, rule: AlertRule) -> None:
    session.delete(rule)
    session.flush()


# --------------------------------------------------------------------------- #
# Recipients
# --------------------------------------------------------------------------- #


def set_enabled(session: Session, recipient: AlertRecipient, enabled: bool) -> None:
    """Turn one recipient on or off without losing them.

    ⚠️ The reason this exists next to `remove`. Somebody goes on leave, or an
    address starts bouncing and drowning the relay: they come off the list today
    without the record of who was on it going too.
    """
    recipient.enabled = enabled
    session.flush()


def remove(session: Session, recipient: AlertRecipient) -> None:
    session.delete(recipient)
    session.flush()
