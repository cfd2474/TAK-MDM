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

"""app_group_kind

An app group is either general apps or ATAK plugins (W317), fixed when it is
created.

Existing groups are classified here: a non-empty group whose members are all
plugins becomes `plugins`, every other group `apps`. "Plugin" is the rule in
`atak_compat.plugin_packages`: any build declaring a `plugin-api`, or imported
from TAK.gov or TAKWERX, and never ATAK itself (`com.atakmap.app*`).

⚠️ No member is removed. One that no longer belongs is shown on the group with
a warning and dropped by the operator's next save.

Revision ID: c5e7g9i1k3m5
Revises: b4d6f8h0j2l4
"""

from alembic import op
import sqlalchemy as sa

revision = "c5e7g9i1k3m5"
down_revision = "b4d6f8h0j2l4"
branch_labels = None
depends_on = None

#: Classifies the groups that existed before the split. A module constant so the
#: test runs this exact statement, not a re-implementation of it.
BACKFILL = """
UPDATE app_group SET kind = 'plugins'
WHERE EXISTS (
    SELECT 1 FROM app_group_member m WHERE m.group_id = app_group.id
)
AND NOT EXISTS (
    SELECT 1 FROM app_group_member m
    JOIN app_package p ON p.id = m.package_id
    WHERE m.group_id = app_group.id
    AND (
        p.package_name LIKE 'com.atakmap.app%'
        OR NOT EXISTS (
            SELECT 1 FROM app_package_version v
            WHERE v.package_id = p.id
            AND (v.plugin_api IS NOT NULL OR v.source IN ('tak.gov', 'takwerx'))
        )
    )
)
"""


def upgrade() -> None:
    op.add_column(
        "app_group",
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="apps"),
    )
    op.execute(sa.text(BACKFILL))


def downgrade() -> None:
    op.drop_column("app_group", "kind")
