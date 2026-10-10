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

"""record which ATAK build a plugin targets (W32)

An ATAK plugin only loads in the ATAK build it was compiled against, and the
manifest says which: `<meta-data android:name="plugin-api"
android:value="com.atakmap.app@5.5.0.CIV"/>`.

Left NULL here. Backfilling would mean re-reading every stored artifact from
inside a migration, which is slow, needs the artifact store, and fails for a row
whose blob has since been deleted. `app/services/packages.backfill_plugin_api()`
does it afterwards, where a missing artifact is a skipped row rather than a failed
migration.

Revision ID: l2n4p6r8t0v2
Revises: k1m3o5q7s9u1
Create Date: 2026-09-03 11:20:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "l2n4p6r8t0v2"
down_revision: str | None = "k1m3o5q7s9u1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "app_package_version",
        sa.Column("plugin_api", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("app_package_version", "plugin_api")
