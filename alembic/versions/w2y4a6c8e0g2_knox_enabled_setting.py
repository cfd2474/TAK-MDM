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

"""Samsung Knox on/off setting (W480)

The Admin switch `knox.enabled` replaces the W278 code constant. Off means hide
and stop. ⚠️ **Turned on where a Knox key is already saved**, so this update
changes nothing on a box already using Knox; a box without a key starts off.

Effective-policy caches are marked stale so every device recomputes once.

Revision ID: w2y4a6c8e0g2
Revises: v1x3z5b7d9f1
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "w2y4a6c8e0g2"
down_revision = "v1x3z5b7d9f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    has_key = connection.execute(sa.text(
        "SELECT 1 FROM app_setting WHERE key = 'knox.license_key' AND value <> ''"
    )).first()
    exists = connection.execute(sa.text("SELECT 1 FROM app_setting WHERE key = 'knox.enabled'")).first()
    if has_key and not exists:
        connection.execute(sa.text(
            "INSERT INTO app_setting (key, value, updated_at, updated_by) "
            "VALUES ('knox.enabled', 'true', CURRENT_TIMESTAMP, 'migration')"
        ))
    connection.execute(sa.text("UPDATE effective_policy_cache SET stale = true WHERE stale = false"))


def downgrade() -> None:
    op.get_bind().execute(sa.text("DELETE FROM app_setting WHERE key = 'knox.enabled'"))
