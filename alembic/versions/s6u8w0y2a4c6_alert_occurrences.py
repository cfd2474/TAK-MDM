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

"""alert_occurrence (W195)

One time one rule had something to say about one device — and the reason
alerting does not repeat itself.

⚠️ `cleared_at` NULL means "still true". A device with no check-in for 72 hours
also has none for 73, so while an occurrence is open the same rule raises
nothing further about the same device. Without that column this feature is an
email every sweep for every quiet device, for ever.

⚠️ The rule is ON DELETE CASCADE; the **device is SET NULL**, and disenrolment
is why. `disenroll.complete` deletes the device row — that is what disenrolment
is — so a cascade would delete the "device disenrolled" alert in the same breath
as recording it. `detail` carries the serial, because an alert whose subject has
been deleted still has to say who it was about.

Revision ID: s6u8w0y2a4c6
Revises: q4s6u8w0y2a4
"""

from alembic import op
import sqlalchemy as sa

from app.db.base import UtcDateTime

revision = "s6u8w0y2a4c6"
down_revision = "q4s6u8w0y2a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_occurrence",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("rule_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("raised_at", UtcDateTime(), nullable=False),
        sa.Column("cleared_at", UtcDateTime(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["alert_rule.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_alert_occurrence_rule_id", "alert_occurrence", ["rule_id"])
    op.create_index("ix_alert_occurrence_device_id", "alert_occurrence", ["device_id"])
    # ⚠️ The index the suppression check runs on — every sweep, for every rule
    # and every device. Without it, asking "is one already open" costs more the
    # longer the deployment has been alerting.
    op.create_index(
        "ix_alert_occurrence_open",
        "alert_occurrence",
        ["rule_id", "device_id", "cleared_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_alert_occurrence_open", table_name="alert_occurrence")
    op.drop_index("ix_alert_occurrence_device_id", table_name="alert_occurrence")
    op.drop_index("ix_alert_occurrence_rule_id", table_name="alert_occurrence")
    op.drop_table("alert_occurrence")
