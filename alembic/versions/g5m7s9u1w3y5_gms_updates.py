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

"""ATLAS keeps Google Play services updated (W517)

`device.gms_version_code`: the Google Play services build a device has, from its
Play profile (`GSF.version`). `gms_update_status`: one row per device model, what
the last Play check for it found. `gms_model_build`: which library builds Google
Play served to which model (two models can share one build, W517 C2).

Revision ID: g5m7s9u1w3y5
Revises: w5q1a9c3e7g2
"""

from alembic import op
import sqlalchemy as sa

revision = "g5m7s9u1w3y5"
down_revision = "w5q1a9c3e7g2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("device", sa.Column("gms_version_code", sa.BigInteger(), nullable=True))
    op.create_table(
        "gms_update_status",
        sa.Column("model_key", sa.String(length=64), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("play_version_code", sa.BigInteger(), nullable=True),
        sa.Column("play_version_name", sa.String(length=128), nullable=True),
        sa.Column("imported_version_code", sa.BigInteger(), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("model_key"),
    )
    op.create_table(
        "gms_model_build",
        sa.Column("model_key", sa.String(length=64), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["app_package_version.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("model_key", "version_id"),
    )


def downgrade() -> None:
    op.drop_table("gms_model_build")
    op.drop_table("gms_update_status")
    op.drop_column("device", "gms_version_code")
