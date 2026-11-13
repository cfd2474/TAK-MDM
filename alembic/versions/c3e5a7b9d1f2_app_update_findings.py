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

"""app update findings (W454)

The newer builds each update-check rule last found, for the library badge and
the dashboard card. Empty until each rule next runs.

Revision ID: c3e5a7b9d1f2
Revises: b7d2e9f4c1a8
"""

from alembic import op
import sqlalchemy as sa

import app.db.base  # UtcDateTime, as autogenerate emits it

revision = "c3e5a7b9d1f2"
down_revision = "b7d2e9f4c1a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_update_finding",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.Uuid(), nullable=False),
        sa.Column("package_name", sa.String(length=255), nullable=False),
        sa.Column("version_code", sa.Integer(), nullable=False),
        sa.Column("version_name", sa.String(length=128), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("found_at", app.db.base.UtcDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["rule_id"], ["alert_rule.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_id", "package_name"),
    )
    op.create_index("ix_app_update_finding_rule_id", "app_update_finding", ["rule_id"])


def downgrade() -> None:
    op.drop_index("ix_app_update_finding_rule_id", table_name="app_update_finding")
    op.drop_table("app_update_finding")
