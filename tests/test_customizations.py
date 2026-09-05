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

"""The CUSTOMIZATIONS policy: operator-authored text shown on the device (W42).

Three strings landing in three different places in the OS. Not much logic, so what
is worth testing is the parts that fail quietly if they are wrong: the length caps
that mirror Android's silent truncation, the two sub-pages the console derives from
`ui_group`, and — the one with teeth — that a cleared text box goes *absent* rather
than becoming an empty string. On the lock screen those are different instructions
to the device (Android reference §W42).
"""

from __future__ import annotations

from starlette.datastructures import FormData

from app.policies import form_parse
from app.policies.creator_catalog import get as category
from app.policies.form_schema import sub_pages
from app.policies.registry import PolicyTypeError, registry
from app.policies.resolver import resolve
from tests.test_resolver import make_assignment

# --------------------------------------------------------------------------- #
# The spec
# --------------------------------------------------------------------------- #


def test_the_category_is_wired_to_the_policy_type():
    """The catalog entry shipped as a placeholder for a long time; a category that
    is listed but inert offers the operator a form that saves nothing."""
    customizations = category("customizations")
    assert customizations is not None
    assert customizations.wired
    assert customizations.policy_type == "CUSTOMIZATIONS"


def test_all_three_fields_travel():
    spec = registry.validate_spec(
        "CUSTOMIZATIONS",
        {
            "disabled_setting_message": "Disabled by ops — call the watch desk.",
            "admin_app_description": "This tablet is managed by 3rd Bde S6.",
            "lock_screen_message": "Property of 3rd Bde. If found call 555-0100.",
        },
    )
    assert spec["disabled_setting_message"].startswith("Disabled by ops")
    assert spec["admin_app_description"].startswith("This tablet")
    assert spec["lock_screen_message"].endswith("555-0100.")


def test_an_empty_policy_is_allowed():
    """Unlike WALLPAPER, an empty section here is meaningful: it is how an operator
    says "clear the messages" rather than "leave them alone", because the applier
    pushes null for whatever is absent."""
    assert registry.validate_spec("CUSTOMIZATIONS", {}) == {}


def test_an_over_long_support_message_is_refused_here_not_truncated_there():
    """Android truncates past 200 characters without telling anyone. An operator
    should learn that from the console, while they can still edit it."""
    try:
        registry.validate_spec("CUSTOMIZATIONS", {"disabled_setting_message": "x" * 201})
    except PolicyTypeError as exc:
        assert "disabled_setting_message" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("a 201-character support message should not validate")


def test_the_long_description_gets_the_platform_s_larger_ceiling():
    """setLongSupportMessage truncates at 20000, not 200 — a description is meant
    to be prose, and capping it at the short message's limit would be our own
    restriction invented on top of the platform's."""
    spec = registry.validate_spec("CUSTOMIZATIONS", {"admin_app_description": "x" * 20_000})
    assert len(spec["admin_app_description"]) == 20_000


# --------------------------------------------------------------------------- #
# The console form
# --------------------------------------------------------------------------- #


def test_the_two_sub_pages_are_support_message_and_lock_screen():
    """W12 derives sub-pages from ui_group, so this is what the operator navigates."""
    pages = {page.label: [f.name for f in page.fields] for page in sub_pages("CUSTOMIZATIONS")}

    assert set(pages) == {"Support message", "Lock screen"}
    assert pages["Support message"] == ["disabled_setting_message", "admin_app_description"]
    assert pages["Lock screen"] == ["lock_screen_message"]


def test_the_messages_render_as_multi_line_text_with_their_limit():
    fields = {f.name: f for page in sub_pages("CUSTOMIZATIONS") for f in page.fields}

    assert fields["disabled_setting_message"].control == "text"
    # The cap has to reach the control, or the textarea's maxlength is decoration.
    assert fields["disabled_setting_message"].maximum == 200
    assert fields["admin_app_description"].maximum == 20_000


def test_a_cleared_box_goes_absent_rather_than_empty():
    """The one that matters. An empty lock screen message hands the field back to
    the user; a *blank* one holds it blank and keeps them locked out of it. An
    operator clearing the box means the former, so the field must not be written."""
    parsed = form_parse.parse_form(
        "CUSTOMIZATIONS",
        FormData(
            [
                ("disabled_setting_message", "Ask ops."),
                ("admin_app_description", ""),
                ("lock_screen_message", "   "),
            ]
        ),
    )

    assert parsed == {"disabled_setting_message": "Ask ops."}


# --------------------------------------------------------------------------- #
# Stacking
# --------------------------------------------------------------------------- #


def test_the_highest_ranked_policy_wins_a_message():
    """Two policies cannot both have their say in one sentence, so rank decides.
    Concatenating would put text in front of a user that nobody wrote."""
    resolved = resolve(
        "dev-1",
        [
            make_assignment(
                "CUSTOMIZATIONS", {"lock_screen_message": "Property of Bde HQ."}, rank=10
            ),
            make_assignment(
                "CUSTOMIZATIONS", {"lock_screen_message": "Property of 3rd Bn."}, rank=0
            ),
        ],
    )

    assert resolved.values["CUSTOMIZATIONS"]["lock_screen_message"] == "Property of Bde HQ."


def test_a_narrow_policy_stacks_onto_a_broad_one():
    """The point of per-field optionality: a policy setting only the lock screen
    must not blank the support message a lower-ranked one contributed."""
    resolved = resolve(
        "dev-1",
        [
            make_assignment("CUSTOMIZATIONS", {"lock_screen_message": "Bde HQ."}, rank=10),
            make_assignment(
                "CUSTOMIZATIONS", {"disabled_setting_message": "Ask the S6."}, rank=0
            ),
        ],
    )

    values = resolved.values["CUSTOMIZATIONS"]
    assert values["lock_screen_message"] == "Bde HQ."
    assert values["disabled_setting_message"] == "Ask the S6."
