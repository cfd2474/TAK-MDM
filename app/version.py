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

"""Which build of the console is actually running (W102).

⚠️ **A version string somebody has to remember to bump is worse than none.**
`main.py` carried `version="0.1.0"` through a hundred work items; anyone reading
it learned nothing true. What an operator needs from a footer is the answer to
*"is the server running the code I think it is"*, and only the revision can
answer that.

⚠️ **The deploy tarball excludes `.git`**, so the host cannot ask git anything.
The revision is therefore captured when the tarball is packed and written to a
`BUILD` file that ships inside it. Sources are tried in order:

1. `TAKMDM_BUILD` — an explicit override, for an image built by other means.
2. `BUILD` at the repo root — what the deploy writes. The normal case in
   production.
3. `git` — the working copy, which is the normal case in development.
4. Nothing.

⚠️ **Nothing is invented.** With no source, this reports `unknown` rather than a
plausible-looking number. A footer confidently displaying a stale or guessed build
is worse than an empty one: it would be believed.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

#: Repo root: this file is app/version.py.
_ROOT = Path(__file__).resolve().parent.parent

BUILD_FILE = _ROOT / "BUILD"


@dataclass(frozen=True)
class BuildInfo:
    """What is known about the running build."""

    #: Short commit hash, or "unknown".
    revision: str = "unknown"
    #: ISO date of that commit, when known.
    committed: str | None = None
    #: ⚠️ True when the tree had uncommitted changes at pack time. Shown, because
    #: "which commit" is a misleading answer for a build that was not exactly one.
    dirty: bool = False
    #: Where this came from: env, file, git, or none. Kept so a surprising value
    #: can be traced rather than argued about.
    source: str = "none"

    @property
    def known(self) -> bool:
        return self.revision != "unknown"

    @property
    def label(self) -> str:
        """One short string for the footer."""
        if not self.known:
            return "build unknown"
        text = f"build {self.revision}"
        if self.committed:
            text += f" · {self.committed}"
        if self.dirty:
            text += " · modified"
        return text


def _from_env() -> BuildInfo | None:
    value = (os.environ.get("TAKMDM_BUILD") or "").strip()
    if not value:
        return None
    return BuildInfo(revision=value, source="env")


def _from_file() -> BuildInfo | None:
    try:
        raw = BUILD_FILE.read_text(encoding="utf-8")
    except OSError:
        return None

    fields: dict[str, str] = {}
    for line in raw.splitlines():
        key, _, value = line.partition("=")
        if value:
            fields[key.strip()] = value.strip()

    revision = fields.get("revision")
    if not revision:
        return None
    return BuildInfo(
        revision=revision,
        committed=fields.get("committed") or None,
        dirty=fields.get("dirty", "").lower() == "true",
        source="file",
    )


def _from_git() -> BuildInfo | None:
    """The working copy, for development. Absent in production by design."""
    if not (_ROOT / ".git").exists():
        return None
    try:
        described = subprocess.run(
            ["git", "-C", str(_ROOT), "log", "-1", "--format=%h %cs"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if described.returncode != 0:
            return None
        revision, _, committed = described.stdout.strip().partition(" ")
        if not revision:
            return None

        status = subprocess.run(
            ["git", "-C", str(_ROOT), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return BuildInfo(
            revision=revision,
            committed=committed or None,
            dirty=bool(status.stdout.strip()),
            source="git",
        )
    except (OSError, subprocess.SubprocessError):
        return None


@lru_cache(maxsize=1)
def build_info() -> BuildInfo:
    """The running build. Resolved once — it cannot change while the process runs."""
    for resolve in (_from_env, _from_file, _from_git):
        found = resolve()
        if found is not None:
            return found
    return BuildInfo()


def write_build_file(path: Path, info: BuildInfo) -> Path:
    """Record a build for a tarball that will not carry `.git`."""
    path.write_text(
        "\n".join(
            [
                f"revision={info.revision}",
                f"committed={info.committed or ''}",
                f"dirty={'true' if info.dirty else 'false'}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path
