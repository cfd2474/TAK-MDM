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

"""Stamp the working copy's revision into `BUILD`, for the deploy tarball (W102).

Run immediately before packing. ⚠️ **The tarball excludes `.git`**, so the host
has no way to work out what it is running — this file is the only thing that
carries the answer across.

    python scripts/write_build.py && tar -czf … .

⚠️ **It records a dirty tree as dirty.** Deploying uncommitted work is ordinary
during development; quietly labelling it with the last commit's hash would make
the footer claim something false, which is worse than the footer being vague.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.version import BUILD_FILE, _from_git, write_build_file  # noqa: E402


def main() -> int:
    info = _from_git()
    if info is None:
        print("no git working copy here; BUILD not written", file=sys.stderr)
        return 1

    write_build_file(BUILD_FILE, info)
    print(f"BUILD: {info.label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
