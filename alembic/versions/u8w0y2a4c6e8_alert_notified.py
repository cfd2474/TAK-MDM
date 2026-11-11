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

"""alert_occurrence.notified_at (W195)

When an alert was included in a message. NULL means nobody has been told.

Nullable, so every occurrence raised before ATLAS could send anything is
correctly "not yet sent" rather than wrongly "already handled".

Revision ID: u8w0y2a4c6e8
Revises: s6u8w0y2a4c6
"""

from alembic import op
import sqlalchemy as sa

from app.db.base import UtcDateTime

revision = "u8w0y2a4c6e8"
down_revision = "s6u8w0y2a4c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "alert_occurrence", sa.Column("notified_at", UtcDateTime(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("alert_occurrence", "notified_at")
