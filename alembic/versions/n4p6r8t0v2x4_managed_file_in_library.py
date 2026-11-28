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

"""managed files can live outside the Content library (W46)

A wallpaper uploaded from inside the policy editor is an ordinary managed file to
the device — same artifact, same download — but it is not something the operator
published to the fleet's catalogue, so it should not appear there.

``server_default`` is set by hand and deliberately: autogenerate never infers one,
and a NOT NULL column added to a table that already has rows fails on Postgres
without it. Every file that exists today was uploaded through Content, so they all
default to being in the library.

Revision ID: n4p6r8t0v2x4
Revises: m3o5q7s9u1w3
Create Date: 2026-09-05 17:40:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "n4p6r8t0v2x4"
down_revision: str | None = "m3o5q7s9u1w3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "managed_file",
        sa.Column(
            "in_library",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("managed_file", "in_library")
