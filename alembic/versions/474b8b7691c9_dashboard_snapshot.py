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

"""dashboard snapshots (W442)

One reading a day of the dashboard's trend figures, keyed by the console's
local date.

Revision ID: 474b8b7691c9
Revises: ac716cdb78b4
"""

from alembic import op
import sqlalchemy as sa

revision = "474b8b7691c9"
down_revision = "ac716cdb78b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dashboard_snapshot",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), autoincrement=True, nullable=False),
        sa.Column("day", sa.String(length=10), nullable=False),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("devices", sa.Integer(), nullable=False),
        sa.Column("checked_in_1h", sa.Integer(), nullable=False),
        sa.Column("checked_in_24h", sa.Integer(), nullable=False),
        sa.Column("stale_30d", sa.Integer(), nullable=False),
        sa.Column("low_battery", sa.Integer(), nullable=False),
        sa.Column("disk_percent", sa.Float(), nullable=True),
        sa.Column("memory_percent", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("day"),
    )


def downgrade() -> None:
    op.drop_table("dashboard_snapshot")
