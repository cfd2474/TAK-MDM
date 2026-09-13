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

#: The released version. ⚠️ Hand-maintained, which this module's own docstring
#: warns about — so `tests/test_version.py` fails the build when it does not
#: match the newest git tag. That is the difference between a number somebody
#: must remember to bump and one they cannot forget: the guard, not the intent.
#:
#: The revision is *not* replaced by it. "Which release is this" and "is this
#: exactly the code I think it is" are different questions, and a tag can move
#: while a commit cannot — so the version leads and the commit stays alongside.
VERSION_FILE = _ROOT / "VERSION"


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
    #: Released version, e.g. "1.0.0", or None when nothing declared one.
    version: str | None = None

    @property
    def known(self) -> bool:
        return self.revision != "unknown"

    @property
    def label(self) -> str:
        """One short string for the footer.

        The version when there is one, because that is what an operator compares
        against a release note and what InfraTAK offers to update. A build with
        no declared version still reports its revision rather than nothing.
        """
        if self.version:
            text = f"v{self.version}"
            if self.dirty:
                text += " · modified"
            return text
        if not self.known:
            return "build unknown"
        text = f"build {self.revision}"
        if self.committed:
            text += f" · {self.committed}"
        if self.dirty:
            text += " · modified"
        return text

    @property
    def detail(self) -> str:
        """The long form, for the footer's tooltip.

        ⚠️ The commit does not disappear just because a version is shown. The
        question "is this server exactly the code I think it is" still has only
        one answer, and this is where it stays reachable.
        """
        parts = [f"revision {self.revision}"]
        if self.committed:
            parts.append(self.committed)
        if self.dirty:
            parts.append("uncommitted changes at build time")
        parts.append(f"source: {self.source}")
        return " · ".join(parts)


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


def _resolve_version() -> str | None:
    """The released version, or None.

    ⚠️ Resolved separately from the revision, and deliberately so: a deployment
    can know exactly which commit it runs and still not be a numbered release
    (a working copy between tags), and an image built by other means can be told
    its version without being able to reach git.

    1. `TAKMDM_VERSION` — an explicit override.
    2. `VERSION` at the repo root — ships in the clone and in the image, which
       is what makes this work in a container with no `.git`.
    3. `git describe --tags` — a working copy, for development.
    """
    from_env = (os.environ.get("TAKMDM_VERSION") or "").strip()
    if from_env:
        return from_env.lstrip("v")

    try:
        declared = VERSION_FILE.read_text(encoding="utf-8").strip()
        if declared:
            return declared.lstrip("v")
    except OSError:
        pass

    if (_ROOT / ".git").exists():
        try:
            found = subprocess.run(
                ["git", "-C", str(_ROOT), "describe", "--tags", "--abbrev=0"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if found.returncode == 0 and found.stdout.strip():
                return found.stdout.strip().lstrip("v")
        except (OSError, subprocess.SubprocessError):
            pass
    return None


@lru_cache(maxsize=1)
def build_info() -> BuildInfo:
    """The running build. Resolved once — it cannot change while the process runs."""
    import dataclasses

    found = BuildInfo()
    for resolve in (_from_env, _from_file, _from_git):
        candidate = resolve()
        if candidate is not None:
            found = candidate
            break
    return dataclasses.replace(found, version=_resolve_version())


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
