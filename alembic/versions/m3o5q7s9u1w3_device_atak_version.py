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

"""record the ATAK a device actually has (W32)

An ATAK plugin only loads in the ATAK build it was compiled against. The device
cannot say so — the plugin installs and simply never appears — so the mismatch is
only visible where both facts meet, which is here.

Revision ID: m3o5q7s9u1w3
Revises: l2n4p6r8t0v2
Create Date: 2026-09-03 13:05:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "m3o5q7s9u1w3"
down_revision: str | None = "l2n4p6r8t0v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("device", sa.Column("atak_package", sa.String(length=128), nullable=True))
    op.add_column("device", sa.Column("atak_version", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("device", "atak_version")
    op.drop_column("device", "atak_package")
