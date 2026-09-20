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

"""google_play_link

The one Google account this instance downloads Play apps as (W99).

⚠️ **A table rather than `app_setting`, for the reason `tak_gov_link` gives:** it
carries a credential, and `app_setting` is plaintext. The AAS token column holds a
Fernet-sealed value and nothing else.

No row is created here. Absent means unlinked, which is the correct state for
every existing deployment — and it means the feature costs nothing until an
operator chooses it.

Revision ID: d0f2h4j6l8n0
Revises: b8d0f2h4j6l8
"""

from alembic import op
import sqlalchemy as sa

revision = "d0f2h4j6l8n0"
down_revision = "b8d0f2h4j6l8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "google_play_link",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="unlinked"),
        sa.Column("email", sa.String(length=256), nullable=True),
        sa.Column("aas_token_sealed", sa.Text(), nullable=True),
        sa.Column(
            "device_profile", sa.String(length=64), nullable=False, server_default="px_9a"
        ),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("linked_by", sa.String(length=128), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("google_play_link")
