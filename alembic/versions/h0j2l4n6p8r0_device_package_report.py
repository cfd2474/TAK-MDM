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

"""device_package_report

The latest Device Package List Report per device (W335).

Revision ID: h0j2l4n6p8r0
Revises: g9i1k3m5o7q9
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.db.base import UtcDateTime

revision = "h0j2l4n6p8r0"
down_revision = "g9i1k3m5o7q9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "device_package_report",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("device_id", sa.Uuid(), sa.ForeignKey("device.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("command_id", sa.Uuid(),
                  sa.ForeignKey("device_command.id", ondelete="SET NULL"), nullable=True),
        sa.Column("packages", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
                  nullable=False),
        sa.Column("package_count", sa.Integer(), nullable=False),
        sa.Column("agent_version", sa.String(32), nullable=True),
        sa.Column("collected_at", UtcDateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("device_package_report")
