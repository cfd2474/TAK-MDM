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

"""device identifiers

Revision ID: c7d2f18b6e40
Revises: b41c7e2d9a03
Create Date: 2026-09-01 18:05:00.000000

Backfills every existing device's ``serial_number`` as a ``legacy`` identifier.
That is what preserves today's behaviour exactly: whatever string a device
currently matches on, it goes on matching on, whether that string is a real
hardware serial or an ANDROID_ID fallback. Without the backfill this migration
would orphan every enrolled device on its next re-enrolment — the precise failure
the change exists to prevent.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text  # autogenerate emits a bare Text() inside JSONB variants

import app.db.base  # autogenerate emits app.db.base.UtcDateTime for timestamps


revision: str = 'c7d2f18b6e40'
down_revision: str | None = 'b41c7e2d9a03'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'device_identifier',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('device_id', sa.Uuid(), nullable=False),
        sa.Column('kind', sa.Enum(
            'SERIAL', 'LEGACY', 'ANDROID_ID',
            name='identifierkind', native_enum=False, length=16,
        ), nullable=False),
        sa.Column('value', sa.String(length=128), nullable=False),
        sa.Column('first_seen_at', app.db.base.UtcDateTime(), nullable=False),
        sa.Column('last_seen_at', app.db.base.UtcDateTime(), nullable=False),
        sa.ForeignKeyConstraint(['device_id'], ['device.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('value', name='uq_device_identifier_value'),
    )
    op.create_index(
        op.f('ix_device_identifier_device_id'), 'device_identifier', ['device_id']
    )
    op.create_index(
        op.f('ix_device_identifier_value'), 'device_identifier', ['value']
    )

    # Backfill. Raw SQL rather than the ORM: a migration must not depend on the
    # models file, which moves on ahead of it.
    #
    # `value` is unique and `device.serial_number` is unique, so this cannot
    # collide. Timestamps come from the device's own created_at, so the record does
    # not claim the identifier was first seen at migration time.
    op.execute(
        """
        INSERT INTO device_identifier
            (id, device_id, kind, value, first_seen_at, last_seen_at)
        SELECT
            {uuid_expr}, d.id, 'LEGACY', d.serial_number, d.created_at, d.created_at
        FROM device d
        """.format(
            uuid_expr=(
                "gen_random_uuid()"
                if op.get_bind().dialect.name == "postgresql"
                else "lower(hex(randomblob(16)))"
            )
        )
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_device_identifier_value'), table_name='device_identifier')
    op.drop_index(
        op.f('ix_device_identifier_device_id'), table_name='device_identifier'
    )
    op.drop_table('device_identifier')
