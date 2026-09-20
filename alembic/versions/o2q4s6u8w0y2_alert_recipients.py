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

"""alert_recipient (W195)

Who is told when the fleet needs attention.

⚠️ `address` is unique and stored lower-cased by the service. Two rows differing
only in case are one person receiving every alert twice, and the second copy is
the one that teaches them to filter the first.

⚠️ `enabled` has a `server_default` (D35): a NOT NULL column added without one
fails on Postgres against a table with rows. The table is new here, so it cannot
bite today — it is written this way because the next person to copy this file
will not be adding a new table.

Revision ID: o2q4s6u8w0y2
Revises: m0o2q4s6u8w0
"""

from alembic import op
import sqlalchemy as sa

from app.db.base import UtcDateTime

revision = "o2q4s6u8w0y2"
down_revision = "m0o2q4s6u8w0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_recipient",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("address", sa.String(length=320), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=True),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_alert_recipient_address", "alert_recipient", ["address"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_alert_recipient_address", table_name="alert_recipient")
    op.drop_table("alert_recipient")
