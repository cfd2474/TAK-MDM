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

"""managed file deployment defaults

Revision ID: f6h8j0l2n4p6
Revises: e5g7i9k1m3o5
Create Date: 2026-09-02 18:00:00.000000

All nullable — a file with no suggested deployment is the normal starting state.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f6h8j0l2n4p6"
down_revision: str | None = "e5g7i9k1m3o5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("managed_file", sa.Column("default_dest_path", sa.String(length=512), nullable=True))
    op.add_column("managed_file", sa.Column("default_persist", sa.Boolean(), nullable=True))
    op.add_column("managed_file", sa.Column("default_extract", sa.Boolean(), nullable=True))
    op.add_column("managed_file", sa.Column("default_extract_to", sa.String(length=512), nullable=True))
    op.add_column("managed_file", sa.Column("default_overwrite", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("managed_file", "default_overwrite")
    op.drop_column("managed_file", "default_extract_to")
    op.drop_column("managed_file", "default_extract")
    op.drop_column("managed_file", "default_persist")
    op.drop_column("managed_file", "default_dest_path")
