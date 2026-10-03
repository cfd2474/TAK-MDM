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

"""Per-field merge strategies.

Every strategy is a pure function over an ordered list of contributions and returns
a :class:`MergeOutcome` carrying not just the winning value but *why* it won and
what it beat. Provenance is produced here, at the point of decision — it cannot be
reconstructed afterwards (D4).

Contributions arrive already sorted by the resolver: highest precedence first.

The distinction between ``overridden`` and ``conflict`` matters:

* **overridden** — a value lost to a strategy with deterministic, intended
  semantics (``MAX`` picked the larger number). Informational.
* **conflict** — a value was discarded by a strategy with no natural ordering
  (``HIGHEST_RANK`` had to pick arbitrarily between two different wallpapers).
  The operator probably did not intend this and must be told.
"""

from __future__ import annotations

import enum
import json
from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass
from typing import Any


class MergeStrategy(str, enum.Enum):
    MOST_RESTRICTIVE = "most_restrictive"
    MAX = "max"
    MIN = "min"
    UNION = "union"
    INTERSECT = "intersect"
    MERGE_BY_KEY = "merge_by_key"
    HIGHEST_RANK = "highest_rank"


@dataclass(frozen=True)
class Merge:
    """Field annotation declaring how a field composes when policies stack.

    Attached via ``Annotated[int | None, Merge(MergeStrategy.MAX)]`` so the schema
    *is* the merge contract and the two cannot drift apart (D3).
    """

    strategy: MergeStrategy
    key: str | None = None  # required by MERGE_BY_KEY
    note: str | None = None


@dataclass(frozen=True)
class SourceRef:
    """Identifies the assignment/policy a value came from."""

    assignment_id: str
    policy_id: str
    policy_name: str
    policy_version: int
    scope: str
    rank: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "assignment_id": self.assignment_id,
            "policy_id": self.policy_id,
            "policy_name": self.policy_name,
            "policy_version": self.policy_version,
            "scope": self.scope,
            "rank": self.rank,
        }


@dataclass(frozen=True)
class Contribution:
    value: Any
    source: SourceRef


@dataclass(frozen=True)
class MergeOutcome:
    value: Any
    strategy: MergeStrategy
    contributors: tuple[SourceRef, ...]
    winner: SourceRef | None = None
    overridden: tuple[tuple[Any, SourceRef], ...] = ()
    conflict: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "strategy": self.strategy.value,
            "source": self.winner.as_dict() if self.winner else None,
            "contributors": [s.as_dict() for s in self.contributors],
            "overridden": [
                {"value": v, "source": s.as_dict()} for v, s in self.overridden
            ],
            "conflict": self.conflict,
        }


class MergeError(ValueError):
    """Raised when a strategy is applied to data it cannot handle."""


# --------------------------------------------------------------------------- #
# Strategy implementations
# --------------------------------------------------------------------------- #

StrategyFn = Callable[[Sequence[Contribution], Merge], MergeOutcome]


def _sources(contributions: Sequence[Contribution]) -> tuple[SourceRef, ...]:
    return tuple(c.source for c in contributions)


def _losers(
    contributions: Sequence[Contribution], winning_value: Any
) -> tuple[tuple[Any, SourceRef], ...]:
    return tuple((c.value, c.source) for c in contributions if c.value != winning_value)


def _merge_most_restrictive(
    contributions: Sequence[Contribution], cfg: Merge
) -> MergeOutcome:
    """Logical AND over 'allow' flags: a single ``False`` denies."""
    for c in contributions:
        if not isinstance(c.value, bool):
            raise MergeError(
                f"MOST_RESTRICTIVE requires bool values, got {type(c.value).__name__}"
            )
    value = all(c.value for c in contributions)
    # The winner is whoever actually decided it: the first denier, else the top-ranked.
    winner = next((c.source for c in contributions if not c.value), contributions[0].source)
    return MergeOutcome(
        value=value,
        strategy=MergeStrategy.MOST_RESTRICTIVE,
        contributors=_sources(contributions),
        winner=winner,
        overridden=_losers(contributions, value),
    )


def _merge_extremum(
    contributions: Sequence[Contribution], cfg: Merge, *, take_max: bool
) -> MergeOutcome:
    picker = max if take_max else min
    value = picker(c.value for c in contributions)
    winner = next(c.source for c in contributions if c.value == value)
    return MergeOutcome(
        value=value,
        strategy=MergeStrategy.MAX if take_max else MergeStrategy.MIN,
        contributors=_sources(contributions),
        winner=winner,
        overridden=_losers(contributions, value),
    )


def _merge_max(contributions: Sequence[Contribution], cfg: Merge) -> MergeOutcome:
    return _merge_extremum(contributions, cfg, take_max=True)


def _merge_min(contributions: Sequence[Contribution], cfg: Merge) -> MergeOutcome:
    return _merge_extremum(contributions, cfg, take_max=False)


