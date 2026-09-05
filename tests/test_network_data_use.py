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

"""NETWORK_DATA_USE: tracking works, blocking is Knox's job (W43).

The tests that matter here are the ones guarding the line between those two. A
threshold an operator believes is enforced, but which no code on the device can
act on, is worse than no threshold — so the blocking fields must be refused, and
refused with a message that says why rather than "invalid spec".
"""

from __future__ import annotations

from starlette.datastructures import FormData

from app.policies import form_parse
from app.policies.creator_catalog import get as category
from app.policies.form_schema import sub_pages
from app.policies.registry import PolicyTypeError, registry
from app.policies.resolver import resolve
from tests.test_resolver import make_assignment

TYPE = "NETWORK_DATA_USE"


def _fields() -> dict:
    return {f.name: f for page in sub_pages(TYPE) for f in page.fields}


# --------------------------------------------------------------------------- #
# What the platform can actually do
# --------------------------------------------------------------------------- #


def test_tracking_and_notification_rules_are_accepted():
    spec = registry.validate_spec(
        TYPE,
        {
            "track_usage": True,
            "notify_rules": [{"period": 2, "metric": 0, "threshold_mb": 500}],
            "reset_daily_at": "00:00",
            "reset_monthly_on_day": 1,
        },
    )
    assert spec["track_usage"] is True
    assert spec["notify_rules"][0]["threshold_mb"] == 500
    assert spec["reset_monthly_on_day"] == 1


def test_per_app_notifications_are_accepted():
    """Per-app *usage* is readable by a Device Owner, so warning on it is real."""
    spec = registry.validate_spec(
        TYPE,
        {"app_notify_rules": [{"package_name": "com.atakmap.app.civ", "threshold_mb": 200}]},
    )
    assert spec["app_notify_rules"][0]["package_name"] == "com.atakmap.app.civ"


def test_a_reset_day_past_the_28th_is_refused():
    """A cycle set to the 31st silently never fires in February — a counter that
    does not reset is a cap that never triggers."""
    try:
        registry.validate_spec(TYPE, {"reset_monthly_on_day": 31})
    except PolicyTypeError as exc:
        assert "reset_monthly_on_day" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("day 31 should not validate")


def test_a_zero_threshold_is_refused():
    """Hexnode's form defaults these boxes to 0. Zero MB is either "block
    everything" — which is the part we cannot enforce — or a row left unfilled."""
    try:
        registry.validate_spec(TYPE, {"notify_rules": [{"threshold_mb": 0}]})
    except PolicyTypeError as exc:
        assert "threshold_mb" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("a 0 MB threshold should not validate")


# --------------------------------------------------------------------------- #
# What it cannot — and must therefore refuse rather than store
# --------------------------------------------------------------------------- #


def test_network_blocking_is_refused_and_says_why():
    try:
        registry.validate_spec(TYPE, {"network_restriction": 2})
    except PolicyTypeError as exc:
        message = str(exc)
        assert "network_restriction" in message
        # The operator has to learn *why*, not just that it failed — otherwise
        # this reads as a bug in the console rather than a platform wall.
        assert "Knox" in message
    else:  # pragma: no cover
        raise AssertionError("network_restriction should not validate without Knox")


def test_threshold_restrictions_are_refused_even_though_notifications_are_not():
    """Same shape, same screen, one enforceable and one not. This is the pair most
    likely to be confused, so it is asserted rather than assumed."""
    rule = [{"period": 2, "metric": 0, "threshold_mb": 500}]

    assert registry.validate_spec(TYPE, {"notify_rules": rule})["notify_rules"]

    try:
        registry.validate_spec(TYPE, {"restrict_rules": rule})
    except PolicyTypeError as exc:
        assert "restrict_rules" in str(exc) and "Knox" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("restrict_rules should not validate without Knox")


