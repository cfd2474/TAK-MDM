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

"""How much of ATLAS's storage is in use, and by what (W208).

⚠️ **The filesystem is the meter; the database is only the breakdown.** What
runs out is the filesystem, so it supplies the total, the used and the free. What
"apps" and "files" *mean* is something only the database knows. Mixing the two
sources into one number would produce a figure that is neither.

⚠️ **The denominator is whatever filesystem holds the artifacts.** Where the
InfraTAK module has reserved a store (W205) that is the reservation — measured on
a live box as 97.87 GiB usable inside a 100 GB provision, holding the artifacts,
the repository caches *and* the database. Where it has not, it is the box's disk.
`dedicated` says which, so the page can tell an operator the truth either way
rather than calling a shared disk a reservation.

⚠️ **Artifacts are content-addressed** (D8), so a blob referenced by an app *and*
a managed file is stored once. Every sum here is over **distinct digests**;
summing per reference would report more in use than the disk holds, on a page
whose whole purpose is to be trusted about exactly that.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AppPackageFile, Artifact, ManagedFile


@dataclass(frozen=True)
class Usage:
    """What the meter draws.

    ``apps`` and ``files`` deliberately do **not** add up to ``used``: the
    repository caches, the database and the filesystem's own structures share
    this space. :attr:`other` is that remainder, named rather than hidden — a
    breakdown engineered to total exactly would be a lie told in a place built
    to be believed.
    """

    total: int
    used: int
    free: int
    apps: int
    files: int
    #: Blobs referenced by an app *and* a managed file. Counted once in `used`,
    #: and included in both `apps` and `files`, because it genuinely belongs to
    #: both — so the two can sum to more than what is stored.
    shared: int
    #: Everything else on the filesystem: caches, the database, `lost+found`.
    other: int
    #: True when the artifacts sit on their own filesystem rather than the box's.
    dedicated: bool

    @property
    def percent_used(self) -> float:
        """0–100, for the bar's width. 0 when the total is unknown."""
        if self.total <= 0:
            return 0.0
        return min(100.0, max(0.0, self.used * 100.0 / self.total))

    @property
    def uploads(self) -> int:
        """Apps and files together, counting a shared blob once.

        This is the number the operator asked for — "storage being used by apps
        and files (all uploads)" — and it is smaller than `apps + files`
        whenever anything is shared.
        """
        return self.apps + self.files - self.shared


def _distinct_bytes(session: Session, digests) -> int:
    """Total size of the given digests, each counted once."""
    total = session.scalar(
        select(func.coalesce(func.sum(Artifact.size_bytes), 0)).where(
            Artifact.sha256.in_(digests)
        )
    )
    return int(total or 0)


def survey(session: Session, root: Path | str) -> Usage:
    """Measure the storage ATLAS is using, and what is using it.

    `root` is the artifact directory — the filesystem it lives on is the one
    being measured.
    """
    root = Path(root)
    try:
        usage = shutil.disk_usage(root)
        total, used, free = usage.total, usage.used, usage.free
    except (OSError, ValueError):
        # A path that cannot be read is reported as nothing rather than guessed
        # at. A meter drawn from a fabricated total is worse than no meter.
        total = used = free = 0

    dedicated = False
    try:
        # ⚠️ `ValueError` as well as `OSError`. `os.stat` raises ValueError on
        # an embedded null, not OSError, so catching only the latter let a bad
        # path crash the page instead of degrading to "unknown" — the same trap
        # the InfraTAK module hit, repeated here and caught by the same test.
        dedicated = os.stat(root).st_dev != os.stat(root.anchor or "/").st_dev
    except (OSError, ValueError):
        dedicated = False

    app_digests = set(session.scalars(select(AppPackageFile.artifact_sha256)))
    file_digests = set(session.scalars(select(ManagedFile.artifact_sha256)))

    return Usage(
        total=total,
        used=used,
        free=free,
        apps=_distinct_bytes(session, app_digests) if app_digests else 0,
        files=_distinct_bytes(session, file_digests) if file_digests else 0,
        shared=(
            _distinct_bytes(session, app_digests & file_digests)
            if (app_digests & file_digests)
            else 0
        ),
        other=max(0, used - _distinct_bytes(session, app_digests | file_digests))
        if (app_digests | file_digests)
        else used,
        dedicated=dedicated,
    )
