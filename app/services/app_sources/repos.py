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

from dataclasses import dataclass
from pathlib import Path

from app.services.app_sources.fdroid import FDroidSource


@dataclass(frozen=True)
class RepoSpec:
    """One repository the console offers."""

    name: str
    label: str
    url: str
    #: Shown beside the picker. States what the operator is trusting.
    note: str


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

_BY_NAME = {spec.name: spec for spec in KNOWN}


def spec(name: str) -> RepoSpec | None:
    return _BY_NAME.get(name)


def build(name: str, cache_dir: Path) -> FDroidSource | None:
    """The source for a named repository, or None if it is not one we offer."""
    found = spec(name)
    if found is None:
        return None
    return FDroidSource(
        Path(cache_dir), repo=found.url, name=found.name, label=found.label
    )
