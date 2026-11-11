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

"""enrollment holds (W448)

A re-enrollment of a managed device whose hardware did not prove it is the
same tablet, waiting for the security code.

Revision ID: b7d2e9f4c1a8
Revises: 474b8b7691c9
"""

from alembic import op
import sqlalchemy as sa

import app.db.base  # UtcDateTime, as autogenerate emits it

revision = "b7d2e9f4c1a8"
down_revision = "474b8b7691c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "enrollment_hold",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", app.db.base.UtcDateTime(timezone=True), nullable=False),
        sa.Column("expires_at", app.db.base.UtcDateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_enrollment_hold_device_id", "enrollment_hold", ["device_id"])


def downgrade() -> None:
    op.drop_index("ix_enrollment_hold_device_id", table_name="enrollment_hold")
    op.drop_table("enrollment_hold")
