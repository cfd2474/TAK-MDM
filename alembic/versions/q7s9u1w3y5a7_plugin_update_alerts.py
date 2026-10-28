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

"""plugin update alerts (W422)

An occurrence's subject (a package at a catalog build), and when a rule that
checks a catalog last ran.

Revision ID: q7s9u1w3y5a7
Revises: m4p6r8t0v2x4
"""

from alembic import op
import sqlalchemy as sa

revision = "q7s9u1w3y5a7"
down_revision = "m4p6r8t0v2x4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("alert_occurrence", sa.Column("subject", sa.String(255), nullable=True))
    op.create_index("ix_alert_occurrence_subject", "alert_occurrence", ["rule_id", "subject"])
    op.add_column("alert_rule", sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("alert_rule", sa.Column("last_result", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("alert_rule", "last_result")
    op.drop_column("alert_rule", "last_checked_at")
    op.drop_index("ix_alert_occurrence_subject", table_name="alert_occurrence")
    op.drop_column("alert_occurrence", "subject")
