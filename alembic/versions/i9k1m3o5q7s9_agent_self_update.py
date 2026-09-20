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

"""agent self-update: the agent's reported versionCode (W27)

Which agent build a device is entitled to is decided server-side at check-in, so
the server needs a fact it did not have: the agent's numeric versionCode. The
display versionName is free text and cannot be compared, and versionCode is also
the only thing Android's own upgrade rule looks at.

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


def downgrade() -> None:
    op.drop_column("device", "agent_version_code")
