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

"""ATAK pref extracts (W433)

Each request for ATAK's configuration as a .pref, from the moment an admin asks
to the file arriving (or the plugin's error).

Revision ID: efc0648e4082
Revises: r2t4v6x8z0b2
"""

from alembic import op
import sqlalchemy as sa

revision = "efc0648e4082"
down_revision = "r2t4v6x8z0b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "atak_pref_extract",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("device_id", sa.Uuid(), sa.ForeignKey("device.id", ondelete="CASCADE"), nullable=False),
        sa.Column("command_id", sa.Uuid(), sa.ForeignKey("device_command.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("requested_by", sa.String(128), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("atak_version", sa.String(64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.UniqueConstraint("command_id", name="uq_atak_pref_extract_command_id"),
    )
    op.create_index("ix_atak_pref_extract_device_id", "atak_pref_extract", ["device_id"])


def downgrade() -> None:
    op.drop_index("ix_atak_pref_extract_device_id", table_name="atak_pref_extract")
    op.drop_table("atak_pref_extract")
