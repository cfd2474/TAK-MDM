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

"""Binding a Google account, and downloading as it (W99).

⚠️ **apkeep is stubbed throughout.** There is no Google account on this side, and
a real token must never reach a test fixture — so what is proved here is the
handling: that the durable secret is sealed, never put on a command line, never
rendered back, and destroyed on unlink.
"""

from __future__ import annotations

import stat
from types import SimpleNamespace

import httpx
import pytest

from app.db.models import GooglePlayLinkStatus
from app.services import google_play_link
from app.services.app_sources.base import SourceError, SourceVersion
from app.services.app_sources.googleplay import GooglePlaySource
from tests.apk_fixtures import build_apk

OAUTH = "oauth2_4/0AVMBsJ-fake-value-for-tests"
AAS = "aas_et/FAKEtokenFORtests1234"


class _Apkeep:
    def __init__(self, *, stdout="", returncode=0, stderr="", writes=None):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr
        self.writes = writes
        self.calls: list[list[str]] = []

    def __call__(self, args, **kwargs):
        self.calls.append(args)
        if self.writes and kwargs.get("cwd"):
            import pathlib

            for name, payload in self.writes.items():
                pathlib.Path(kwargs["cwd"], name).write_bytes(payload)
        return SimpleNamespace(
            stdout=self.stdout, stderr=self.stderr, returncode=self.returncode
        )


# --------------------------------------------------------------------------- #
# Linking
# --------------------------------------------------------------------------- #


def test_the_one_time_token_is_exchanged_and_the_durable_one_sealed(db, token_vault):
    runner = _Apkeep(stdout=f"Suceeded. AAS token: {AAS}\n")

    link = google_play_link.link_account(
        db, token_vault, email="ops@example.com", oauth_token=OAUTH, runner=runner
    )
    db.commit()

    assert link.status is GooglePlayLinkStatus.LINKED
    assert link.email == "ops@example.com"
    # ⚠️ Sealed, not stored. The column must never hold the token itself.
    assert AAS not in (link.aas_token_sealed or "")
    assert token_vault.open(link.aas_token_sealed) == AAS


def test_an_obvious_paste_mistake_is_caught_before_apkeep_runs(db, token_vault):
    runner = _Apkeep()

    with pytest.raises(google_play_link.GooglePlayLinkError) as raised:
        google_play_link.link_account(
            db, token_vault, email="ops@example.com",
            oauth_token="the whole cookie, not its value", runner=runner,
        )

    assert "oauth2_4/" in str(raised.value)
    assert runner.calls == [], "nothing is spent on a value that cannot work"


def test_a_failed_exchange_says_the_token_is_spent(db, token_vault):
    """⚠️ Google issues the oauth value for a single exchange.

    An operator retrying with the same one would conclude the feature is broken,
    so the failure says plainly that a fresh one is needed.
    """
    runner = _Apkeep(returncode=1, stderr="BadAuthentication")

    with pytest.raises(google_play_link.GooglePlayLinkError) as raised:
        google_play_link.link_account(
            db, token_vault, email="ops@example.com", oauth_token=OAUTH, runner=runner
        )

    assert "BadAuthentication" in str(raised.value)
    assert "used up" in str(raised.value)
    assert google_play_link.get(db).status is GooglePlayLinkStatus.BROKEN


def test_unlink_destroys_the_token(db, token_vault):
    runner = _Apkeep(stdout=f"AAS token: {AAS}")
    google_play_link.link_account(
        db, token_vault, email="ops@example.com", oauth_token=OAUTH, runner=runner
    )
    db.commit()

    link = google_play_link.unlink(db)
    db.commit()

    assert link.status is GooglePlayLinkStatus.UNLINKED
    assert link.aas_token_sealed is None
    assert link.email is None
    assert google_play_link.credentials(db, token_vault) is None


