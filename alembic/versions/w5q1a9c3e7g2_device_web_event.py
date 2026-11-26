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

"""device web activity (W501)

One row per (site, app) the ATLAS filter saw a device look up within a few
minutes, and (`device_app_usage`) how long each app was in front per day. See `DeviceWebEvent` for why the key is a bigint and why uploads are
idempotent on (device, stream, seq).

Revision ID: w5q1a9c3e7g2
Revises: a7c9e1g3i5k7
"""

from alembic import op
import sqlalchemy as sa

revision = "w5q1a9c3e7g2"
down_revision = "a7c9e1g3i5k7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "device_web_event",
        # bigint on Postgres, INTEGER on SQLite (see device_location).
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("stream", sa.BigInteger(), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("hostname", sa.String(length=253), nullable=False),
        sa.Column("package_name", sa.String(length=255), nullable=True),
        sa.Column("looked_up_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lookups", sa.Integer(), nullable=False),
        sa.Column("blocked", sa.Boolean(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", "stream", "seq", name="uq_device_web_event_seq"),
        sa.CheckConstraint("lookups >= 1", name="ck_device_web_event_lookups"),
    )
    op.create_index(
        "ix_device_web_event_device_time", "device_web_event", ["device_id", "looked_up_at"]
    )
    op.create_index(
        "ix_device_web_event_host_time", "device_web_event", ["hostname", "looked_up_at"]
    )
    op.create_table(
        "device_app_usage",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("package_name", sa.String(length=255), nullable=False),
        sa.Column("foreground_ms", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", "day", "package_name", name="uq_device_app_usage_day"),
        sa.CheckConstraint("foreground_ms >= 0", name="ck_device_app_usage_ms"),
    )


def downgrade() -> None:
    op.drop_table("device_app_usage")
    op.drop_index("ix_device_web_event_host_time", table_name="device_web_event")
    op.drop_index("ix_device_web_event_device_time", table_name="device_web_event")
    op.drop_table("device_web_event")
