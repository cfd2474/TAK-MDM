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

"""enrollment_token.bypass_attempts

Failed guesses at the provisioning bypass PIN, counted per enrollment token
(W117).

⚠️ **Per token rather than global, deliberately.** A single global counter would
let anyone holding one token lock every other operator out of provisioning,
turning a brute-force guard into a denial of service. Tokens are minted by an
admin, so an attacker cannot mint themselves fresh attempts.

Non-nullable with a server-side default of 0: existing tokens start with a full
allowance, and the counter is never "unknown".

Revision ID: a8c0e2g4i6k8
Revises: z6b8d0f2h4j6
Create Date: 2026-09-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a8c0e2g4i6k8"
down_revision = "z6b8d0f2h4j6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "enrollment_token",
        sa.Column(
            "bypass_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("enrollment_token", "bypass_attempts")