def test_credentials_carry_the_pinned_device_profile(db, token_vault):
    runner = _Apkeep(stdout=f"AAS token: {AAS}")
    google_play_link.link_account(
        db, token_vault, email="ops@example.com", oauth_token=OAUTH,
        device_profile="ad_g3_pro", runner=runner,
    )
    db.commit()

    email, token, device = google_play_link.credentials(db, token_vault)

    assert (email, token) == ("ops@example.com", AAS)
    # ⚠️ Play serves device-matched builds, so the profile is part of the
    # credential's meaning — it decides the architecture that arrives.
    assert device == "ad_g3_pro"


# --------------------------------------------------------------------------- #
# ⚠️ The token must never reach a command line
# --------------------------------------------------------------------------- #


def test_the_ini_is_created_owner_only_rather_than_chmod_ed_after(tmp_path, monkeypatch):
    """⚠️ The permission is requested at creation, not applied afterwards.

    Between an open and a later `chmod` there is a window in which a Google
    credential is world-readable. Asserted by capturing what `os.open` is asked
    for, which holds on any platform — the mode itself is only meaningful on
    POSIX, and the server this runs on is Linux.
    """
    import os as _os

    seen: list[int] = []
    real_open = _os.open

    def spy(path, flags, mode=0o777, *a, **k):
        seen.append(mode)
        return real_open(path, flags, mode, *a, **k)

    monkeypatch.setattr(google_play_link.os, "open", spy)
    path = google_play_link.write_ini(tmp_path, "ops@example.com", AAS)

    assert seen == [0o600], "created readable by its owner and nobody else"
    assert AAS in path.read_text(encoding="utf-8")


@pytest.mark.skipif(
    not hasattr(stat, "S_IRGRP") or __import__("os").name == "nt",
    reason="Windows does not honour POSIX mode bits; the server runs on Linux",
)
def test_the_ini_file_is_private_to_this_user(tmp_path):
    path = google_play_link.write_ini(tmp_path, "ops@example.com", AAS)

    mode = stat.S_IMODE(path.stat().st_mode)
    assert not mode & stat.S_IRGRP, "group must not read a Google credential"
    assert not mode & stat.S_IROTH, "nor anyone else"


def test_downloading_never_puts_the_token_in_argv(tmp_path):
    """⚠️ The whole reason the ini file exists.

    `apkeep -t <token>` places a durable Google credential in argv, where anything
    able to read /proc on this host can see it.
    """
    apk = build_apk("com.example.app", 1)
    runner = _Apkeep(writes={"com.example.app.apk": apk})
    source = GooglePlaySource(
        "ops@example.com", AAS, device_profile="px_9a", runner=runner
    )
    type(source).available = property(lambda self: True)

    source.download(
        SourceVersion(package_name="com.example.app", version_code=None,
                      version_name="latest", version_key="latest")
    )

    flat = " ".join(runner.calls[0])
    assert AAS not in flat, "the token must not appear on the command line"
    assert "-i" in runner.calls[0], "credentials are passed as an ini file"
    assert "device=px_9a" in flat, "the profile decides the architecture"
    assert "split_apk=true" in flat


def test_a_paid_or_region_locked_app_explains_itself(tmp_path):
    runner = _Apkeep(writes={})
    source = GooglePlaySource("ops@example.com", AAS, runner=runner)
    type(source).available = property(lambda self: True)

    with pytest.raises(SourceError) as raised:
        source.download(
            SourceVersion(package_name="com.example.app", version_code=None,
                          version_name="latest", version_key="latest")
        )

    assert "region-locked" in str(raised.value)


def test_an_exact_package_id_needs_no_lookup():
    """The id is already the answer, and it reaches apps that search does not."""
    source = GooglePlaySource("ops@example.com", AAS, runner=_Apkeep())

    assert [a.package_name for a in source.search("com.instagram.android")] == [
        "com.instagram.android"
    ]


