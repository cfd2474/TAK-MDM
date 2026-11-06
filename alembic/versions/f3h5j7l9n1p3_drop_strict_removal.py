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

"""Drop the strict must-not-be-installed list (W154)

`removed_packages` was a second blacklist that uninstalled outright, refused to
fall back to hiding, and reported a failure when the app survived. For an
ordinary sideloaded app it did exactly what `blocked_packages` does; the two
differed only for preinstalled apps, where the blocklist hides and the strict
list could only fail. Two lists behaving identically in the common case cost
more in confusion than the distinction was worth.

⚠️ **The key has to come out of stored specs, not just out of the model.**
Policy specs are `extra="forbid"`, so a saved `APP_CATALOG` version still
carrying `removed_packages` would stop validating the moment the field left the
class — and that is not a quiet failure, it is every page that renders or merges
that policy raising instead.

⚠️ **This changes what devices do, and the change is not symmetrical.** Packages
listed only here stop being removed at all; they are *not* migrated into
`blocked_packages`, because that would silently start hiding apps an operator
asked to have deleted, on preinstalled packages where deletion was impossible
anyway. Anything that still needs suppressing has to be put on the blocklist
deliberately. The `downgrade` puts the column's schema back but cannot put the
lists back — the values are gone once this runs.

Revision ID: f3h5j7l9n1p3
Revises: e2g4i6k8m0o2
Create Date: 2026-09-13
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "f3h5j7l9n1p3"
down_revision = "e2g4i6k8m0o2"
branch_labels = None
depends_on = None

_FIELD = "removed_packages"


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, spec FROM policy_version")
    ).fetchall()

    touched = 0
    for row in rows:
        spec = row.spec
        # ⚠️ SQLite hands back a string where Postgres hands back a dict, and this
        # project runs both (tests on the former, deployments on the latter). A
        # migration that only handled one would pass every test and then do
        # nothing at all in production.
        raw = json.loads(spec) if isinstance(spec, str) else spec
        if not isinstance(raw, dict) or _FIELD not in raw:
            continue
        raw.pop(_FIELD)
        connection.execute(
            sa.text("UPDATE policy_version SET spec = :spec WHERE id = :id"),
            {"spec": json.dumps(raw) if isinstance(spec, str) else raw, "id": row.id},
        )
        touched += 1

    if touched:
        print(f"dropped {_FIELD} from {touched} policy version(s)")


def downgrade() -> None:
    """Nothing to restore.

    The field's absence is what the model now expects, and the lists themselves
    were discarded by `upgrade`. Re-adding the key empty would be worse than
    leaving it out: a policy that reads as "must not be installed: nothing" is
    indistinguishable from one whose entries were lost.
    """
