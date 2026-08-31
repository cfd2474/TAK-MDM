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

"""The policy stacking resolver.

A pure function from a set of assignments to one merged, fully-attributed policy.
It takes plain dataclasses rather than ORM objects deliberately: the hardest logic
in the system stays testable without a database, a device, or a web request.

Resolution order, highest precedence first::

    rank DESC, then scope specificity (device > group > tag), then assignment_id

``rank`` is authoritative and specificity only breaks ties — so a deliberately
high-ranked tag policy *can* outrank a device-level one. That is the useful
behaviour (a "quarantine" tag should beat everything), and it is documented here
because the alternative reading is equally plausible and silently different.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.policies.registry import PolicyTypeRegistry, registry as default_registry
from app.policies.strategies import (
    Contribution,
    MergeOutcome,
    SourceRef,
    apply_strategy,
)

_SCOPE_SPECIFICITY = {"device": 3, "group": 2, "tag": 1}


@dataclass(frozen=True)
class PolicySnapshot:
    """An immutable published policy version, flattened for the resolver."""

    policy_id: str
    policy_name: str
    policy_type: str
    version: int
    spec: Mapping[str, Any]


@dataclass(frozen=True)
class AssignmentInput:
    assignment_id: str
    scope: str
    rank: int
    policy: PolicySnapshot

    def source_ref(self) -> SourceRef:
        return SourceRef(
            assignment_id=self.assignment_id,
            policy_id=self.policy.policy_id,
            policy_name=self.policy.policy_name,
            policy_version=self.policy.version,
            scope=self.scope,
            rank=self.rank,
        )


@dataclass(frozen=True)
class Conflict:
    """A value discarded by a strategy with no natural ordering."""

    policy_type: str
    field_name: str
    strategy: str
    winning_value: Any
    winning_source: dict[str, Any] | None
    discarded: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy_type": self.policy_type,
            "field": self.field_name,
            "strategy": self.strategy,
            "winning_value": self.winning_value,
            "winning_source": self.winning_source,
            "discarded": list(self.discarded),
        }


@dataclass(frozen=True)
class EffectivePolicy:
    device_id: str
    values: dict[str, dict[str, Any]] = field(default_factory=dict)
    provenance: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    conflicts: tuple[Conflict, ...] = ()
    considered: tuple[dict[str, Any], ...] = ()

    def explain(self, policy_type: str, field_name: str) -> dict[str, Any] | None:
        """Why does this field hold this value? Returns the provenance record."""
        return self.provenance.get(policy_type, {}).get(field_name)

    def as_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "values": self.values,
            "provenance": self.provenance,
            "conflicts": [c.as_dict() for c in self.conflicts],
            "considered": list(self.considered),
        }


def order_assignments(assignments: Iterable[AssignmentInput]) -> list[AssignmentInput]:
    """Sort into resolution order: highest precedence first, fully deterministic."""
    return sorted(
        assignments,
        key=lambda a: (
            -a.rank,
            -_SCOPE_SPECIFICITY.get(a.scope, 0),
            a.assignment_id,
        ),
    )


def _collect(
    assignments: Sequence[AssignmentInput], field_name: str
) -> list[Contribution]:
    """Gather contributions for one field, skipping policies that do not set it.

    A spec is persisted with ``exclude_unset=True``, so presence of the key means the
    author explicitly set it. An explicit ``null`` is treated as unset — it must not
    drag a merged value down to nothing.
    """
    contributions: list[Contribution] = []
    for assignment in assignments:
        if field_name not in assignment.policy.spec:
            continue
        value = assignment.policy.spec[field_name]
        if value is None:
            continue
        contributions.append(Contribution(value=value, source=assignment.source_ref()))
    return contributions


def _record_conflict(
    policy_type: str, field_name: str, outcome: MergeOutcome
) -> Conflict:
    return Conflict(
        policy_type=policy_type,
        field_name=field_name,
        strategy=outcome.strategy.value,
        winning_value=outcome.value,
        winning_source=outcome.winner.as_dict() if outcome.winner else None,
        discarded=tuple(
            {"value": v, "source": s.as_dict()} for v, s in outcome.overridden
        ),
    )


def resolve(
    device_id: str,
    assignments: Iterable[AssignmentInput],
    *,
    policy_registry: PolicyTypeRegistry | None = None,
) -> EffectivePolicy:
    """Merge stacked assignments into one effective policy with full provenance."""
    reg = policy_registry or default_registry
    ordered = order_assignments(assignments)

    values: dict[str, dict[str, Any]] = {}
    provenance: dict[str, dict[str, dict[str, Any]]] = {}
    conflicts: list[Conflict] = []

    by_type: dict[str, list[AssignmentInput]] = {}
    for assignment in ordered:
        by_type.setdefault(assignment.policy.policy_type, []).append(assignment)

    for policy_type in sorted(by_type):
        definition = reg.get(policy_type)
        type_values: dict[str, Any] = {}
        type_provenance: dict[str, dict[str, Any]] = {}

        for field_name, rule in definition.merge_rules.items():
            contributions = _collect(by_type[policy_type], field_name)
            if not contributions:
                continue  # nobody set it: stays absent rather than defaulted
            outcome = apply_strategy(contributions, rule)
            type_values[field_name] = outcome.value
            type_provenance[field_name] = outcome.as_dict()
            if outcome.conflict:
                conflicts.append(_record_conflict(policy_type, field_name, outcome))

        if type_values:
            values[policy_type] = type_values
            provenance[policy_type] = type_provenance

    return EffectivePolicy(
        device_id=device_id,
        values=values,
        provenance=provenance,
        conflicts=tuple(conflicts),
        considered=tuple(a.source_ref().as_dict() for a in ordered),
    )


def diff_values(
    before: Mapping[str, Mapping[str, Any]], after: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Field-level diff between two effective-policy value maps.

    Drives the pre-publish preview: an operator about to retarget 300 devices sees
    exactly which fields move before anything is written.
    """
    changes: list[dict[str, Any]] = []
    _ABSENT = object()

    for policy_type in sorted(set(before) | set(after)):
        old_fields = before.get(policy_type, {})
        new_fields = after.get(policy_type, {})
        for field_name in sorted(set(old_fields) | set(new_fields)):
            old = old_fields.get(field_name, _ABSENT)
            new = new_fields.get(field_name, _ABSENT)
            if old == new:
                continue
            changes.append(
                {
                    "policy_type": policy_type,
                    "field": field_name,
                    "change": (
                        "added"
                        if old is _ABSENT
                        else "removed"
                        if new is _ABSENT
                        else "changed"
                    ),
                    "before": None if old is _ABSENT else old,
                    "after": None if new is _ABSENT else new,
                }
            )
    return changes
