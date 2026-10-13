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

"""Drop tags (W123)

Tags, tag membership, tag-scoped assignments and tag-scoped enrollment tokens
all go. Groups carry every grouping this project actually uses, and the console
surface came out in the previous release.

⚠️ **This destroys data where any exists.** Tag-scoped assignments reach devices
exactly the way group-scoped ones do, so on an install that used tags the
affected devices lose those policies at their next check-in. Run against this
project's only deployment, which was verified to hold zero tags, zero
memberships, zero tag-scoped assignments and zero tag-scoped tokens before the
work began — and nobody else had deployed yet.

⚠️ **The rows are deleted before the enum loses the value, and that order is not
cosmetic.** `Assignment.scope` is mapped through a Python enum; a surviving row
saying `"tag"` would become unloadable the moment `AssignmentScope.TAG` was
removed from the model — a 500 in the resolver rather than a tidy absence. The
surface release and this one are therefore ordered, never the reverse.

⚠️ **`ck_assignment_single_target` is rewritten, not dropped.** It enforces
"exactly one target", and simply removing it would let an assignment be created
pointing at nothing, which the resolver would silently ignore. SQLite cannot
alter a constraint in place, hence batch mode.

`downgrade()` recreates the schema. It cannot recreate the data, and pretending
otherwise would be worse than saying so.

Revision ID: c0e2g4i6k8m0
Revises: b9d1f3h5j7l9
Create Date: 2026-09-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c0e2g4i6k8m0"
down_revision = "b9d1f3h5j7l9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rows first: see the note above on enum ordering.
    op.execute("DELETE FROM assignment WHERE tag_id IS NOT NULL")
    op.execute("DELETE FROM profile_assignment WHERE tag_id IS NOT NULL")

    with op.batch_alter_table("assignment") as batch:
        batch.drop_constraint("ck_assignment_single_target", type_="check")
        batch.drop_column("tag_id")
        batch.create_check_constraint(
            "ck_assignment_single_target",
            "(CASE WHEN device_id IS NOT NULL THEN 1 ELSE 0 END) "
            "+ (CASE WHEN group_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
        )

    with op.batch_alter_table("profile_assignment") as batch:
        batch.drop_constraint("ck_profile_assignment_single_target", type_="check")
        batch.drop_column("tag_id")
        batch.create_check_constraint(
            "ck_profile_assignment_single_target",
            "(CASE WHEN device_id IS NOT NULL THEN 1 ELSE 0 END) "
            "+ (CASE WHEN group_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
        )

    op.drop_table("enrollment_token_tag")
    op.drop_table("device_tag_member")
    op.drop_table("tag")


def downgrade() -> None:
    op.create_table(
        "tag",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "device_tag_member",
        sa.Column(
            "device_id",
            sa.Uuid(),
            sa.ForeignKey("device.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            sa.Uuid(),
            sa.ForeignKey("tag.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "enrollment_token_tag",
        sa.Column(
            "token_id",
            sa.Uuid(),
            sa.ForeignKey("enrollment_token.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            sa.Uuid(),
            sa.ForeignKey("tag.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    for table, constraint in (
        ("assignment", "ck_assignment_single_target"),
        ("profile_assignment", "ck_profile_assignment_single_target"),
    ):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(constraint, type_="check")
            batch.add_column(
                sa.Column(
                    "tag_id",
                    sa.Uuid(),
                    sa.ForeignKey("tag.id", ondelete="CASCADE"),
                    nullable=True,
                )
            )
            batch.create_check_constraint(
                constraint,
                "(CASE WHEN device_id IS NOT NULL THEN 1 ELSE 0 END) "
                "+ (CASE WHEN group_id IS NOT NULL THEN 1 ELSE 0 END) "
                "+ (CASE WHEN tag_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            )
