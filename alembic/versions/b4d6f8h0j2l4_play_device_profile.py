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

"""play_device_profile

How Google Play sees each device model in the fleet, captured from enrolled
devices (W312), so Play downloads can be made as that model. One row per
`Build.MODEL`; the newest capture replaces the last.

Revision ID: b4d6f8h0j2l4
Revises: a3c5e7g9i1k3
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.db.base import UtcDateTime

revision = "b4d6f8h0j2l4"
down_revision = "a3c5e7g9i1k3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "play_device_profile",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("model_key", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("manufacturer", sa.String(length=64), nullable=False),
        sa.Column(
            "properties",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("captured_from", sa.String(length=64), nullable=True),
        sa.Column("captured_at", UtcDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_key"),
    )


def downgrade() -> None:
    op.drop_table("play_device_profile")
