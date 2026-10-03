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

"""device friendly name

Revision ID: a1c3e5f7b9d2
Revises: f2a91c6d4b78
Create Date: 2026-09-02 09:00:00.000000

Nullable, no server default: an unnamed device is the normal state right after
enrolment, and the console falls back to the serial for display.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a1c3e5f7b9d2"
down_revision: str | None = "f2a91c6d4b78"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("device", sa.Column("name", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("device", "name")
