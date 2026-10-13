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

"""app_version_declared_bundles

Each bundle's own declared settings (W357), so the device can build a nested
Bundle with the types the app reads. NULL = a build scanned before W357, filled
on first need.

Revision ID: m5o7q9s1u3w5
Revises: l4n6p8r0t2v4
"""

from alembic import op
import sqlalchemy as sa

revision = "m5o7q9s1u3w5"
down_revision = "l4n6p8r0t2v4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_package_version", sa.Column("declared_bundles", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("app_package_version", "declared_bundles")
