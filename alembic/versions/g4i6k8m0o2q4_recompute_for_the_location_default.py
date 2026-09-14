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

"""Let already-enrolled devices reach the fleet location default (W161 follow-up)

v1.12.0 made every enrolled device report its position on a fleet-wide interval,
injected into the effective policy at resolve time. It works for a device that
resolves — and a device already enrolled does not.

⚠️ **The cached payload is what a check-in answers from.** `get_effective` returns
the stored row unless it is marked stale, and nothing in an ATLAS update marks it:
not the lifespan hooks, not the seeder, not `docker compose up`. The row lives in
Postgres and survives the rebuild. So the feature reached every device enrolled
*after* the update and silently skipped the fleet that was already there — which
is the worst possible split, because it works perfectly on whatever device you
test with.

There was a manual way round it (saving Admin → Location calls `invalidate_all`),
but a feature whose delivery depends on the operator knowing an undocumented
ritual is not delivered. Marking the rows stale here means the next check-in
recomputes, exactly once, on the deploy that carries the change.

⚠️ **Stale is not a delete.** The payload stays, because it is the baseline
`refresh` compares against to decide whether `state_version` should actually move.
Deleting the rows would make every device look changed and wake the whole fleet
over nothing. A device whose resolved state genuinely does not move — one already
covered by a tracking policy — recomputes, compares equal, and is left alone.

The second half clears settings rows that hold an **empty string** for a key that
now displays a default. Blank and absent have always behaved identically for these
two (both fall back), but only absent renders the default in the form — so on a box
where someone once saved the Location group, the retention field showed an empty
box beside help text promising 30. That is the ambiguity the default was added to
remove. No intent is lost: there has never been a way to mean anything by blank.

Revision ID: g4i6k8m0o2q4
Revises: f3h5j7l9n1p3
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "g4i6k8m0o2q4"
down_revision = "f3h5j7l9n1p3"
branch_labels = None
depends_on = None

#: Keys whose form field gained a displayed default in v1.12.0.
#:
#: ⚠️ Listed literally rather than imported from `settings_store`. A migration has
#: to keep doing the same thing years from now, and importing app code makes it do
#: whatever that code happens to say at the time it is finally run.
_DEFAULTED_KEYS = ("location.retention_days", "location.default_interval_minutes")


def upgrade() -> None:
    connection = op.get_bind()

    stale = connection.execute(
        sa.text("UPDATE effective_policy_cache SET stale = true WHERE stale = false")
    ).rowcount
    print(f"location default: {stale} device(s) will recompute on their next check-in")

    cleared = connection.execute(
        sa.text(
            "DELETE FROM app_setting "
            "WHERE key IN :keys AND (value IS NULL OR trim(value) = '')"
        ).bindparams(sa.bindparam("keys", expanding=True)),
        {"keys": list(_DEFAULTED_KEYS)},
    ).rowcount
    if cleared:
        print(f"location default: cleared {cleared} blank setting(s) so the form shows them")


def downgrade() -> None:
    """Nothing to undo.

    ⚠️ Deliberately empty rather than "restore what was there". A stale flag is a
    cache instruction, not data — the rows re-populate on the next read, and the
    only thing a downgrade could restore is the *stalenesss*, which nobody wants
    back. Re-inserting the blank settings rows would likewise recreate a display
    bug on purpose.

    Downgrading past this leaves the fleet correctly computed, which is the state
    an older ATLAS is perfectly happy with: the injected interval simply stops
    being added on the next recompute.
    """
