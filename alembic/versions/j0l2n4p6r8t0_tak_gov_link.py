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

"""TAK.gov plugin catalog link (W29)

One row holding the OAuth device-authorization state and the offline refresh
token this instance pulls the TAK.gov plugin catalog with. A table rather than
settings because it carries a state machine and a credential that must not sit
in `app_setting`, which is plaintext.

Revision ID: j0l2n4p6r8t0
Revises: i9k1m3o5q7s9
Create Date: 2026-09-02 23:10:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "j0l2n4p6r8t0"
down_revision: str | None = "i9k1m3o5q7s9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tak_gov_link",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="unlinked"),
        sa.Column("device_code", sa.Text(), nullable=True),
        sa.Column("user_code", sa.String(length=64), nullable=True),
        sa.Column("verification_uri", sa.Text(), nullable=True),
        sa.Column("verification_uri_complete", sa.Text(), nullable=True),
        sa.Column(
            "poll_interval_seconds", sa.Integer(), nullable=False, server_default="5"
        ),
        sa.Column("code_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refresh_token_sealed", sa.Text(), nullable=True),
        sa.Column("previous_refresh_token_sealed", sa.Text(), nullable=True),
        sa.Column("access_token_sealed", sa.Text(), nullable=True),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("account_label", sa.String(length=256), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("linked_by", sa.String(length=128), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("tak_gov_link")
