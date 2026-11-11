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

"""app package versions can be held rather than deployed (W31)

Until now, uploading a build deployed it: the upload invalidated every device's
cache, the resolver picked the newest build satisfying each policy's floor, and
the fleet upgraded. There was no way to put a build in the library without
shipping it.

⚠️ ``published`` defaults to **true**, and existing rows are backfilled true by
the server default. It cannot default false: every version already uploaded is
one the fleet may currently be running, and holding them all would empty the
resolver at the next recompute.

Revision ID: k1m3o5q7s9u1
Revises: j0l2n4p6r8t0
Create Date: 2026-09-03 09:40:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "k1m3o5q7s9u1"
down_revision: str | None = "j0l2n4p6r8t0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "app_package_version",
        sa.Column(
            "published",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("app_package_version", "published")
