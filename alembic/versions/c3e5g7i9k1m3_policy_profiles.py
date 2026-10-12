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

"""policy profiles

Revision ID: c3e5g7i9k1m3
Revises: b2d4f6a8c1e3
Create Date: 2026-09-02 12:00:00.000000

A profile bundles single-concern policies into one assignable unit (DW5). Each
tab of a profile is a real `policy` row with `profile_id` set.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

import app.db.base


revision: str = "c3e5g7i9k1m3"
down_revision: str | None = "b2d4f6a8c1e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "policy_profile",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", app.db.base.UtcDateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column("archived_at", app.db.base.UtcDateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_policy_profile_name"),
    )
    # Batch mode so this works on SQLite too (it rebuilds the table; Postgres does
    # a plain ALTER). SQLite cannot add a foreign key to an existing table any
    # other way.
    with op.batch_alter_table("policy") as batch_op:
        batch_op.add_column(sa.Column("profile_id", sa.Uuid(), nullable=True))
        batch_op.add_column(
            sa.Column("profile_section", sa.String(length=64), nullable=True)
        )
        batch_op.create_index(op.f("ix_policy_profile_id"), ["profile_id"])
        batch_op.create_foreign_key(
            "fk_policy_profile_id",
            "policy_profile",
            ["profile_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    with op.batch_alter_table("policy") as batch_op:
        batch_op.drop_constraint("fk_policy_profile_id", type_="foreignkey")
        batch_op.drop_index(op.f("ix_policy_profile_id"))
        batch_op.drop_column("profile_section")
        batch_op.drop_column("profile_id")
    op.drop_table("policy_profile")