def test_per_app_blocking_is_refused():
    try:
        registry.validate_spec(
            TYPE,
            {"app_restrict_rules": [{"package_name": "com.example.app", "threshold_mb": 10}]},
        )
    except PolicyTypeError as exc:
        assert "app_restrict_rules" in str(exc) and "Knox" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("app_restrict_rules should not validate without Knox")


def test_every_blocked_field_is_named_at_once():
    """One save, one error listing everything to fix — not three round trips."""
    try:
        registry.validate_spec(
            TYPE,
            {
                "network_restriction": 1,
                "restrict_rules": [{"threshold_mb": 1}],
                "app_restrict_rules": [{"package_name": "com.example.app", "threshold_mb": 1}],
            },
        )
    except PolicyTypeError as exc:
        for name in ("network_restriction", "restrict_rules", "app_restrict_rules"):
            assert name in str(exc)
    else:  # pragma: no cover
        raise AssertionError("the blocked fields should not validate")


# --------------------------------------------------------------------------- #
# The console form
# --------------------------------------------------------------------------- #


def test_the_category_is_wired_with_both_sub_sections():
    entry = category("network_data_use")
    assert entry is not None and entry.wired
    assert entry.policy_type == TYPE

    labels = {page.label for page in sub_pages(TYPE)}
    assert labels == {"Data usage restrictions", "App-wise restrictions"}


def test_the_unavailable_controls_are_marked_rather_than_hidden():
    """Greyed and explained beats absent: an operator hunting for a data cap
    should find out it needs Knox, not conclude nobody built it."""
    fields = _fields()

    assert fields["network_restriction"].requires == "Knox"
    assert fields["restrict_rules"].requires == "Knox"
    assert fields["app_restrict_rules"].requires == "Knox"

    assert fields["track_usage"].requires is None
    assert fields["notify_rules"].requires is None
    assert fields["app_notify_rules"].requires is None


def test_the_app_wise_page_carries_the_per_app_controls():
    pages = {page.label: [f.name for f in page.fields] for page in sub_pages(TYPE)}
    assert pages["App-wise restrictions"] == ["app_notify_rules", "app_restrict_rules"]


def test_rule_rows_parse_and_blank_rows_are_dropped():
    parsed = form_parse.parse_form(
        TYPE,
        FormData(
            [
                ("notify_rules__period", "2"),
                ("notify_rules__metric", "0"),
                ("notify_rules__threshold_mb", "500"),
                # The template row an operator added and never filled in.
                ("notify_rules__period", "2"),
                ("notify_rules__metric", "1"),
                ("notify_rules__threshold_mb", ""),
            ]
        ),
    )
    assert parsed["notify_rules"] == [{"threshold_mb": 500, "period": 2, "metric": 0}]


def test_a_per_app_rule_naming_no_app_is_dropped():
    """It would restrict nothing, so storing it only makes the policy look busier
    than it is."""
    parsed = form_parse.parse_form(
        TYPE,
        FormData(
            [
                ("app_notify_rules__package_name", ""),
                ("app_notify_rules__period", "2"),
                ("app_notify_rules__metric", "0"),
                ("app_notify_rules__threshold_mb", "100"),
            ]
        ),
    )
    assert "app_notify_rules" not in parsed


# --------------------------------------------------------------------------- #
# Stacking
# --------------------------------------------------------------------------- #


def test_thresholds_from_stacked_policies_all_apply():
    """UNION, not highest-rank: two teams each wanting a warning should get both,
    because a threshold is an alert someone asked for, not a setting to win."""
    resolved = resolve(
        "dev-1",
        [
            make_assignment(
                TYPE, {"notify_rules": [{"period": 2, "metric": 0, "threshold_mb": 500}]}, rank=10
            ),
            make_assignment(
                TYPE, {"notify_rules": [{"period": 2, "metric": 0, "threshold_mb": 900}]}, rank=0
            ),
        ],
    )

    thresholds = {r["threshold_mb"] for r in resolved.values[TYPE]["notify_rules"]}
    assert thresholds == {500, 900}
