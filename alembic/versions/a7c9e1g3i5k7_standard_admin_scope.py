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

"""standard_admin_scope (W495)

What each standard administrator may reach: granted categories, device groups
and devices, and the templates they may create policies from (B8), one row
per Authentik username. Empty on every existing box; only
a super admin fills it. The links cascade, so deleting a group or a device
takes it out of every scope.

Revision ID: a7c9e1g3i5k7
Revises: x3z5b7d9f1h3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a7c9e1g3i5k7"
down_revision = "x3z5b7d9f1h3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "standard_admin_scope",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("username", sa.String(150), nullable=False),
        sa.Column(
            "categories",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(150), nullable=True),
        sa.UniqueConstraint("username", name="uq_standard_admin_scope_username"),
    )
    op.create_table(
        "standard_admin_scope_group",
        sa.Column("scope_id", sa.Uuid(), primary_key=True),
        sa.Column("group_id", sa.Uuid(), primary_key=True),
        sa.ForeignKeyConstraint(
            ["scope_id"], ["standard_admin_scope.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["group_id"], ["device_group.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "standard_admin_scope_device",
        sa.Column("scope_id", sa.Uuid(), primary_key=True),
        sa.Column("device_id", sa.Uuid(), primary_key=True),
        sa.ForeignKeyConstraint(
            ["scope_id"], ["standard_admin_scope.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "standard_admin_scope_profile_template",
        sa.Column("scope_id", sa.Uuid(), primary_key=True),
        sa.Column("profile_id", sa.Uuid(), primary_key=True),
        sa.ForeignKeyConstraint(
            ["scope_id"], ["standard_admin_scope.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["policy_profile.id"], ondelete="CASCADE"
        ),
    )
    op.create_table(
        "standard_admin_scope_policy_template",
        sa.Column("scope_id", sa.Uuid(), primary_key=True),
        sa.Column("policy_id", sa.Uuid(), primary_key=True),
        sa.ForeignKeyConstraint(
            ["scope_id"], ["standard_admin_scope.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["policy_id"], ["policy.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("standard_admin_scope_policy_template")
    op.drop_table("standard_admin_scope_profile_template")
    op.drop_table("standard_admin_scope_device")
    op.drop_table("standard_admin_scope_group")
    op.drop_table("standard_admin_scope")
