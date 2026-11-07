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

"""admin settings and custom attributes

Revision ID: g7i9k1m3o5q7
Revises: f6h8j0l2n4p6
Create Date: 2026-09-02 20:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

import app.db.base


revision: str = "g7i9k1m3o5q7"
down_revision: str | None = "f6h8j0l2n4p6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_setting",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", app.db.base.UtcDateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=128), nullable=True),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "custom_attribute",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("attr_type", sa.String(length=16), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", app.db.base.UtcDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_custom_attribute_name"),
    )
    op.create_table(
        "device_attribute_value",
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("attribute_id", sa.Uuid(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["attribute_id"], ["custom_attribute.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("device_id", "attribute_id"),
    )


def downgrade() -> None:
    op.drop_table("device_attribute_value")
    op.drop_table("custom_attribute")
    op.drop_table("app_setting")
