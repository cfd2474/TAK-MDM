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

"""device_location — where devices have been (W106)

⚠️ **The one table here expected to reach millions of rows**, which is why it
takes a `bigint` identity key rather than the `uuid4` every other table uses.
Random keys scatter each insert across the index instead of filling the rightmost
page; on an append-only table that costs write throughput and bloats the index
exactly as it grows. Nothing references a point by id.

**Two timestamps, deliberately.** `recorded_at` is the device's fix time — which
may be hours stale, because the agent reports *last known* position on purpose,
and may be wrong outright if the device clock is. `received_at` is when this
server was told, the only one we can vouch for. Keeping both is what
distinguishes "the device was here an hour ago" from "the device was silent for
six hours and then delivered all of it at once".

The CHECK constraints are at the database rather than only in Pydantic because a
latitude of 91 is not a coordinate and a NaN poisons every bounding box computed
from the table afterwards — including ones drawn long after the bad row landed.

Revision ID: f2h4j6l8n0p2
Revises: d0f2h4j6l8n0
"""

from alembic import op
import sqlalchemy as sa

revision = "f2h4j6l8n0p2"
down_revision = "d0f2h4j6l8n0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "device_location",
        # bigint on Postgres, INTEGER on SQLite: SQLite auto-assigns a rowid only
        # for a column declared exactly `INTEGER PRIMARY KEY`, so a BIGINT key
        # there is an ordinary column that stays NULL on every insert.
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("accuracy_m", sa.Float(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "PERIODIC",
                "COMMAND",
                "GEOFENCE",
                name="locationsource",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "latitude >= -90 AND latitude <= 90", name="ck_device_location_latitude"
        ),
        sa.CheckConstraint(
            "longitude >= -180 AND longitude <= 180",
            name="ck_device_location_longitude",
        ),
        sa.CheckConstraint(
            "accuracy_m IS NULL OR accuracy_m >= 0", name="ck_device_location_accuracy"
        ),
    )
    op.create_index(
        "ix_device_location_device_id", "device_location", ["device_id"]
    )
    # Every read is "this device, newest first": the latest point on the detail
    # page, a history range, and the retention purge alike.
    op.create_index(
        "ix_device_location_device_recorded",
        "device_location",
        ["device_id", "recorded_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_device_location_device_recorded", table_name="device_location")
    op.drop_index("ix_device_location_device_id", table_name="device_location")
    op.drop_table("device_location")