def test_a_name_is_resolved_against_play_s_own_listing_links():
    """⚠️ Anchored on a URL shape and an `aria-label`, not a CSS class (W101).

    Those are the two parts of that page least likely to be renamed by a
    redesign — which is exactly why the earlier survey rejected the scrapers
    built on styling.
    """
    page = (
        '<div class="XUIuZ"><a href="/store/apps/details?id=com.oi.handtevy" '
        'aria-label="Handtevy Mobile" class="Qfxief">…</a>'
        # The same app appears again further down in a "similar apps" rail; the
        # first occurrence must win rather than producing a duplicate row.
        '<a href="/store/apps/details?id=com.oi.handtevy" aria-label="Handtevy Mobile">'
        '<a href="/store/apps/details?id=com.handbid.android" aria-label="Handbid">'
    )
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text=page))
    )
    source = GooglePlaySource("ops@example.com", AAS, runner=_Apkeep(), client=client)

    found = source.search("handtevy")

    assert [(a.package_name, a.name) for a in found] == [
        ("com.oi.handtevy", "Handtevy Mobile"),
        ("com.handbid.android", "Handbid"),
    ]


def test_a_brand_search_returns_the_grid_layout_too():
    """⚠️ The bug this test exists for (W101).

    Play renders **two** card layouts. A specific query gives list rows carrying
    the name on the anchor; a broad or brand query gives a grid whose anchor has
    no `aria-label` at all, with the name as text inside the card. The first
    version matched only the former, so `outlook` worked and `microsoft` returned
    **nothing** — which reads as "Play has no Microsoft apps" rather than as a
    parsing failure.
    """
    grid = (
        '<a class="Si6A0c Gy4nib" href="/store/apps/details?id=com.microsoft.emmx" '
        'jslog="38003"><div class="Shbxxd"><img alt="Screenshot image"/></div>'
        '<div class="j2FCNc"><img/><div><span>Microsoft Edge</span></div>'
        '<div><span>Microsoft Corporation</span></div></div></a>'
        '<a class="Si6A0c" href="/store/apps/details?id=com.microsoft.teams" jslog="x">'
        '<div><span>Microsoft Teams</span></div></a>'
    )
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text=grid))
    )
    source = GooglePlaySource("ops@example.com", AAS, runner=_Apkeep(), client=client)

    assert [(a.package_name, a.name) for a in source.search("microsoft")] == [
        ("com.microsoft.emmx", "Microsoft Edge"),
        ("com.microsoft.teams", "Microsoft Teams"),
    ]


def test_a_row_without_a_readable_name_still_gives_its_package_id():
    """⚠️ The name is best effort; the package id is not.

    The id is what a fetch needs and it comes from a URL. If a redesign hides the
    title, a row degrades to something plainer — never to something wrong, and
    never to nothing.
    """
    bare = '<a href="/store/apps/details?id=com.example.silent"></a>'
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text=bare))
    )
    source = GooglePlaySource("ops@example.com", AAS, runner=_Apkeep(), client=client)

    found = source.search("silent")

    assert [(a.package_name, a.name) for a in found] == [
        ("com.example.silent", "com.example.silent")
    ]


def test_a_search_page_that_will_not_answer_says_so():
    """A changed page or an outage must report itself, not read as "no results" —
    an empty catalogue and an unreachable one are different facts."""
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(503, text=""))
    )
    source = GooglePlaySource("ops@example.com", AAS, runner=_Apkeep(), client=client)

    with pytest.raises(SourceError) as raised:
        source.search("handtevy")

    assert "503" in str(raised.value)


def test_google_play_is_not_offered_until_an_account_is_linked(tmp_path):
    """An unlinked instance must not report a failure on every search for a
    feature nobody has turned on."""
    from app.services.app_sources import repos

    repos.reset_cache()
    assert repos.build("google-play", tmp_path, play=None) is None
    assert repos.build(
        "google-play", tmp_path, play=("ops@example.com", AAS, "px_9a")
    ) is not None
