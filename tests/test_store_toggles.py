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

"""Store shortcuts write package names into the blocklist (W153).

⚠️ A blocklist entry naming a package the device does not have blocks nothing
and reports nothing — the policy looks applied and the store still opens. So the
names are a maintained constant rather than something an operator types from
memory, and they land in the *visible* list where they can be checked and added
to.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.policies import app_stores


def _blocklist_panel(html: str) -> str:
    """The Blocklist sub-page's markup."""
    start = html.index("data-store-toggles")
    return html[max(0, start - 4000) : start + 6000]


# --------------------------------------------------------------------------- #
# ⚠️ What must never be in here
# --------------------------------------------------------------------------- #


def test_play_services_is_not_blocked_with_the_play_store():
    """⚠️ The single most damaging mistake available here.

    `com.google.android.gms` backs location, push and attestation. Hiding it
    breaks far more than app installation — including things ATAK depends on —
    and it would look like "the Play tickbox broke the tablet".
    """
    for store in app_stores.STORE_GROUPS:
        assert "com.google.android.gms" not in store.package_names, store.key


def test_no_group_blocks_the_atlas_agent_or_launcher():
    """⚠️ Blocking the agent would end management of the device, and nothing
    could undo it remotely afterwards."""
    forbidden = {"com.taksolutions.atlasmdm", "com.taksolutions.atlaslauncher"}

    for store in app_stores.STORE_GROUPS:
        assert not forbidden & set(store.package_names), store.key


# --------------------------------------------------------------------------- #
# The data
# --------------------------------------------------------------------------- #


def test_the_three_groups_the_operator_asked_for_exist():
    assert [s.key for s in app_stores.STORE_GROUPS] == ["play", "galaxy", "third_party"]


def test_every_group_has_a_label_help_and_packages():
    for store in app_stores.STORE_GROUPS:
        assert store.label and store.help and store.packages, store.key


def test_package_names_look_like_package_names():
    for store in app_stores.STORE_GROUPS:
        for package, name in store.packages:
            assert re.fullmatch(r"[a-z][a-z0-9_]*(\.[a-z0-9_]+)+", package), package
            assert name, package


def test_no_package_is_listed_twice_within_a_group():
    for store in app_stores.STORE_GROUPS:
        names = store.package_names
        assert len(names) == len(set(names)), store.key


def test_the_play_store_package_is_the_store_not_a_guess():
    assert app_stores.PLAY.package_names == ("com.android.vending",)


def test_all_packages_is_deduplicated_and_ordered():
    every = app_stores.all_packages()

    assert len(every) == len(set(every))
    assert every[0] == "com.android.vending"


# --------------------------------------------------------------------------- #
# The form
# --------------------------------------------------------------------------- #


def test_the_blocklist_offers_the_shortcuts(client: TestClient):
    body = client.get("/policies/new?policy_type=APP_CATALOG").text

    assert body.count("data-store-toggles") == 1
    assert body.count("data-store-group") == len(app_stores.STORE_GROUPS)


def test_every_package_reaches_the_page(client: TestClient):
    """⚠️ `_policy_form.html` is pulled in with `{% from ... import %}`, and an
    imported macro cannot see the caller's context — a bare name there renders
    *empty* rather than raising, which is how a select shipped blank in W140."""
    body = client.get("/policies/new?policy_type=APP_CATALOG").text

    for package in app_stores.all_packages():
        assert package in body, package


def test_only_the_blocklist_gets_them(client: TestClient):
    """⚠️ The same tick on an allowlist would mean the opposite of what was
    asked: it would *permit* every store instead of blocking them."""
    from app.policies.form_schema import form_fields

    opted_in = [f.name for f in form_fields("APP_CATALOG") if f.store_toggles]

    assert opted_in == ["blocked_packages"]


def test_the_shortcut_is_a_shortcut_not_a_separate_setting():
    """The spec gains no field: ticking writes into `blocked_packages`, so the
    stored policy is exactly what an operator would have typed."""
    from app.policies.specs.app_catalog import AppCatalogSpec

    # `storefront_id` is the unrelated ATLAS store picker and predates this.
    invented = [
        n for n in AppCatalogSpec.model_fields
        if any(k in n for k in ("disable_", "block_store", "play_store", "galaxy"))
    ]

    assert not invented, invented
