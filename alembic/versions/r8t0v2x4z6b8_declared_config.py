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

"""record the managed configuration a build declares (W49)

The device needs each key's declared type, not just its value: a Bundle holding
the string "300" returns 0 from getInt, and "true" returns false from getBoolean —
silently, with the app falling back to its own default and nothing reporting a
fault. The type has to travel with the value.

Stored on the version rather than re-read from the APK because the desired state
is rebuilt on every check-in for every device. Safe to store because a version row
is immutable: its bytes never change, so this cannot drift from the build it
describes.

NULL means "not scanned yet" and is backfilled lazily; an empty object means
"scanned, declares nothing". The two are different and the code relies on it.

Revision ID: r8t0v2x4z6b8
Revises: p6r8t0v2x4z6
Create Date: 2026-09-05 17:40:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "r8t0v2x4z6b8"
down_revision: str | None = "p6r8t0v2x4z6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "app_package_version", sa.Column("declared_config", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("app_package_version", "declared_config")
