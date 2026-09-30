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

"""What an alert rule may say, and what it may not (W195).

Three kinds, each validating its own config, so a fourth needs a validator here
and no changes anywhere else — the same shape as the policy type registry.

⚠️ **The custom kind is an allowlist, not an expression language.** A rule is
*field, operator, value* over a fixed set of device columns, each declaring its
type and the operators that type permits. Nothing is evaluated, nothing is
parsed, and no column outside the list can be named. A real expression language
is a far larger feature with a far larger attack surface, and nothing asked for
one.

⚠️ **Everything is refused at save time, where the operator is looking at it.**
A rule that cannot fire, or fires on everything, is invisible once saved: it
either never alerts or alerts constantly, and both read as "the alerting is
broken" rather than "that rule is wrong".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable

from app.db.models import ComplianceStatus, EnrollmentState


class RuleError(Exception):
    """A rule cannot be saved as written."""


# --------------------------------------------------------------------------- #
# The events a rule can be attached to
# --------------------------------------------------------------------------- #

#: The four the operator asked for, and what the console calls each.
#:
#: ⚠️ Keys are stored in the database, so they are the stable half. Renaming a
#: label is a wording change; renaming a key orphans every rule using it.
EVENTS: dict[str, str] = {
    "device_enrolled": "A device finished enrolling",
    "device_disenrolled": "A device was disenrolled",
    "device_out_of_compliance": "A device stopped applying its policy",
    "device_breached": "A device was put into breach mode",
}


# --------------------------------------------------------------------------- #
# How long is "hasn't checked in"
# --------------------------------------------------------------------------- #

#: The units a threshold may be written in, and what each is worth.
#:
#: ⚠️ Three units rather than one, because the alternative is arithmetic in the
#: operator's head: 14 days is 20160 minutes, and a list of thresholds in
#: minutes is a list nobody can read at a glance during an incident.
UNITS: dict[str, timedelta] = {
    "minutes": timedelta(minutes=1),
    "hours": timedelta(hours=1),
    "days": timedelta(days=1),
}

#: Shortest threshold worth allowing.
#:
#: ⚠️ Not defensive tidiness. A device checks in on its own schedule, and a
#: threshold shorter than that interval is true of every healthy device all the
#: time — the whole fleet alerting for ever, which reads as a broken system
#: rather than a mis-set number.
MIN_STALE = timedelta(minutes=15)


def duration(config: dict[str, Any]) -> timedelta:
    """The span a stale rule means."""
    return UNITS[config["unit"]] * int(config["amount"])


# --------------------------------------------------------------------------- #
# The device fields a custom rule may name
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Field:
    """One device column a rule may ask about."""

    name: str
    label: str
    kind: str  # number | text | bool | choice
    choices: tuple[str, ...] = ()


#: ⚠️ **An allowlist, and the reason is not only safety.** Every field here is
#: something an operator can see on a device page and reason about. A rule over
#: `state_version` or a primary key would be syntactically fine and meaningless
#: — and a meaningless rule that never fires is indistinguishable from alerting
#: that does not work.
FIELDS: tuple[Field, ...] = (
    Field("battery_level", "Battery level (%)", "number"),
    Field("battery_charging", "Battery charging", "bool"),
    Field("sdk_int", "Android API level", "number"),
    Field("agent_version_code", "Agent version code", "number"),
    Field("os_version", "Android version", "text"),
    Field("atak_version", "ATAK version", "text"),
    Field("model", "Model", "text"),
    Field("name", "Device name", "text"),
    Field("serial_number", "Serial number", "text"),
    Field("has_telephony", "Has a cellular radio", "bool"),
    Field(
        "enrollment_state",
        "Enrolment state",
        "choice",
        tuple(s.value for s in EnrollmentState),
    ),
    Field(
        "compliance_status",
        "Compliance",
        "choice",
        tuple(s.value for s in ComplianceStatus),
    ),
)

FIELDS_BY_NAME = {f.name: f for f in FIELDS}

#: Which comparisons each kind of field permits, and what to call them.
#:
#: ⚠️ Per kind, not one list for everything. "Less than" over a model name would
#: compare strings alphabetically and answer something nobody meant, which is
#: worse than refusing: it produces a rule that fires on the wrong devices
#: rather than one that visibly does not work.
OPERATORS: dict[str, dict[str, str]] = {
    "number": {
        "lt": "is less than",
        "lte": "is at most",
        "gt": "is more than",
        "gte": "is at least",
        "eq": "is",
        "ne": "is not",
    },
    "text": {"eq": "is", "ne": "is not", "contains": "contains"},
    "bool": {"is": "is"},
    "choice": {"eq": "is", "ne": "is not"},
}

#: What a `bool` condition accepts as its value.
BOOL_VALUES = ("true", "false")

#: Most conditions one custom rule may carry.
#:
#: ⚠️ A cap rather than no limit. Conditions are ANDed, so a long rule is one
#: that fires on fewer and fewer devices until it fires on none — and a rule
#: that silently matches nothing is the failure this whole module is shaped to
#: avoid. Ten is far past anything legible.
MAX_CONDITIONS = 10


# --------------------------------------------------------------------------- #
# Validation, per kind
# --------------------------------------------------------------------------- #


def _validate_event(config: dict[str, Any]) -> dict[str, Any]:
    event = str(config.get("event") or "").strip()
    if event not in EVENTS:
        raise RuleError(
            f"{event or 'that'!r} is not something ATLAS can tell you about. "
            f"Choose one of: {', '.join(sorted(EVENTS))}"
        )
    return {"event": event}


def _validate_stale(config: dict[str, Any]) -> dict[str, Any]:
    unit = str(config.get("unit") or "").strip()
    if unit not in UNITS:
        raise RuleError(f"the unit must be one of {', '.join(UNITS)}")
    try:
        amount = int(str(config.get("amount")).strip())
    except (TypeError, ValueError):
        raise RuleError("how long must be a whole number") from None
    if amount <= 0:
        raise RuleError("how long must be more than zero")

    span = UNITS[unit] * amount
    if span < MIN_STALE:
        # ⚠️ Named with the consequence, not just the limit. "Minimum 15
        # minutes" tells an operator what to type; this tells them why the
        # number they chose would have alerted on every healthy device.
        raise RuleError(
            f"{amount} {unit} is shorter than devices check in, so every device "
            f"would alert all the time. Use at least {int(MIN_STALE.total_seconds() // 60)} minutes."
        )
    return {"amount": amount, "unit": unit}


def _validate_custom(config: dict[str, Any]) -> dict[str, Any]:
    raw = config.get("conditions")
    if not isinstance(raw, list) or not raw:
        # ⚠️ A rule with no conditions matches every device. Refused rather than
        # saved, because "alert me about everything, for ever" is never what
        # somebody meant to build and is indistinguishable from a bug.
        raise RuleError("a custom alert needs at least one condition")
    if len(raw) > MAX_CONDITIONS:
        raise RuleError(f"a custom alert may have at most {MAX_CONDITIONS} conditions")

    cleaned: list[dict[str, Any]] = []
    for condition in raw:
        if not isinstance(condition, dict):
            raise RuleError("each condition must name a field, a test and a value")
        cleaned.append(_validate_condition(condition))
    return {"conditions": cleaned}


def _validate_condition(condition: dict[str, Any]) -> dict[str, Any]:
    name = str(condition.get("field") or "").strip()
    field = FIELDS_BY_NAME.get(name)
    if field is None:
        raise RuleError(
            f"{name or 'that'!r} is not a device field alerts can read. "
            f"Choose one of: {', '.join(sorted(FIELDS_BY_NAME))}"
        )

    op = str(condition.get("op") or "").strip()
    permitted = OPERATORS[field.kind]
    if op not in permitted:
        raise RuleError(
            f"{field.label} cannot be tested with {op or 'that'!r}. "
            f"Try: {', '.join(sorted(permitted))}"
        )

    value = str(condition.get("value") if condition.get("value") is not None else "").strip()
    return {"field": name, "op": op, "value": _validate_value(field, value)}


def _validate_value(field: Field, value: str) -> str:
    """Check the value against the field's own type.

    ⚠️ Stored as text — the config is JSON and a number typed into a form arrives
    as a string either way — but checked as the type the field really is. A
    battery level of "twenty" would compare as a string against an integer
    column and match nothing, silently.
    """
    if field.kind == "number":
        try:
            int(value)
        except ValueError:
            raise RuleError(
                f"{field.label} is a number, so {value or 'that'!r} cannot be compared to it"
            ) from None
        return str(int(value))

    if field.kind == "bool":
        if value.lower() not in BOOL_VALUES:
            raise RuleError(f"{field.label} is yes or no, so it must be true or false")
        return value.lower()

    if field.kind == "choice":
        if value not in field.choices:
            raise RuleError(
                f"{field.label} must be one of: {', '.join(field.choices)}"
            )
        return value

    if not value:
        # ⚠️ Text specifically: an empty string would match every device whose
        # field is empty, which for `atak_version` is every device that has not
        # reported one. Almost never what was meant, and impossible to spot in a
        # list of rules.
        raise RuleError(f"{field.label} needs something to compare against")
    return value


# --------------------------------------------------------------------------- #
# Deciding whether a device matches
# --------------------------------------------------------------------------- #


def matches(device: Any, config: dict[str, Any]) -> bool:
    """Does this device satisfy every condition of a custom rule?

    ⚠️ **Conditions are ANDed**, which is why an empty list is refused at
    save time: `all([])` is True, and a rule with no conditions would match the
    entire fleet.
    """
    conditions = config.get("conditions") or []
    return bool(conditions) and all(
        _condition_matches(device, condition) for condition in conditions
    )


def _condition_matches(device: Any, condition: dict[str, Any]) -> bool:
    field = FIELDS_BY_NAME.get(condition.get("field", ""))
    if field is None:
        # A rule naming a field that has since left the allowlist. Matching
        # nothing is the safe reading: the alternative is alerting on a
        # condition nobody can see the meaning of any more.
        return False

    actual = getattr(device, field.name, None)
    if actual is None:
        # ⚠️ **An absent value never matches, whatever the operator.** This is
        # the decision that keeps `is not` from flooding: a device that has not
        # reported its battery is not a device whose battery "is not 20", and
        # treating absence as a value would alert on every device that has not
        # checked in yet — which is most of a fleet, most of the time.
        return False

    op = condition.get("op", "")
    value = condition.get("value", "")

    if field.kind == "number":
        return _compare_number(actual, op, value)
    if field.kind == "bool":
        return bool(actual) is (value == "true")
    if field.kind == "choice":
        current = getattr(actual, "value", actual)
        return current == value if op == "eq" else current != value
    return _compare_text(str(actual), op, value)


def _compare_number(actual: Any, op: str, value: str) -> bool:
    try:
        left, right = int(actual), int(value)
    except (TypeError, ValueError):
        return False
    return {
        "lt": left < right,
        "lte": left <= right,
        "gt": left > right,
        "gte": left >= right,
        "eq": left == right,
        "ne": left != right,
    }.get(op, False)


def _compare_text(actual: str, op: str, value: str) -> bool:
    """⚠️ Case-insensitively, deliberately.

    Model names, Android versions and device names are typed by people and read
    by people. A rule that misses `SM-X520` because the operator wrote
    `sm-x520` is a rule that silently covers nothing, and silence is this
    feature's worst failure mode.
    """
    left, right = actual.casefold(), value.casefold()
    if op == "eq":
        return left == right
    if op == "ne":
        return left != right
    if op == "contains":
        return right in left
    return False


#: kind -> validator. The registry, and the whole extension point.
VALIDATORS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "event": _validate_event,
    "stale": _validate_stale,
    "custom": _validate_custom,
}

KINDS = tuple(VALIDATORS)


def validate(kind: str, config: dict[str, Any] | None) -> dict[str, Any]:
    """Normalise and check one rule's config, or explain why it cannot be saved."""
    validator = VALIDATORS.get(kind)
    if validator is None:
        raise RuleError(f"{kind!r} is not a kind of alert")
    return validator(dict(config or {}))


def describe(kind: str, config: dict[str, Any]) -> str:
    """One line saying what this rule watches for, for a list of rules.

    ⚠️ Built from the stored config rather than remembered from the form. A
    description saved alongside would drift the first time a rule was edited,
    and a list of rules whose descriptions are stale is worse than a list with
    none.
    """
    if kind == "event":
        return EVENTS.get(config.get("event", ""), "an event")
    if kind == "stale":
        amount, unit = config.get("amount"), config.get("unit")
        return f"No check-in for {amount} {unit}"
    if kind == "custom":
        parts = []
        for condition in config.get("conditions", []):
            field = FIELDS_BY_NAME.get(condition.get("field", ""))
            label = field.label if field else condition.get("field", "?")
            kinds = OPERATORS.get(field.kind, {}) if field else {}
            op = kinds.get(condition.get("op", ""), condition.get("op", "?"))
            parts.append(f"{label} {op} {condition.get('value', '')}".strip())
        return " and ".join(parts)
    return kind
