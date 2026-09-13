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

"""Google Play offers no search until an account is linked (W145).

⚠️ Play is the one source that cannot be searched anonymously — every request is
made *as* the linked account. Offering the box first meant a search that failed
at the credential and surfaced as an error mentioning Google, which reads like
Play being down rather than like a step not yet taken.

The route already drew this distinction ("nothing found" and "nothing linked"
are different answers). The panel did not.
"""

from __future__ import annotations

import io
import subprocess

from fastapi.testclient import TestClient

from app.services import google_play_link

AAS = "aas_et/AKppINbc0Q"


class _Apkeep:
    """Stands in for the apkeep binary, which is not present in a test run."""

    def __call__(self, *args, **kwargs):
        return subprocess.CompletedProcess(
            args=[], stdout=f"Suceeded. AAS token: {AAS}\n", stderr="", returncode=0
        )


def _play_panel(html: str) -> str:
    start = html.index('data-tab-panel="play"')
    return html[start : html.index("tab-panel", start + 10)]


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #


def test_no_search_box_before_an_account_is_linked(client: TestClient):
    panel = _play_panel(client.get("/apps").text)

    assert "data-repo-query" not in panel
    assert "data-repo-search" not in panel


def test_it_says_what_to_do_instead(client: TestClient):
    """⚠️ A hidden control with no explanation is a worse bug than the one it
    replaced: the operator cannot tell a missing feature from a broken one."""
    panel = _play_panel(client.get("/apps").text)

    assert "No Google account is linked" in panel
    assert "/admin#tab-googleplay" in panel


def test_the_search_appears_once_linked(client: TestClient, db, token_vault):
    google_play_link.link_account(
        db, token_vault, email="ops@example.com",
        oauth_token="oauth2_4/" + "x" * 20, runner=_Apkeep(),
    )
    db.commit()

    panel = _play_panel(client.get("/apps").text)

    assert "data-repo-query" in panel
    assert "data-repo-search" in panel


def test_the_route_refuses_too(client: TestClient):
    """⚠️ The gate is in the page, so the route has to stand on its own — a
    hidden button is not an access control."""
    body = client.get("/apps/play/search", params={"q": "outlook"}).json()

    assert body["apps"] == []
    assert "No Google account is linked" in body["problems"][0]["error"]


# --------------------------------------------------------------------------- #
# ⚠️ The link that went nowhere
# --------------------------------------------------------------------------- #


def test_the_tab_switcher_honours_a_query_string():
    """`/admin?tab=googleplay` landed on Admin and sat on the default tab.

    Both spellings are in use across the templates and only the fragment worked,
    so the query form read as a broken link. Asserted on the source because this
    repository has no JavaScript harness; the behaviour itself was exercised in
    jsdom when the fix was made.
    """
    js = io.open("app/web/static/atlas.js", encoding="utf-8").read()
    start = js.index('document.querySelectorAll("[data-tabs]")')
    block = js[start : start + 1400]

    assert 'location.search' in block
    assert '"tab"' in block


def test_every_tab_link_points_at_a_tab_that_exists():
    """⚠️ The other half of the same bug: a link can be spelled correctly and
    still name a panel nothing renders."""
    import re
    from pathlib import Path

    panels: dict[str, set[str]] = {}
    for path in Path("app/web/templates").glob("*.html"):
        text = path.read_text(encoding="utf-8")
        found = set(re.findall(r'data-tab(?:-panel)?="([a-z0-9_-]+)"', text))
        if found:
            panels[path.name] = found
    known = set().union(*panels.values()) if panels else set()

    wanted = set()
    for path in Path("app/web/templates").glob("*.html"):
        text = path.read_text(encoding="utf-8")
        wanted |= set(re.findall(r'href="[^"]*[#?]tab[=-]([a-z0-9_-]+)"', text))

    unknown = wanted - known
    assert not unknown, f"links point at tabs that do not exist: {sorted(unknown)}"


# --------------------------------------------------------------------------- #
# ⚠️ Said once, not twice (W149)
# --------------------------------------------------------------------------- #


def _words(panel: str) -> str:
    import html as _html
    import re

    return _html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", panel)))


def test_the_unlinked_panel_says_each_thing_once(client: TestClient):
    """The panel opened with a paragraph describing how fetches work and then,
    with nothing linked, explained the same account and the same device profile
    again — two versions of one fact, the first describing a capability the page
    did not have."""
    text = _words(_play_panel(client.get("/apps").text))

    for phrase in ("Admin", "device profile", "CPU architecture", "held"):
        assert text.count(phrase) == 1, f"{phrase!r} appears {text.count(phrase)} times"


def test_the_unlinked_panel_does_not_describe_fetching(client: TestClient):
    """⚠️ The intro is written in the present tense about something this
    deployment cannot do yet. It belongs to the linked state only."""
    text = _words(_play_panel(client.get("/apps").text))

    assert "Fetches as the account linked under" not in text
    assert "No Google account is linked" in text


def test_the_linked_panel_still_explains_itself(client: TestClient, db, token_vault):
    """⚠️ Removing the duplicate must not cost the explanation. Once linked,
    the intro is the only place that says what the device profile decides."""
    google_play_link.link_account(
        db, token_vault, email="ops@example.com",
        oauth_token="oauth2_4/" + "x" * 20, runner=_Apkeep(),
    )
    db.commit()

    text = _words(_play_panel(client.get("/apps").text))

    assert "Fetches as the account linked under" in text
    assert "No Google account is linked" not in text
    for phrase in ("device profile", "CPU architecture", "held"):
        assert text.count(phrase) == 1, f"{phrase!r} appears {text.count(phrase)} times"


def test_the_admin_panel_points_at_the_play_tab_not_the_repo_search(client: TestClient):
    """⚠️ Google Play stopped being a row in the shared repository search when it
    got its own tab (W101). The admin panel went on saying it fed that search,
    and sent operators to the wrong tab to use what they had just linked."""
    body = client.get("/admin").text

    assert "3rd party repo</a> search fetch apps from" not in body
    assert "/apps#tab-play" in body
