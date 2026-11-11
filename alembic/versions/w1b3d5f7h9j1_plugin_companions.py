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

"""app_package_companion (W407)

Which ATAK plugin build carried which companion app build, so ATLAS installs
the companion itself instead of the plugin asking the user to. And
`app_package_version.companions_scanned`, so the boot-time backfill reads each
plugin already in the library once.

Revision ID: w1b3d5f7h9j1
Revises: v9z1b3d5f7h9
"""

from alembic import op
import sqlalchemy as sa

revision = "w1b3d5f7h9j1"
down_revision = "v9z1b3d5f7h9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_package_companion",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("plugin_version_id", sa.Uuid(), nullable=False),
        sa.Column("companion_version_id", sa.Uuid(), nullable=False),
        sa.Column("asset_path", sa.String(512), nullable=False),
        sa.Column("launchable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(
            ["plugin_version_id"], ["app_package_version.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["companion_version_id"], ["app_package_version.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "plugin_version_id", "companion_version_id", name="uq_companion_link"
        ),
    )
    op.create_index(
        "ix_app_package_companion_plugin_version_id",
        "app_package_companion",
        ["plugin_version_id"],
    )
    op.create_index(
        "ix_app_package_companion_companion_version_id",
        "app_package_companion",
        ["companion_version_id"],
    )
    op.add_column(
        "app_package_version",
        sa.Column("companions_scanned", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("app_package_version", "companions_scanned")
    op.drop_index(
        "ix_app_package_companion_companion_version_id", table_name="app_package_companion"
    )
    op.drop_index(
        "ix_app_package_companion_plugin_version_id", table_name="app_package_companion"
    )
    op.drop_table("app_package_companion")
