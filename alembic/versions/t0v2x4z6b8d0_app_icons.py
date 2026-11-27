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

"""app_package: launcher icon extracted from the APK (W53)

`icon_adaptive` is NOT NULL and therefore carries a `server_default`. Autogenerate
never infers one, and adding a NOT NULL column without it fails outright on a
Postgres table that already has rows — the defect this project has hit before
(D35).

Revision ID: t0v2x4z6b8d0
Revises: r8t0v2x4z6b8
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "t0v2x4z6b8d0"
down_revision = "r8t0v2x4z6b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_package", sa.Column("icon_data", sa.LargeBinary(), nullable=True))
    op.add_column("app_package", sa.Column("icon_media_type", sa.String(length=32), nullable=True))
    # Which version's APK the backfill last inspected. Nullable with no default:
    # every existing row is "never inspected", which is exactly right.
    op.add_column("app_package", sa.Column("icon_source_version_id", sa.Uuid(), nullable=True))
    op.add_column(
        "app_package",
        sa.Column(
            "icon_adaptive",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("app_package", "icon_source_version_id")
    op.drop_column("app_package", "icon_adaptive")
    op.drop_column("app_package", "icon_media_type")
    op.drop_column("app_package", "icon_data")