def _as_sequence(value: Any, strategy: MergeStrategy) -> Sequence[Hashable]:
    if not isinstance(value, (list, tuple)):
        raise MergeError(f"{strategy.value} requires list values, got {type(value).__name__}")
    return value


def _dedupe_key(item: Any) -> Hashable:
    """A hashable stand-in for ``item``, so a list of dicts can be unioned.

    UNION was written for lists of scalars — package names, SSIDs — and used the
    items themselves as set members. A list of objects (a data-usage threshold,
    say) then failed with a bare ``TypeError: unhashable type: 'dict'`` from
    inside the merge, which reads as a server fault rather than a policy one.

    Sorted-key JSON rather than ``repr``: two equal rules written in a different
    field order are the same rule, and should collapse to one.
    """
    if isinstance(item, Hashable):
        return item
    return json.dumps(item, sort_keys=True, default=str)


def _merge_union(contributions: Sequence[Contribution], cfg: Merge) -> MergeOutcome:
    """Set union, preserving first-seen order for deterministic output."""
    merged: list[Any] = []
    seen: set[Hashable] = set()
    for c in contributions:
        for item in _as_sequence(c.value, MergeStrategy.UNION):
            key = _dedupe_key(item)
            if key not in seen:
                seen.add(key)
                merged.append(item)
    # Aggregate strategies have no single winner; every contributor shaped the result.
    return MergeOutcome(
        value=merged,
        strategy=MergeStrategy.UNION,
        contributors=_sources(contributions),
    )


def _merge_intersect(contributions: Sequence[Contribution], cfg: Merge) -> MergeOutcome:
    """Only what *every* contributor permits. Order follows the highest-precedence list."""
    common: set[Hashable] | None = None
    for c in contributions:
        items = set(_as_sequence(c.value, MergeStrategy.INTERSECT))
        common = items if common is None else (common & items)
    ordered_source = _as_sequence(contributions[0].value, MergeStrategy.INTERSECT)
    merged = [item for item in ordered_source if item in (common or set())]
    dropped = tuple(
        (c.value, c.source)
        for c in contributions
        if set(_as_sequence(c.value, MergeStrategy.INTERSECT)) != set(merged)
    )
    return MergeOutcome(
        value=merged,
        strategy=MergeStrategy.INTERSECT,
        contributors=_sources(contributions),
        overridden=dropped,
    )


def _merge_by_key(contributions: Sequence[Contribution], cfg: Merge) -> MergeOutcome:
    """Union of object lists keyed by ``cfg.key``; higher precedence wins collisions."""
    if not cfg.key:
        raise MergeError("MERGE_BY_KEY requires a key")

    merged: dict[Any, Any] = {}
    owner: dict[Any, SourceRef] = {}
    overridden: list[tuple[Any, SourceRef]] = []
    conflict = False

    for c in contributions:
        for item in _as_sequence(c.value, MergeStrategy.MERGE_BY_KEY):
            if not isinstance(item, dict) or cfg.key not in item:
                raise MergeError(f"MERGE_BY_KEY items must be dicts containing {cfg.key!r}")
            identity = item[cfg.key]
            if identity not in merged:
                merged[identity] = item
                owner[identity] = c.source
            elif merged[identity] != item:
                # Same entity described differently by two policies — arbitrary pick.
                overridden.append((item, c.source))
                conflict = True

    return MergeOutcome(
        value=list(merged.values()),
        strategy=MergeStrategy.MERGE_BY_KEY,
        contributors=_sources(contributions),
        overridden=tuple(overridden),
        conflict=conflict,
    )


def _merge_highest_rank(contributions: Sequence[Contribution], cfg: Merge) -> MergeOutcome:
    """Top-ranked contributor wins. Any differing value below is a real conflict."""
    winning = contributions[0]
    losers = _losers(contributions, winning.value)
    return MergeOutcome(
        value=winning.value,
        strategy=MergeStrategy.HIGHEST_RANK,
        contributors=_sources(contributions),
        winner=winning.source,
        overridden=losers,
        conflict=bool(losers),
    )


STRATEGY_FUNCTIONS: dict[MergeStrategy, StrategyFn] = {
    MergeStrategy.MOST_RESTRICTIVE: _merge_most_restrictive,
    MergeStrategy.MAX: _merge_max,
    MergeStrategy.MIN: _merge_min,
    MergeStrategy.UNION: _merge_union,
    MergeStrategy.INTERSECT: _merge_intersect,
    MergeStrategy.MERGE_BY_KEY: _merge_by_key,
    MergeStrategy.HIGHEST_RANK: _merge_highest_rank,
}


def apply_strategy(contributions: Sequence[Contribution], cfg: Merge) -> MergeOutcome:
    """Dispatch to the configured strategy. Requires at least one contribution."""
    if not contributions:
        raise MergeError("cannot merge an empty contribution set")
    try:
        fn = STRATEGY_FUNCTIONS[cfg.strategy]
    except KeyError:  # pragma: no cover - guarded by the enum
        raise MergeError(f"unknown merge strategy {cfg.strategy!r}") from None
    return fn(contributions, cfg)
