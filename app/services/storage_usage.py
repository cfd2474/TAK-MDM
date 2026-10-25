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

⚠️ **The denominator is whatever filesystem holds the artifacts, and it is
shared with the rest of the box (W285).** InfraTAK's reserved loop store (W205)
was retired module-side in W230: in *both* its storage modes the store is now a
plain directory on the host disk. "Fixed" is a size InfraTAK plans against at
deploy; nothing holds the space and nothing caps ATLAS at runtime.

⚠️ So there is no "reserved" case to detect, and the detector that tried was
wrong anyway: it called any artifact directory on a different device from `/`
a reservation, and inside a container `/` is the overlay while `/artifacts` is
a bind mount -- different devices on every deployment. The page said "Reserved
for ATLAS -- nothing else on this box can use it" on boxes where both halves
were false. If InfraTAK ever reserves space again, it must *say* so (a setting
it passes in), not leave ATLAS to infer it from device numbers.

⚠️ **Artifacts are content-addressed** (D8), so a blob referenced by an app *and*
a managed file is stored once. Every sum here is over **distinct digests**;
summing per reference would report more in use than the disk holds, on a page
whose whole purpose is to be trusted about exactly that.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AppPackageFile, Artifact, ManagedFile


@dataclass(frozen=True)
class Usage:
    """What the meter draws.

    ``apps`` and ``files`` deliberately do **not** add up to ``used``: ``used``
    is the whole disk's, and everything else on the box is in it too. A
    remainder is not drawn -- on a shared disk it is the box's usage, not
    ATLAS's (W285).
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
    )
