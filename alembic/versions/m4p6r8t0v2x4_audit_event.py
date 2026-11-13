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

"""audit_event (W421)

One row per change made through the console or the admin API, hash-chained.

Revision ID: m4p6r8t0v2x4
Revises: k8m2p4r6t8v0
"""

from alembic import op
import sqlalchemy as sa

revision = "m4p6r8t0v2x4"
down_revision = "k8m2p4r6t8v0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_event",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("actor_groups", sa.String(512), nullable=True),
        sa.Column("anonymous", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_ip", sa.String(64), nullable=True),
        sa.Column("method", sa.String(8), nullable=False),
        sa.Column("path", sa.String(512), nullable=False),
        sa.Column("action", sa.String(64), nullable=False, server_default="request"),
        sa.Column("target_type", sa.String(32), nullable=True),
        sa.Column("target_id", sa.String(64), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("hash", name="uq_audit_event_hash"),
        sa.UniqueConstraint("seq", name="uq_audit_event_seq"),
    )
    for column in ("occurred_at", "actor", "action", "target_type", "target_id"):
        op.create_index(f"ix_audit_event_{column}", "audit_event", [column])


def downgrade() -> None:
    for column in ("occurred_at", "actor", "action", "target_type", "target_id"):
        op.drop_index(f"ix_audit_event_{column}", table_name="audit_event")
    op.drop_table("audit_event")
