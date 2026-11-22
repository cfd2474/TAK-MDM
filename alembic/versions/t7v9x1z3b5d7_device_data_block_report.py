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

"""device_data_block_report

The data blocks a device's NETWORK_DATA_USE policy asks for, and whether the
Knox firewall carries them out (W465), with when the server received it. NULL
means never reported: an older agent.

Revision ID: t7v9x1z3b5d7
Revises: s5u7w9y1a3c5
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "t7v9x1z3b5d7"
down_revision = "s5u7w9y1a3c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "device",
        sa.Column(
            "data_block_report",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
    )
    op.add_column("device", sa.Column("data_block_reported_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("device", "data_block_reported_at")
    op.drop_column("device", "data_block_report")
