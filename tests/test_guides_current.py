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

"""The guides describe the product that exists (W158).

⚠️ Documentation drift is not a cosmetic problem here. A guide that names a
control which no longer exists sends an operator looking for it, and one that
omits a capability means the capability may as well not ship. Both happened:
the guides still routed assignment through tags, removed a year ago, and never
mentioned the permanent QR that exists for exactly the bulk-onboarding case
they describe.

These tests pin the *model* references, not the prose. Rewording a guide should
not fail them; describing a feature that does not exist should.
"""

from __future__ import annotations

import pathlib
import re

import pytest

GUIDES = pathlib.Path("app/web/guides")

#: Release notes are a record of what changed and may name retired concepts.
HISTORY = {"release-notes.md"}


def _guides() -> list[pathlib.Path]:
    return [p for p in sorted(GUIDES.rglob("*.md")) if p.name not in HISTORY]


def _text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# ⚠️ Concepts the model no longer has
# --------------------------------------------------------------------------- #


def test_no_guide_mentions_tags():
    """Assignment scope is device or group. Tags were dropped in W123."""
    from app.db.models import AssignmentScope

    assert {s.value for s in AssignmentScope} == {"device", "group"}

    offenders = {
        p.name: re.findall(r"[^.]*\btags?\b[^.]*", _text(p), re.I)
        for p in _guides()
        if re.search(r"\btags?\b", _text(p), re.I)
    }

    assert not offenders, offenders


def test_no_guide_offers_the_add_to_store_toggle():
    """Replaced by storefronts in W140 — a shelf a policy names, not a flag."""
    for path in _guides():
        assert "Add to store" not in _text(path), path.name


def test_no_guide_names_the_strict_removal_list():
    """`removed_packages` went in W154."""
    for path in _guides():
        assert "removed_packages" not in _text(path), path.name


# --------------------------------------------------------------------------- #
# Capabilities that exist and have to be findable
# --------------------------------------------------------------------------- #


def test_the_enrolment_guide_covers_the_permanent_qr():
    """⚠️ The case the operator asked about: printing one code for a
    provisioning bench. Undocumented, it may as well not exist."""
    text = _text(GUIDES / "howto" / "01-enrolment.md")

    assert "permanent" in text.lower()
    assert "Save QR" in text
    assert "15-minute" in text, "the default and the trade must both be stated"


def test_the_enrolment_guide_states_the_trade():
    """A permanent QR is a picture that stays a live credential."""
    text = _text(GUIDES / "howto" / "01-enrolment.md").lower()

    assert "retire" in text


def test_the_policy_guide_explains_profiles_and_sections():
    """⚠️ `/policies/new` builds a profile. An operator who thinks it builds a
    policy tries to assign a section and is refused."""
    text = _text(GUIDES / "howto" / "02-building-a-policy.md")

    assert "profile" in text.lower()
    assert "section" in text.lower()


def test_the_app_guide_describes_storefronts_and_pinned_builds():
    text = _text(GUIDES / "howto" / "04-uploading-an-app.md")

    # ⚠️ Emphasis stripped before matching. The guide writes "**one**
    # storefront", so a literal phrase check fails on the asterisks rather than
    # on the claim — and a test that breaks when prose is emphasised teaches
    # people to weaken it.
    plain = re.sub(r"[*_`]", "", text).lower()

    assert "storefront" in plain
    assert "one storefront" in plain, "the one-per-policy limit must be stated"
    # W139: nothing is chosen automatically.
    assert 'no "latest"' in text.lower() or "names the exact build" in text


def test_the_kiosk_guide_names_the_right_category():
    """Kiosk is its own category, not part of App Management."""
    text = _text(GUIDES / "howto" / "06-kiosk.md")

    assert "Kiosk** category" in text or "Kiosk category" in text
    assert "kiosk_package` in a policy's App Management" not in text


# --------------------------------------------------------------------------- #
# ⚠️ Every field name a guide cites must exist
# --------------------------------------------------------------------------- #


def test_backticked_field_names_exist_in_some_spec():
    """A guide naming a field the model dropped is worse than one saying
    nothing: it sends someone looking for a control that is not there."""
    from app.policies.form_schema import form_fields

    known: set[str] = set()
    for policy_type in (
        "PASSWORD", "RESTRICTIONS", "APP_CATALOG", "KIOSK", "ATAK_CONFIG",
        "NETWORKS", "WALLPAPER", "CUSTOMIZATIONS", "NETWORK_DATA_USE",
        "FILES", "TRACKING_FENCING",
    ):
        known |= {f.name for f in form_fields(policy_type)}

    # Sub-model fields and non-field words the guides legitimately use.
    known |= {
        "dest_path", "availability", "persist", "extract", "extract_to",
        "package_name", "min_version_code", "artifact_sha256", "auto_update",
        "file_id", "required", "optional", "disabled", "android_id", "logcat",
    }

    unknown: dict[str, list[str]] = {}
    for path in _guides():
        for token in sorted(set(re.findall(r"`([a-z][a-z0-9_]{3,})`", _text(path)))):
            if token not in known:
                unknown.setdefault(path.name, []).append(token)

    assert not unknown, f"fields named in guides that no spec has: {unknown}"


@pytest.mark.parametrize("path", _guides(), ids=lambda p: p.name)
def test_every_guide_still_renders(path, client):
    """⚠️ Editing prose must not break the page that serves it."""
    slug = path.stem.split("-", 1)[-1] if "-" in path.stem else path.stem
    section = path.parent.name
    response = client.get(f"/guides/{section}/{slug}")

    assert response.status_code == 200, f"{section}/{slug}"
