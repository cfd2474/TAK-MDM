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

"""device_web_filter_report

The ATLAS filter app's last status, as the agent forwarded it (W369 F3), and
when the server received it. NULL means never reported: an older agent, or a
device without Web Filtering.

Revision ID: r1t3v5x7z9b1
Revises: q9s1u3w5y7a9
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "r1t3v5x7z9b1"
down_revision = "q9s1u3w5y7a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "device",
        sa.Column(
            "web_filter_report",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
    )
    op.add_column("device", sa.Column("web_filter_reported_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("device", "web_filter_reported_at")
    op.drop_column("device", "web_filter_report")
