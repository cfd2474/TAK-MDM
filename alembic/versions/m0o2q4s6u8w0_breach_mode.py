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

"""device breach-mode state (W193)

A device in breach receives the breach profile and nothing else. Three columns
rather than one flag, because three different things are worth knowing and two
of them are timestamps nobody can reconstruct later.

⚠️ **Engaged and confirmed are separate on purpose.** Engaged is what an
operator did; confirmed is what the device did about it. A tablet that was
switched off, or is already out of contact, has the first and never the second —
and during an incident those two must not look the same on the page.

All nullable, so every existing device comes out not-in-breach without a
``server_default`` to argue about.

Revision ID: m0o2q4s6u8w0
Revises: k8m0o2q4s6u8
"""

from alembic import op
import sqlalchemy as sa

from app.db.base import UtcDateTime

revision = "m0o2q4s6u8w0"
down_revision = "k8m0o2q4s6u8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("device", sa.Column("breach_engaged_at", UtcDateTime(), nullable=True))
    op.add_column(
        "device", sa.Column("breach_engaged_by", sa.String(length=128), nullable=True)
    )
    op.add_column(
        "device", sa.Column("breach_confirmed_at", UtcDateTime(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("device", "breach_confirmed_at")
    op.drop_column("device", "breach_engaged_by")
    op.drop_column("device", "breach_engaged_at")
