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

"""atak_session_log (W416)

ATAK session logs collected from devices: one row per session, the file
itself in `<artifact_dir>/atak-logs/<id>.gz`.

Revision ID: k8m2p4r6t8v0
Revises: w1b3d5f7h9j1
"""

from alembic import op
import sqlalchemy as sa

revision = "k8m2p4r6t8v0"
down_revision = "w1b3d5f7h9j1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "atak_session_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("session_key", sa.String(160), nullable=False),
        sa.Column("file_name", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("complete", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("stored_bytes", sa.Integer(), nullable=False),
        sa.Column("atak_version", sa.String(64), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("device_id", "session_key", name="uq_atak_session_log"),
    )
    op.create_index("ix_atak_session_log_device_id", "atak_session_log", ["device_id"])


def downgrade() -> None:
    op.drop_index("ix_atak_session_log_device_id", table_name="atak_session_log")
    op.drop_table("atak_session_log")
