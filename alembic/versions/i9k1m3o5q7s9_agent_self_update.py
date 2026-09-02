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

"""agent self-update: canary flag and reported versionCode (W27)

Which agent build a device is entitled to is decided server-side at check-in, so
the server needs two facts it did not have: the agent's numeric versionCode (the
display versionName cannot be compared) and whether this device takes candidate
builds ahead of the fleet.

Revision ID: i9k1m3o5q7s9
Revises: h8j0l2n4p6r8
Create Date: 2026-09-02 22:15:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "i9k1m3o5q7s9"
down_revision: str | None = "h8j0l2n4p6r8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("device", sa.Column("agent_version_code", sa.Integer(), nullable=True))
    op.add_column(
        "device",
        sa.Column(
            "is_agent_canary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("device", "is_agent_canary")
    op.drop_column("device", "agent_version_code")
