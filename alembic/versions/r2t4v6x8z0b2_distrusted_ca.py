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

"""distrusted CAs (W432)

The operator's own entries on the distrusted-CA list. ATLAS's built-in entries
are code, not rows.

Revision ID: r2t4v6x8z0b2
Revises: q7s9u1w3y5a7
"""

from alembic import op
import sqlalchemy as sa

revision = "r2t4v6x8z0b2"
down_revision = "q7s9u1w3y5a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "distrusted_ca",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("added_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("sha256", name="uq_distrusted_ca_sha256"),
    )


def downgrade() -> None:
    op.drop_table("distrusted_ca")
