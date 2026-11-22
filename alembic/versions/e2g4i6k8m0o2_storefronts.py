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

"""Storefronts, and the end of the server-wide shelf (W140)

`app_package.store_listed` made the ATLAS store one curated set every enrolled
device saw. A `storefront` is a named version of that store which a policy
assigns, so different devices can be offered different shelves.

⚠️ **Store membership is destroyed, not migrated.** A boolean per package does
not carry enough information to become a storefront: it says *which* apps were
on the shelf but not which build of each, and a storefront names builds. There
is no honest automatic conversion — inventing "the newest build" would
reintroduce exactly the automatic selection W139 removed. Any deployment
upgrading through this rebuilds its shelf by hand, once.

Checked against this project's only deployment before writing, and the first
guess was wrong: **four packages were on the shelf**, and they are named here so
the list survives the column that held it.

    com.beartooth.beartoothtakplugin
    com.atakmap.android.fobs.plugin
    com.taksolutions.uasready
    com.nht.edgescout

Rebuilding that as a storefront is a minute's work and it is the operator's
choice which build of each to offer. Deriving it here would have meant this
migration picking builds on their behalf.

⚠️ The downgrade brings the column back empty. It cannot restore what was on the
shelf; nothing records that once the storefronts are dropped.

Revision ID: e2g4i6k8m0o2
Revises: d1f3h5j7l9n1
Create Date: 2026-09-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e2g4i6k8m0o2"
down_revision = "d1f3h5j7l9n1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "storefront",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "storefront_item",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "storefront_id",
            sa.Uuid(),
            sa.ForeignKey("storefront.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "package_id",
            sa.Uuid(),
            sa.ForeignKey("app_package.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # A build leaving the library takes its shelf entry with it. An entry
        # pointing at nothing would either vanish from the shelf silently or be
        # resolved to some other build of the same app, and a shelf that changes
        # what it offers without anyone deciding to is what this design prevents.
        sa.Column(
            "version_id",
            sa.Uuid(),
            sa.ForeignKey("app_package_version.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint(
            "storefront_id", "package_id", name="uq_storefront_one_entry_per_package"
        ),
    )
    op.drop_column("app_package", "store_listed")


def downgrade() -> None:
    op.add_column(
        "app_package",
        sa.Column(
            "store_listed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.drop_table("storefront_item")
    op.drop_table("storefront")
