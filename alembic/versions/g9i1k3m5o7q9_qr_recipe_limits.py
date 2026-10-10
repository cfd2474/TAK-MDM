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

"""qr_recipe_limits

Enrolment QR codes with a use count and/or an expiry (W330). Existing recipes are
permanent QRs: `limited` false, no expiry, no use limit.

Revision ID: g9i1k3m5o7q9
Revises: f8h0j2l4n6p8
"""

from alembic import op
import sqlalchemy as sa

from app.db.base import UtcDateTime

revision = "g9i1k3m5o7q9"
down_revision = "f8h0j2l4n6p8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("enrollment_qr_recipe",
                  sa.Column("limited", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("enrollment_qr_recipe", sa.Column("expires_at", UtcDateTime(), nullable=True))
    op.add_column("enrollment_qr_recipe", sa.Column("max_uses", sa.Integer(), nullable=True))
    op.add_column("enrollment_qr_recipe",
                  sa.Column("use_count", sa.Integer(), nullable=False, server_default=sa.text("0")))


def downgrade() -> None:
    op.drop_column("enrollment_qr_recipe", "use_count")
    op.drop_column("enrollment_qr_recipe", "max_uses")
    op.drop_column("enrollment_qr_recipe", "expires_at")
    op.drop_column("enrollment_qr_recipe", "limited")
