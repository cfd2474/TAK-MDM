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

"""app store flag and app groups

Revision ID: e5g7i9k1m3o5
Revises: d4f6h8j0l2n4
Create Date: 2026-09-02 16:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

import app.db.base


revision: str = "e5g7i9k1m3o5"
down_revision: str | None = "d4f6h8j0l2n4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "app_package",
        sa.Column(
            "store_listed", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.create_table(
        "app_group",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", app.db.base.UtcDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_app_group_name"),
    )
    op.create_table(
        "app_group_member",
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("package_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["app_group.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["package_id"], ["app_package.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("group_id", "package_id"),
    )


def downgrade() -> None:
    op.drop_table("app_group_member")
    op.drop_table("app_group")
    op.drop_column("app_package", "store_listed")
