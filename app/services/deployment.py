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

"""Whether a policy has been deployed yet, and when it will be (W191).

A policy can be built complete — content, versions, device and group targets —
and still not be in force. Three states, carried by two columns:

* **live** — ``pending_deployment`` false. Reaches devices now. Every row that
  predates this feature is here, and the migration keeps it that way.
* **held** — true, ``effective_at`` NULL. Reaches nobody until someone presses
  Deploy.
* **scheduled** — true, ``effective_at`` set. Reaches devices at that moment,
  without anyone pressing anything.

⚠️ **This module is the only place that reads the columns together.** Anywhere
else comparing ``pending_deployment`` to a date is a second definition of "live"
waiting to disagree with this one, and disagreement here is either a policy on
devices that should not have it, or a scheduled deployment that never lands.

⚠️ **Profile sections inherit; they do not decide.** A ``Policy`` with
``profile_id`` set is a tab of a profile, assigned only as part of it, so its own
columns are never set and never consulted — the resolver asks about the
*profile*. Giving a section its own pending state would let one tab of a live
profile silently sit out, which is indistinguishable from a broken merge.

Timeliness is a separate problem, solved in three independent layers. This
module is layer one: a truthful answer to "is it in force *right now*", so that
any recompute is correct no matter what did or did not flip a flag.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Policy, PolicyProfile

log = logging.getLogger(__name__)

#: What :func:`status` can return. Strings rather than an enum because they are a
#: rendering — the console prints them, and nothing branches on them.
LIVE = "live"
HELD = "held"
SCHEDULED = "scheduled"

#: A policy or a profile. Both carry the same three columns and mean the same
#: thing by them, which is the entire reason this module takes either.
Deployable = Policy | PolicyProfile


def _now(now: datetime | None) -> datetime:
    return now if now is not None else datetime.now(timezone.utc)


def is_live(item: Deployable, now: datetime | None = None) -> bool:
    """Is this in force at ``now``?

    ⚠️ **Derived from the clock, not from the flag**, and that is deliberate.
    Something has to clear ``pending_deployment`` when the moment arrives, and
    that something is a background thread — threads die, and hosts are down at
    08:00. Reading the date here means the sweeper decides only *when devices are
    told*, never *what is true*.
    """
    if not item.pending_deployment:
        return True
    return item.effective_at is not None and item.effective_at <= _now(now)


def status(item: Deployable, now: datetime | None = None) -> str:
    """``LIVE``, ``HELD`` or ``SCHEDULED``, for the console to render.

    A scheduled policy whose moment has passed reports ``LIVE`` before the
    sweeper has touched it, because it is: :func:`is_live` says so and the
    resolver agrees. Reporting ``SCHEDULED`` there would tell an operator their
    deployment had not happened while devices were already applying it.
    """
    if is_live(item, now):
        return LIVE
    return SCHEDULED if item.effective_at is not None else HELD


def due(session: Session, now: datetime | None = None) -> list[Deployable]:
    """Everything whose scheduled moment has arrived and is still flagged pending.

    The query is what makes the sweeper idempotent: :func:`activate` clears the
    flag, so a swept item cannot come back. Nothing here depends on the sweeper
    having run recently, or at all — a server down for a week activates the
    week's worth on the way back up, in one pass.
    """
    moment = _now(now)
    found: list[Deployable] = []
    for model in (Policy, PolicyProfile):
        found.extend(
            session.scalars(
                select(model).where(
                    model.pending_deployment.is_(True),
                    model.effective_at.is_not(None),
                    model.effective_at <= moment,
                )
            )
        )
    return found


def next_transition(
    session: Session,
    device_ids: Iterable[uuid.UUID] | None = None,
    now: datetime | None = None,
) -> datetime | None:
    """The earliest moment after ``now`` at which something goes live, or None.

    Layer two of the three. The cache stores this so that a read *after* the
    moment recomputes even though nothing marked it stale — without it,
    :func:`is_live` is never consulted again, because a payload computed at 07:00
    is not stale at 08:00 and the device is served yesterday's answer for good.

    ⚠️ Fleet-wide rather than per-device, and the imprecision is the point.
    Narrowing it to the policies that reach one device means rebuilding the
    resolver's target expansion somewhere it can drift from the original. The
    cost of being wide is that every device recomputes once at a moment when
    *some* policy landed — and a recompute that finds nothing moved does not bump
    ``state_version`` and wakes nobody. ``device_ids`` is accepted and ignored so
    that narrowing it later is not a signature change at every call site.
    """
    moment = _now(now)
    soonest: datetime | None = None
    for model in (Policy, PolicyProfile):
        found = session.scalar(
            select(model.effective_at)
            .where(
                model.pending_deployment.is_(True),
                model.effective_at.is_not(None),
                model.effective_at > moment,
                model.archived_at.is_(None),
            )
            .order_by(model.effective_at)
            .limit(1)
        )
        if found is not None and (soonest is None or found < soonest):
            soonest = found
    return soonest


def activate(session: Session, item: Deployable, now: datetime | None = None) -> bool:
    """Put it in force, and tell the devices it reaches.

    Returns whether anything changed, so a caller sweeping a list can report a
    count without counting no-ops.

    ⚠️ The wake is the whole reason this is a function rather than two
    assignments. Devices park on a long poll; clearing the flag without marking
    their cache stale means the deployment lands whenever they next happen to
    check in, which is the difference between "goes live at 08:00" and "goes live
    some time after 08:00".
    """
    if not item.pending_deployment:
        return False
    item.pending_deployment = False
    item.activated_at = _now(now)
    _invalidate(session, item)
    log.info(
        "%s %r is now live%s",
        _kind(item),
        item.name,
        f", scheduled for {item.effective_at.isoformat()}" if item.effective_at else "",
    )
    return True


def hold(
    session: Session,
    item: Deployable,
    effective_at: datetime | None = None,
    now: datetime | None = None,
) -> None:
    """Take it out of force, optionally naming when it should come back.

    ⚠️ Holding something already live **retracts it from devices**, which is why
    this invalidates unconditionally rather than only on a state change: an
    operator moving a held policy from Tuesday to Friday has changed what the
    fleet does on Wednesday, and no caller can be relied on to notice that.

    Archiving is the permanent form of this and stays the right action for a
    policy that is finished with. This is the reversible one.
    """
    item.pending_deployment = True
    item.effective_at = effective_at
    # Cleared because it is about to be untrue: the next activation stamps its
    # own. Leaving the old one would have a rescheduled policy report that it
    # went live at a moment when it did not.
    item.activated_at = None
    if effective_at is not None and effective_at <= _now(now):
        # ⚠️ Not refused. A moment in the past is how "deploy immediately" comes
        # out of a form that only offers a date, and `is_live` already reads it
        # as live — refusing it here would disagree with the resolver.
        log.info(
            "%s %r was scheduled for a moment that has passed, so it stays live",
            _kind(item),
            item.name,
        )
    _invalidate(session, item)


#: How the console renders an instant it is confirming back to the operator.
_ECHO = "%a %d %b %Y, %H:%M"


def choose(
    session: Session,
    item: Deployable,
    state: str,
    when_text: str = "",
    now: datetime | None = None,
) -> str:
    """Apply a deployment choice made in the console, and say what was understood.

    Returns a sentence for the page to echo. ⚠️ **The echo is not decoration.**
    The operator types a local wall-clock time and the system stores an instant;
    a zone misconfigured by seven hours produces a deployment that lands
    overnight, and nothing else in the interface would ever say so. Both
    renderings go back, so the mistake is visible at the moment it is made
    rather than the morning after.

    Raises ``ValueError`` if a schedule was asked for and the date is unreadable.
    """
    from app.services import clock

    moment = _now(now)
    if state == LIVE:
        if activate(session, item, moment):
            return f"{item.name} is live now."
        return f"{item.name} was already live."

    if state == HELD:
        hold(session, item, None, now=moment)
        return (
            f"{item.name} is held. It reaches no device until you deploy it."
        )

    if state != SCHEDULED:
        raise ValueError(f"{state!r} is not a deployment state")

    tz = clock.configured(session)
    when = clock.from_local(when_text, tz)
    hold(session, item, when, now=moment)

    local = clock.format(when, tz, _ECHO)
    zone = clock.label(tz, [when])
    # utc-by-design: the whole point of this sentence is showing the operator
    # both renderings of the same instant. The local one is what they typed; the
    # UTC one is what was stored, and a console timezone set wrongly is only
    # visible by putting the two side by side.
    utc = when.strftime(_ECHO)
    if when <= moment:
        # ⚠️ Said plainly rather than treated as an error. `is_live` reads a past
        # date as live and the resolver agrees, so the console must not claim a
        # deployment is still coming.
        return (
            f"{local} {zone} ({utc} UTC) has already passed, "
            f"so {item.name} is live now."
        )
    return f"{item.name} deploys at {local} {zone} ({utc} UTC)."


def sweep(session: Session, now: datetime | None = None) -> int:
    """Activate everything that has come due. Returns how many."""
    return sum(1 for item in due(session, now) if activate(session, item, now))


def _kind(item: Deployable) -> str:
    return "profile" if isinstance(item, PolicyProfile) else "policy"


def _invalidate(session: Session, item: Deployable) -> None:
    # Imported here rather than at module scope: `effective_policy` asks this
    # module whether a policy is live, so a top-level import is a cycle.
    from app.services import effective_policy as eff

    if isinstance(item, PolicyProfile):
        eff.invalidate_for_profile(session, item.id)
    else:
        eff.invalidate_for_policy(session, item.id)
