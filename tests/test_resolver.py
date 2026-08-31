"""Resolver tests.

The resolver is a pure function, so these tests need no database, no fixtures, and
no device — which is exactly why the resolver was built that way.
"""

from __future__ import annotations

import itertools
from typing import Any

import pytest

from app.policies.resolver import (
    AssignmentInput,
    PolicySnapshot,
    diff_values,
    order_assignments,
    resolve,
)
from app.policies.strategies import (
    Contribution,
    Merge,
    MergeError,
    MergeStrategy,
    SourceRef,
    apply_strategy,
)

_ids = itertools.count(1)


def make_assignment(
    policy_type: str,
    spec: dict[str, Any],
    *,
    rank: int = 0,
    scope: str = "device",
    name: str | None = None,
    assignment_id: str | None = None,
    version: int = 1,
) -> AssignmentInput:
    n = next(_ids)
    return AssignmentInput(
        assignment_id=assignment_id or f"assign-{n:04d}",
        scope=scope,
        rank=rank,
        policy=PolicySnapshot(
            policy_id=f"policy-{n:04d}",
            policy_name=name or f"Policy {n}",
            policy_type=policy_type,
            version=version,
            spec=spec,
        ),
    )


# --------------------------------------------------------------------------- #
# Ordering
# --------------------------------------------------------------------------- #


def test_rank_dominates_scope_specificity():
    """A high-ranked tag policy outranks a device policy. Documented, deliberate."""
    tag = make_assignment("PASSWORD", {"min_length": 12}, rank=100, scope="tag")
    device = make_assignment("PASSWORD", {"min_length": 4}, rank=10, scope="device")

    assert [a.scope for a in order_assignments([device, tag])] == ["tag", "device"]


def test_scope_specificity_breaks_rank_ties():
    tag = make_assignment("PASSWORD", {}, rank=5, scope="tag")
    group = make_assignment("PASSWORD", {}, rank=5, scope="group")
    device = make_assignment("PASSWORD", {}, rank=5, scope="device")

    ordered = order_assignments([tag, group, device])
    assert [a.scope for a in ordered] == ["device", "group", "tag"]


def test_ordering_is_total_and_stable():
    """Equal rank and scope still resolve deterministically, via assignment_id."""
    a = make_assignment("PASSWORD", {}, rank=1, scope="group", assignment_id="bbb")
    b = make_assignment("PASSWORD", {}, rank=1, scope="group", assignment_id="aaa")

    assert [x.assignment_id for x in order_assignments([a, b])] == ["aaa", "bbb"]
    assert [x.assignment_id for x in order_assignments([b, a])] == ["aaa", "bbb"]


# --------------------------------------------------------------------------- #
# Strategies
# --------------------------------------------------------------------------- #


def test_most_restrictive_single_denial_wins():
    permissive = make_assignment(
        "RESTRICTIONS", {"allow_camera": True}, rank=50, name="Baseline"
    )
    strict = make_assignment(
        "RESTRICTIONS", {"allow_camera": False}, rank=10, name="Secure Area"
    )

    result = resolve("dev-1", [permissive, strict])

    assert result.values["RESTRICTIONS"]["allow_camera"] is False
    # The denier is credited as the source even though it ranked lower.
    assert result.explain("RESTRICTIONS", "allow_camera")["source"]["policy_name"] == "Secure Area"


def test_most_restrictive_all_allow():
    a = make_assignment("RESTRICTIONS", {"allow_bluetooth": True}, rank=1)
    b = make_assignment("RESTRICTIONS", {"allow_bluetooth": True}, rank=2)

    assert resolve("dev-1", [a, b]).values["RESTRICTIONS"]["allow_bluetooth"] is True


def test_max_picks_strictest_length_regardless_of_rank():
    weak = make_assignment("PASSWORD", {"min_length": 4}, rank=100, name="Convenience")
    strong = make_assignment("PASSWORD", {"min_length": 10}, rank=1, name="Hardened")

    result = resolve("dev-1", [weak, strong])
    record = result.explain("PASSWORD", "min_length")

    assert result.values["PASSWORD"]["min_length"] == 10
    assert record["source"]["policy_name"] == "Hardened"
    assert record["strategy"] == "max"
    assert [o["value"] for o in record["overridden"]] == [4]


