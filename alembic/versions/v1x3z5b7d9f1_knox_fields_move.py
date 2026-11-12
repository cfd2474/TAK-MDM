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

"""Knox fields move to Knox Configurations (W468)

Operator, 2026-11-11: every Knox item lives in Knox Configurations
(SYSTEM_CONFIG). The fields below left Restrictions, Network data use and App
Management.

⚠️ **Their saved values are dropped, not moved** — the operator's choice. Only
dev test policies held them (no release on main had these fields), and moving
them would mean inventing a new Knox Configurations policy per old one. The
operator sets them again under Knox Configurations.

⚠️ **The keys have to leave stored specs**, not just the models: specs are
`extra="forbid"`, so a version still carrying one would stop validating (the
same reason as `p8r0t2v4x6z8`). Removed **only from the policy type each came
from**: the names do not occur elsewhere, but a policy type is the only thing
that says which spec a key belongs to.

⚠️ **The list is frozen here**, not imported from `knox_controls`: a migration
must mean the same thing forever, whatever the code says later. A test checks
it matches the code today.

Effective-policy caches are marked stale so every device recomputes once.

Revision ID: v1x3z5b7d9f1
Revises: u9w1y3a5c7e9
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "v1x3z5b7d9f1"
down_revision = "u9w1y3a5c7e9"
branch_labels = None
depends_on = None

MOVED = {
    "RESTRICTIONS": (
        "allow_cellular_data", "allow_bluetooth_discoverable", "allow_tethering", "allow_usb_tethering",
        "allow_data_roaming", "allow_roaming_push", "allow_roaming_sync", "allow_roaming_voice_calls",
        "allow_power_off", "allow_microphone", "allow_settings_changes", "allow_clipboard",
        "allow_share_list", "allow_smart_clip",
        "allow_usb_host_storage", "allow_sd_card_write", "usb_allowed_classes",
    ),
    "NETWORK_DATA_USE": (
        "block_wifi", "block_mobile", "restrict_rules", "allowed_apps", "app_restrict_rules",
        "app_block_rules",
    ),
    "APP_CATALOG": ("battery_optimization_exceptions",),
}


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text(
        "SELECT v.id, v.spec, p.policy_type FROM policy_version v JOIN policy p ON p.id = v.policy_id"
    )).fetchall()

    touched = 0
    for row in rows:
        keys = MOVED.get(row.policy_type)
        if not keys:
            continue
        spec = row.spec
        # ⚠️ SQLite hands back a string, Postgres a dict (see f3h5j7l9n1p3).
        raw = json.loads(spec) if isinstance(spec, str) else spec
        if not isinstance(raw, dict) or not any(k in raw for k in keys):
            continue
        kept = {k: v for k, v in raw.items() if k not in keys}
        connection.execute(
            sa.text("UPDATE policy_version SET spec = :spec WHERE id = :id"),
            {"spec": json.dumps(kept) if isinstance(spec, str) else kept, "id": row.id},
        )
        touched += 1

    stale = connection.execute(
        sa.text("UPDATE effective_policy_cache SET stale = true WHERE stale = false")
    ).rowcount
    if touched:
        print(f"knox fields move: dropped moved values from {touched} policy version(s); "
              f"{stale} device(s) recompute")


def downgrade() -> None:
    """Nothing to put back: the values were dropped on purpose."""
