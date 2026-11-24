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

"""Pending deployment, and a date it goes live on (W191)

A policy can now be built with its targets in place and held back, either
indefinitely or until a stated moment.

Three columns rather than one nullable date, because there are three states:
live (`pending_deployment` false), held (true, `effective_at` NULL) and
scheduled (true, `effective_at` set). `activated_at` records when it actually
went live, which is not the same instant as when it was due to.

⚠️ **`server_default` on the boolean is load-bearing** (D35). A NOT NULL column
added without one fails on Postgres against a table that already has rows, and
the SQLite suite will not tell you — it is the defect this project has now
shipped into a migration twice.

⚠️ **Every existing row must come out live**, which `false` gives. A default of
true would hold every policy in every deployment the moment this migration ran,
and the symptom is an entire fleet quietly reverting to no policy at all.

Revision ID: i6k8m0o2q4s6
Revises: g4i6k8m0o2q4
"""

from alembic import op
import sqlalchemy as sa

from app.db.base import UtcDateTime

revision = "i6k8m0o2q4s6"
down_revision = "g4i6k8m0o2q4"
branch_labels = None
depends_on = None

TABLES = ("policy", "policy_profile")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column(
                "pending_deployment",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
        op.add_column(table, sa.Column("effective_at", UtcDateTime(), nullable=True))
        op.add_column(table, sa.Column("activated_at", UtcDateTime(), nullable=True))


def downgrade() -> None:
    for table in TABLES:
        op.drop_column(table, "activated_at")
        op.drop_column(table, "effective_at")
        op.drop_column(table, "pending_deployment")
