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

"""enrollment_qr_recipe (W204, GitHub issue #2)

How to reproduce a permanent enrollment QR: which token, which group, which
Wi-Fi. No QR and no enrollment secret is stored — a permanent QR carries the
token's own secret, which is already sealed on `enrollment_token`, and that is
what makes re-rendering byte-identical rather than minting a second credential.

⚠️ Both foreign keys are ON DELETE CASCADE, and the group one deliberately so.
A NULL group means "every device" in this payload, so SET NULL would silently
widen a group-scoped QR into an all-devices one. Losing the row is the honest
outcome: the QR it described cannot be made any more.

Revision ID: w0y2a4c6e8g0
Revises: u8w0y2a4c6e8
"""

from alembic import op
import sqlalchemy as sa

from app.db.base import UtcDateTime

revision = "w0y2a4c6e8g0"
down_revision = "u8w0y2a4c6e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "enrollment_qr_recipe",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("token_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=True),
        sa.Column("wifi_ssid", sa.String(length=64), nullable=True),
        sa.Column("wifi_security", sa.String(length=16), nullable=True),
        # Vault ciphertext, never plaintext.
        sa.Column("wifi_password_ciphertext", sa.Text(), nullable=True),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.Column("last_shown_at", UtcDateTime(), nullable=True),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(
            ["token_id"], ["enrollment_token.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["group_id"], ["device_group.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_enrollment_qr_recipe_token_id", "enrollment_qr_recipe", ["token_id"]
    )
    op.create_index(
        "ix_enrollment_qr_recipe_group_id", "enrollment_qr_recipe", ["group_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_enrollment_qr_recipe_group_id", table_name="enrollment_qr_recipe")
    op.drop_index("ix_enrollment_qr_recipe_token_id", table_name="enrollment_qr_recipe")
    op.drop_table("enrollment_qr_recipe")
