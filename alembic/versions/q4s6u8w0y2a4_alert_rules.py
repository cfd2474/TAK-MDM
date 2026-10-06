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

"""alert_rule (W195)

What is worth being told about. Three kinds — an event as it happens, a
check-in threshold, and operator-defined conditions over device fields — with
the per-kind config carried as JSON and validated by
`app.services.alert_rules`.

⚠️ **No table of kinds, and no enum column.** The kind is a short string
validated against a registry in code, for the reason `Policy.policy_type`
carries the same comment: adding a kind should be a validator and nothing else,
never a migration.

⚠️ `enabled` carries a `server_default` (D35). The table is new, so it cannot
bite today — it is written this way because the next person to copy this file
will not be creating one.

Revision ID: q4s6u8w0y2a4
Revises: o2q4s6u8w0y2
"""

from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

from app.db.base import UtcDateTime

revision = "q4s6u8w0y2a4"
down_revision = "o2q4s6u8w0y2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_rule",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        # ⚠️ Spelled out rather than importing `JsonDict`: that name is a
        # type *instance* in `app.db.base`, so calling it raises. Every other
        # migration in this tree writes the variant longhand.
        sa.Column(
            "config",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=True),
    )
    op.create_index("ix_alert_rule_kind", "alert_rule", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_alert_rule_kind", table_name="alert_rule")
    op.drop_table("alert_rule")
