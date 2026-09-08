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

"""The F-Droid-format repositories this console can search (W97, C3).

⚠️ **The index format is not F-Droid's alone**, which is the whole reason a second
and third repository cost almost nothing: same `entry.json`, same published
digests, same verification. `FDroidSource` needed a name and a repository URL, not
new code.

⚠️ **They are not equally trusted, and the console says so rather than implying
otherwise by listing them side by side.** Official F-Droid builds from source on
its own infrastructure. IzzyOnDroid is a third party with its own inclusion policy
that mostly ships developer-provided binaries. Both are legitimate; they are not
the same decision, and an operator picking from a dropdown deserves to know which
one they are making.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from app.services.app_sources.apkpure import ApkPureSource
from app.services.app_sources.fdroid import FDroidSource


@dataclass(frozen=True)
class RepoSpec:
    """One repository the console offers."""

    name: str
    label: str
    url: str
    #: Shown beside the results. States what the operator is trusting.
    note: str
    #: Which implementation answers for it. Not every source is an index.
    kind: str = "fdroid"
    #: ⚠️ False for a source that cannot be searched by name (W98). APKPure
    #: answers only for an exact package id, and the console says so rather than
    #: letting an empty result look like an outage.
    searchable: bool = True


#: ⚠️ Order is the order the console offers them, and it is a recommendation:
#: official F-Droid first, its archive second (same publisher, older builds), a
#: third party last.
KNOWN: tuple[RepoSpec, ...] = (
    RepoSpec(
        name="fdroid",
        label="F-Droid",
        url="https://f-droid.org/repo",
        note="Built from source by F-Droid on its own infrastructure. Current "
        "versions of open-source apps.",
    ),
    RepoSpec(
        name="fdroid-archive",
        label="F-Droid archive",
        url="https://f-droid.org/archive",
        note="Older builds of the same apps, from the same publisher. Where to "
        "look when the newest build is not the one that suits a device — the "
        "situation R19 ended in.",
    ),
    RepoSpec(
        name="izzyondroid",
        label="IzzyOnDroid",
        url="https://apt.izzysoft.de/fdroid/repo",
        note="⚠️ A third-party repository with its own inclusion policy, mostly "
        "shipping binaries provided by each app's developer rather than built "
        "from source. Legitimate and widely used, but a different trust "
        "decision from official F-Droid.",
    ),
)

#: ⚠️ Appended after the indexes, deliberately. Everything above publishes a
#: digest that a download is checked against; APKPure publishes none, so it is
#: offered last and labelled for what it is.
KNOWN = KNOWN + (
    RepoSpec(
        name="apkpure",
        label="APKPure",
        url="https://apkpure.com",
        note="⚠️ A mirror, not a publisher. It states no checksum, so a download "
        "can only be checked by reading the file afterwards — and it is searched "
        "by exact package id only, never by name. Reached through EFF's apkeep.",
        kind="apkpure",
        searchable=False,
    ),
)

#: ⚠️ Offered only when an account is linked (W99). Unlike every other source it
#: needs a credential, so `build` returns None without one and the unified search
#: simply skips it — an unlinked instance should not report a failure on every
#: query for a feature nobody has turned on.
KNOWN = KNOWN + (
    RepoSpec(
        name="google-play",
        label="Google Play",
        url="https://play.google.com",
        note="⚠️ Requires a linked Google account, and using it violates Play's "
        "Terms of Service §3.3 — the account may be locked, so use one kept for "
        "the purpose. Serves device-matched builds, so the linked device profile "
        "decides the architecture. Publishes no checksum. Reached through apkeep.",
        kind="google-play",
        searchable=False,
    ),
)

_BY_NAME = {spec.name: spec for spec in KNOWN}


def spec(name: str) -> RepoSpec | None:
    return _BY_NAME.get(name)


#: ⚠️ Sources are cached per process, and the reason is size (W98). A
#: `FDroidSource` holds its parsed index in memory; building a fresh one per
#: request would re-read and re-parse 59 MB for F-Droid, 111 MB for the archive
#: and 14 MB for IzzyOnDroid **on every search**. The disk cache alone does not
#: save that — parsing is the expensive half.
_INSTANCES: dict[str, object] = {}
_LOCK = threading.Lock()


def build(name: str, cache_dir: Path, *, play: tuple[str, str, str] | None = None):
    """The source for a named repository, or None if it is not one we offer.

    `play` carries `(email, aas_token, device_profile)` for Google Play, which is
    the one source that cannot exist without a credential.
    """
    found = spec(name)
    if found is None:
        return None

    key = f"{found.name}:{cache_dir}"
    with _LOCK:
        # Under a lock because sync routes run in a threadpool: two searches
        # arriving together would otherwise each build and parse their own.
        existing = _INSTANCES.get(key)
        if existing is not None:
            return existing

        if found.kind == "google-play":
            if play is None:
                # Not linked. Not an error — just not on offer.
                return None
            from app.services.app_sources.googleplay import GooglePlaySource

            email, token, device = play
            # ⚠️ Never cached: the credential can be unlinked or rotated between
            # requests, and a cached source would go on using a token the
            # operator believes they have removed.
            return GooglePlaySource(email, token, device_profile=device)
        if found.kind == "apkpure":
            source = ApkPureSource()
        else:
            source = FDroidSource(
                Path(cache_dir), repo=found.url, name=found.name, label=found.label
            )
        _INSTANCES[key] = source
        return source


def reset_cache() -> None:
    """Drop the cached sources. For tests, which must not share state."""
    with _LOCK:
        _INSTANCES.clear()
