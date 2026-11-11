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

"""app_package_version.abis

⚠️ **Nullable on purpose, and NULL is not "universal".** Every row that exists
when this runs was uploaded before anything read `lib/`, so nothing is known about
its native code. An empty string means the opposite — scanned, carries none, runs
on any device.

Collapsing the two would be the worst possible default: an arm64-only APK
uploaded last month would read as "runs anywhere", which is exactly the claim that
left an SM-X520 permanently DEGRADED (R19). Existing rows stay NULL until
something re-reads them.

Revision ID: x4z6b8d0f2h4
Revises: v2x4z6b8d0f2
"""

from alembic import op
import sqlalchemy as sa

revision = "x4z6b8d0f2h4"
down_revision = "v2x4z6b8d0f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_package_version",
        sa.Column("abis", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("app_package_version", "abis")