def test_min_picks_shortest_timeout():
    a = make_assignment("PASSWORD", {"lock_timeout_seconds": 600}, rank=9)
    b = make_assignment("PASSWORD", {"lock_timeout_seconds": 60}, rank=1)

    assert resolve("dev-1", [a, b]).values["PASSWORD"]["lock_timeout_seconds"] == 60


def test_union_accumulates_blocklists_without_duplicates():
    a = make_assignment("APP_CATALOG", {"blocked_packages": ["com.tiktok", "com.game"]}, rank=5)
    b = make_assignment("APP_CATALOG", {"blocked_packages": ["com.game", "com.vpn"]}, rank=1)

    result = resolve("dev-1", [a, b])

    assert result.values["APP_CATALOG"]["blocked_packages"] == [
        "com.tiktok",
        "com.game",
        "com.vpn",
    ]
    # Aggregate merges have no single winner; every contributor is credited.
    record = result.explain("APP_CATALOG", "blocked_packages")
    assert record["source"] is None
    assert len(record["contributors"]) == 2


def test_intersect_narrows_allowlists_to_the_overlap():
    a = make_assignment(
        "APP_CATALOG", {"allowed_packages": ["com.atak", "com.maps", "com.chat"]}, rank=5
    )
    b = make_assignment("APP_CATALOG", {"allowed_packages": ["com.atak", "com.chat"]}, rank=1)

    result = resolve("dev-1", [a, b])
    assert result.values["APP_CATALOG"]["allowed_packages"] == ["com.atak", "com.chat"]


def test_intersect_can_produce_an_empty_allowlist():
    """R4: the counter-intuitive case operators must be warned about."""
    a = make_assignment("APP_CATALOG", {"allowed_packages": ["com.atak"]}, rank=5)
    b = make_assignment("APP_CATALOG", {"allowed_packages": ["com.chat"]}, rank=1)

    assert resolve("dev-1", [a, b]).values["APP_CATALOG"]["allowed_packages"] == []


def test_merge_by_key_unions_apps_and_high_rank_wins_collisions():
    a = make_assignment(
        "APP_CATALOG",
        {"required_apps": [{"package_name": "com.atak", "min_version_code": 500}]},
        rank=50,
        name="ATAK Pinned",
    )
    b = make_assignment(
        "APP_CATALOG",
        {
            "required_apps": [
                {"package_name": "com.atak", "min_version_code": 100},
                {"package_name": "com.plugin", "min_version_code": 3},
            ]
        },
        rank=10,
    )

    result = resolve("dev-1", [a, b])
    apps = {app["package_name"]: app for app in result.values["APP_CATALOG"]["required_apps"]}

    assert apps["com.atak"]["min_version_code"] == 500  # higher rank won
    assert apps["com.plugin"]["min_version_code"] == 3  # unioned in
    assert len(result.conflicts) == 1
    assert result.conflicts[0].field_name == "required_apps"


def test_merge_by_key_identical_entries_are_not_a_conflict():
    entry = {"package_name": "com.atak", "min_version_code": 500, "auto_update": True}
    a = make_assignment("APP_CATALOG", {"required_apps": [entry]}, rank=50)
    b = make_assignment("APP_CATALOG", {"required_apps": [dict(entry)]}, rank=10)

    result = resolve("dev-1", [a, b])
    assert len(result.values["APP_CATALOG"]["required_apps"]) == 1
    assert result.conflicts == ()


def test_highest_rank_wins_and_reports_a_conflict():
    a = make_assignment("APP_CATALOG", {"kiosk_package": "com.atak"}, rank=50, name="Field Kiosk")
    b = make_assignment("APP_CATALOG", {"kiosk_package": "com.scanner"}, rank=10, name="Warehouse")

    result = resolve("dev-1", [a, b])

    assert result.values["APP_CATALOG"]["kiosk_package"] == "com.atak"
    assert len(result.conflicts) == 1
    conflict = result.conflicts[0]
    assert conflict.field_name == "kiosk_package"
    assert conflict.winning_source["policy_name"] == "Field Kiosk"
    assert conflict.discarded[0]["value"] == "com.scanner"


def test_highest_rank_agreement_is_not_a_conflict():
    a = make_assignment("APP_CATALOG", {"kiosk_package": "com.atak"}, rank=50)
    b = make_assignment("APP_CATALOG", {"kiosk_package": "com.atak"}, rank=10)

    assert resolve("dev-1", [a, b]).conflicts == ()


