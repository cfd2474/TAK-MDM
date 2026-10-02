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

"""device ATLAS plugin status

The ATLAS ATAK plugin's last status file, as the agent forwarded it (W303),
and when the server received it.

⚠️ **NULL means "the agent has never said"**, an agent older than the
feature. A device with no plugin running reports `{"present": false}`, which
is a different answer, and the console shows the two differently.

Revision ID: a3c5e7g9i1k3
Revises: y2a4c6e8g0i2
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.db.base import UtcDateTime

revision = "a3c5e7g9i1k3"
down_revision = "y2a4c6e8g0i2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "device",
        sa.Column(
            "atlas_plugin_report",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
    )
    op.add_column(
        "device", sa.Column("atlas_plugin_reported_at", UtcDateTime(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("device", "atlas_plugin_reported_at")
    op.drop_column("device", "atlas_plugin_report")
