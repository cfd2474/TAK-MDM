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

"""web_shortcut

Web links the console builds into apps (W336).

Revision ID: i1k3m5o7q9s1
Revises: h0j2l4n6p8r0
"""

from alembic import op
import sqlalchemy as sa

from app.db.base import UtcDateTime

revision = "i1k3m5o7q9s1"
down_revision = "h0j2l4n6p8r0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "web_shortcut",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("package_name", sa.String(64), nullable=False, unique=True),
        sa.Column("label", sa.String(64), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("icon_png", sa.LargeBinary(), nullable=False),
        sa.Column("version_code", sa.Integer(), nullable=False),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.Column("updated_at", UtcDateTime(), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("web_shortcut")
