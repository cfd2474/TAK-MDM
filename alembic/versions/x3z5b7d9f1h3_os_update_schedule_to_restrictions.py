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

"""OS update schedule moves to Restrictions (W481)

The standard Android schedule left Knox Configurations (SYSTEM_CONFIG) for
Restrictions › OS updates. ⚠️ The saved values are dropped from SYSTEM_CONFIG
versions, as W468 did: specs are `extra="forbid"`, only dev test policies held
them (no main release has SYSTEM_CONFIG), and the operator sets the schedule
again in Restrictions. Caches are marked stale.

Revision ID: x3z5b7d9f1h3
Revises: w2y4a6c8e0g2
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "x3z5b7d9f1h3"
down_revision = "w2y4a6c8e0g2"
branch_labels = None
depends_on = None

KEYS = ("os_update_mode", "os_update_window_start", "os_update_window_end")


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text(
        "SELECT v.id, v.spec FROM policy_version v JOIN policy p ON p.id = v.policy_id "
        "WHERE p.policy_type = 'SYSTEM_CONFIG'"
    )).fetchall()
    for row in rows:
        spec = row.spec
        raw = json.loads(spec) if isinstance(spec, str) else spec
        if not isinstance(raw, dict) or not any(k in raw for k in KEYS):
            continue
        kept = {k: v for k, v in raw.items() if k not in KEYS}
        connection.execute(
            sa.text("UPDATE policy_version SET spec = :spec WHERE id = :id"),
            {"spec": json.dumps(kept) if isinstance(spec, str) else kept, "id": row.id},
        )
    connection.execute(sa.text("UPDATE effective_policy_cache SET stale = true WHERE stale = false"))


def downgrade() -> None:
    """Nothing to put back: the values were dropped on purpose."""
