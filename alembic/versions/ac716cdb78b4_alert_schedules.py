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

"""alert schedules (W436)

When an update-check rule runs (a time of day and weekdays), and the scheduled
slot it last ran for. A NULL schedule is the default, every day at 06:00, so no
existing row needs rewriting.

Revision ID: ac716cdb78b4
Revises: efc0648e4082
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "ac716cdb78b4"
down_revision = "efc0648e4082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "alert_rule",
        sa.Column("schedule", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
                  nullable=True),
    )
    op.add_column("alert_rule", sa.Column("last_scheduled_run_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("alert_rule", "last_scheduled_run_at")
    op.drop_column("alert_rule", "schedule")
