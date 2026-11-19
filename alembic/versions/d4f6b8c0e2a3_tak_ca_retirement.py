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

"""tak ca retirement (W453)

The TAK Server intermediate CAs devices are being moved off. Empty until an
operator retires one.

Revision ID: d4f6b8c0e2a3
Revises: c3e5a7b9d1f2
"""

from alembic import op
import sqlalchemy as sa

import app.db.base  # UtcDateTime, as autogenerate emits it

revision = "d4f6b8c0e2a3"
down_revision = "c3e5a7b9d1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tak_ca_retirement",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("issuer", sa.String(length=1024), nullable=False),
        sa.Column("retire_by", sa.Date(), nullable=True),
        sa.Column("started_at", app.db.base.UtcDateTime(timezone=True), nullable=False),
        sa.Column("started_by", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("issuer"),
    )


def downgrade() -> None:
    op.drop_table("tak_ca_retirement")
