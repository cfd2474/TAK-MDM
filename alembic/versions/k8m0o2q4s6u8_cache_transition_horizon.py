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

"""effective_policy_cache.next_transition_at (W191)

When the soonest scheduled deployment is due, so that a cached payload expires
at that moment instead of outliving it.

⚠️ **This is an expiry, not an optimisation.** Invalidation in this system is a
write marking rows stale; a clock passing a date is not a write, so nothing
would mark anything. The resolver reads the date and would get it right — it
would simply never be asked, because a payload computed at 07:00 is entirely
fresh at 08:00.

NULL on every existing row, which is correct rather than merely convenient:
nothing is scheduled in any deployment that predates the column, so there is no
moment for any cache to expire at. The first refresh of each device fills it in.

Revision ID: k8m0o2q4s6u8
Revises: i6k8m0o2q4s6
"""

from alembic import op
import sqlalchemy as sa

from app.db.base import UtcDateTime

revision = "k8m0o2q4s6u8"
down_revision = "i6k8m0o2q4s6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "effective_policy_cache",
        sa.Column("next_transition_at", UtcDateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("effective_policy_cache", "next_transition_at")