# --------------------------------------------------------------------------- #
# Presence semantics — the heart of "stacking without clobbering"
# --------------------------------------------------------------------------- #


def test_unset_fields_do_not_contribute():
    """A narrow policy must not blank out fields a broad one set."""
    broad = make_assignment("PASSWORD", {"min_length": 8, "history_length": 5}, rank=10)
    narrow = make_assignment("PASSWORD", {"min_digits": 2}, rank=99)

    values = resolve("dev-1", [broad, narrow]).values["PASSWORD"]

    assert values == {"min_length": 8, "history_length": 5, "min_digits": 2}


def test_explicit_null_is_treated_as_unset():
    a = make_assignment("PASSWORD", {"min_length": 8}, rank=10)
    b = make_assignment("PASSWORD", {"min_length": None}, rank=99)

    assert resolve("dev-1", [a, b]).values["PASSWORD"]["min_length"] == 8


def test_fields_nobody_sets_are_absent_not_defaulted():
    result = resolve("dev-1", [make_assignment("PASSWORD", {"min_length": 8})])

    assert "expiration_days" not in result.values["PASSWORD"]


def test_no_assignments_yields_empty_policy():
    result = resolve("dev-1", [])

    assert result.values == {}
    assert result.conflicts == ()
    assert result.considered == ()


def test_policy_types_are_merged_independently():
    pw = make_assignment("PASSWORD", {"min_length": 8}, rank=1)
    res = make_assignment("RESTRICTIONS", {"allow_camera": False}, rank=1)

    result = resolve("dev-1", [pw, res])

    assert set(result.values) == {"PASSWORD", "RESTRICTIONS"}


def test_considered_lists_every_assignment_in_resolution_order():
    a = make_assignment("PASSWORD", {"min_length": 4}, rank=1, name="Low")
    b = make_assignment("PASSWORD", {"min_length": 6}, rank=9, name="High")

    considered = resolve("dev-1", [a, b]).considered

    assert [c["policy_name"] for c in considered] == ["High", "Low"]


def test_resolution_is_independent_of_input_order():
    a = make_assignment("PASSWORD", {"min_length": 4}, rank=1)
    b = make_assignment("PASSWORD", {"min_length": 12}, rank=9)

    assert resolve("d", [a, b]).values == resolve("d", [b, a]).values


# --------------------------------------------------------------------------- #
# Strategy-level error handling
# --------------------------------------------------------------------------- #


def _contribution(value: Any) -> Contribution:
    return Contribution(
        value=value,
        source=SourceRef("a", "p", "Policy", 1, "device", 0),
    )


def test_empty_contributions_rejected():
    with pytest.raises(MergeError):
        apply_strategy([], Merge(MergeStrategy.MAX))


def test_most_restrictive_rejects_non_boolean():
    with pytest.raises(MergeError, match="bool"):
        apply_strategy([_contribution("yes")], Merge(MergeStrategy.MOST_RESTRICTIVE))


def test_union_rejects_non_list():
    with pytest.raises(MergeError, match="list"):
        apply_strategy([_contribution("com.app")], Merge(MergeStrategy.UNION))


def test_merge_by_key_requires_the_key_on_every_item():
    with pytest.raises(MergeError, match="package_name"):
        apply_strategy(
            [_contribution([{"other": 1}])],
            Merge(MergeStrategy.MERGE_BY_KEY, key="package_name"),
        )


# --------------------------------------------------------------------------- #
# Preview diff
# --------------------------------------------------------------------------- #


def test_diff_reports_added_removed_and_changed():
    before = {"PASSWORD": {"min_length": 6, "history_length": 3}}
    after = {"PASSWORD": {"min_length": 10}, "RESTRICTIONS": {"allow_camera": False}}

    changes = {(c["policy_type"], c["field"]): c for c in diff_values(before, after)}

    assert changes[("PASSWORD", "min_length")]["change"] == "changed"
    assert changes[("PASSWORD", "min_length")]["before"] == 6
    assert changes[("PASSWORD", "min_length")]["after"] == 10
    assert changes[("PASSWORD", "history_length")]["change"] == "removed"
    assert changes[("RESTRICTIONS", "allow_camera")]["change"] == "added"


def test_diff_of_identical_policies_is_empty():
    values = {"PASSWORD": {"min_length": 6}}
    assert diff_values(values, dict(values)) == []
