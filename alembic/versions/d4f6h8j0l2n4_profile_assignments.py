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

"""profile assignments

Revision ID: d4f6h8j0l2n4
Revises: c3e5g7i9k1m3
Create Date: 2026-09-02 14:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

import app.db.base


revision: str = "d4f6h8j0l2n4"
down_revision: str | None = "c3e5g7i9k1m3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "profile_assignment",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column(
            "scope",
            sa.Enum(
                "DEVICE", "GROUP", "TAG",
                name="assignmentscope", native_enum=False, length=16,
            ),
            nullable=False,
        ),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("group_id", sa.Uuid(), nullable=True),
        sa.Column("tag_id", sa.Uuid(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", app.db.base.UtcDateTime(), nullable=False),
        sa.CheckConstraint(
            "(CASE WHEN device_id IS NOT NULL THEN 1 ELSE 0 END) "
            "+ (CASE WHEN group_id IS NOT NULL THEN 1 ELSE 0 END) "
            "+ (CASE WHEN tag_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_profile_assignment_single_target",
        ),
        sa.ForeignKeyConstraint(["profile_id"], ["policy_profile.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["group_id"], ["device_group.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tag.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_profile_assignment_profile_id"), "profile_assignment", ["profile_id"]
    )
    op.create_index(
        op.f("ix_profile_assignment_device_id"), "profile_assignment", ["device_id"]
    )
    op.create_index(
        op.f("ix_profile_assignment_group_id"), "profile_assignment", ["group_id"]
    )
    op.create_index(
        op.f("ix_profile_assignment_tag_id"), "profile_assignment", ["tag_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_profile_assignment_tag_id"), table_name="profile_assignment")
    op.drop_index(op.f("ix_profile_assignment_group_id"), table_name="profile_assignment")
    op.drop_index(op.f("ix_profile_assignment_device_id"), table_name="profile_assignment")
    op.drop_index(op.f("ix_profile_assignment_profile_id"), table_name="profile_assignment")
    op.drop_table("profile_assignment")
