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

"""primary enrollment token

Revision ID: f2a91c6d4b78
Revises: c7d2f18b6e40
Create Date: 2026-09-02 09:10:00.000000

Adds ``is_primary`` to enrollment_token, plus a partial unique index enforcing
"at most one live primary" as a database guarantee (Chunk 14). No backfill: every
existing token defaults to is_primary=false, which is correct — none of them was
created through the new single-primary flow, and the console starts from an
explicit empty state rather than silently promoting an arbitrary existing token.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'f2a91c6d4b78'
down_revision: str | None = 'c7d2f18b6e40'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'enrollment_token',
        sa.Column(
            'is_primary', sa.Boolean(), server_default=sa.false(), nullable=False
        ),
    )
    op.create_index(
        'uq_enrollment_token_one_live_primary',
        'enrollment_token',
        ['is_primary'],
        unique=True,
        postgresql_where=sa.text('is_primary AND revoked_at IS NULL'),
        sqlite_where=sa.text('is_primary AND revoked_at IS NULL'),
    )


def downgrade() -> None:
    op.drop_index(
        'uq_enrollment_token_one_live_primary', table_name='enrollment_token'
    )
    op.drop_column('enrollment_token', 'is_primary')
