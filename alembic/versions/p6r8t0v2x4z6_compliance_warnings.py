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

"""things worth saying about a device that has converged (W50)

A policy naming an older build than the device already carries is a mismatch to
report, not a failure to apply — the newer build satisfies the requirement, and
Android would refuse the downgrade regardless. Filed as an apply error it marked
healthy devices DEGRADED, which additionally cut them off from agent updates,
since the update gate refuses a device that is "not applying its policy cleanly".

Nullable with no default: a device that has never reported one has nothing to say,
which is different from having said "no warnings".

Revision ID: p6r8t0v2x4z6
Revises: n4p6r8t0v2x4
Create Date: 2026-09-05 17:20:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "p6r8t0v2x4z6"
down_revision: str | None = "n4p6r8t0v2x4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("device", sa.Column("compliance_warnings", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("device", "compliance_warnings")
