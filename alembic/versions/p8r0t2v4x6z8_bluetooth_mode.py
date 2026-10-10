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

"""Bluetooth becomes a mode (W364)

Restrictions' Bluetooth was a two-way switch, `allow_bluetooth`, merged most
restrictive. W364 makes it `bluetooth_mode` (allow / block / keep on), merged by
rank, as the operator asked: a "keep on" in a higher-ranked policy must beat a
"block" below it, which two separate fields could never do.

⚠️ **The key has to change in stored specs, not just in the model.** Specs are
`extra="forbid"`, and the resolver reads stored JSON field by field, so a version
still carrying `allow_bluetooth` would both stop validating and stop contributing.
The values mean the same thing afterwards: Allowed is `allow`, Blocked is
`block`.

The cached effective policies are marked stale (not deleted, see
`g4i6k8m0o2q4`), so every device recomputes once on its next check-in.

Revision ID: p8r0t2v4x6z8
Revises: o7q9s1u3w5y7
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "p8r0t2v4x6z8"
down_revision = "o7q9s1u3w5y7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, spec FROM policy_version")).fetchall()

    touched = 0
    for row in rows:
        spec = row.spec
        # ⚠️ SQLite hands back a string, Postgres a dict (see f3h5j7l9n1p3).
        raw = json.loads(spec) if isinstance(spec, str) else spec
        if not isinstance(raw, dict) or "allow_bluetooth" not in raw:
            continue
        raw = dict(raw)
        legacy = raw.pop("allow_bluetooth")
        if raw.get("bluetooth_mode") is None and legacy is not None:
            raw["bluetooth_mode"] = "allow" if legacy else "block"
        connection.execute(
            sa.text("UPDATE policy_version SET spec = :spec WHERE id = :id"),
            {"spec": json.dumps(raw) if isinstance(spec, str) else raw, "id": row.id},
        )
        touched += 1

    stale = connection.execute(
        sa.text("UPDATE effective_policy_cache SET stale = true WHERE stale = false")
    ).rowcount
    if touched:
        print(f"bluetooth mode: rewrote {touched} policy version(s); {stale} device(s) recompute")


def downgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, spec FROM policy_version")).fetchall()
    for row in rows:
        spec = row.spec
        raw = json.loads(spec) if isinstance(spec, str) else spec
        if not isinstance(raw, dict) or "bluetooth_mode" not in raw:
            continue
        raw = dict(raw)
        mode = raw.pop("bluetooth_mode")
        # "keep on" has no two-way equivalent; it allowed Bluetooth.
        if mode is not None:
            raw["allow_bluetooth"] = mode != "block"
        connection.execute(
            sa.text("UPDATE policy_version SET spec = :spec WHERE id = :id"),
            {"spec": json.dumps(raw) if isinstance(spec, str) else raw, "id": row.id},
        )
