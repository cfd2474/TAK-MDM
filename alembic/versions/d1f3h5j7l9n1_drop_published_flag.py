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

"""Drop the published flag on app builds (W139)

`app_package_version.published` meant "eligible for automatic selection", and it
was read in exactly one decision: the newest published build at or above a
policy's floor. Policies now name the build they install, so nothing is selected
automatically and the flag governs nothing.

⚠️ **This is not reversible in the sense that matters.** The column comes back on
downgrade, but every build comes back marked published — the record of which
builds an operator had held is gone. Restoring the old behaviour after a
downgrade means re-holding them by hand.

⚠️ **What this does NOT do is change what any device installs.** That was the
whole design question, and the answer is in `resolve_for_policy`: an entry with
no `artifact_sha256` resolves to nothing rather than to the newest build. Two
packages on this project's deployment (`com.android.chrome`,
`com.microsoft.office.outlook`) have every build held, and one of them is named
by an unpinned policy entry — under a "newest wins" reading, running this
migration would have installed Chrome across the fleet.

Revision ID: d1f3h5j7l9n1
Revises: c0e2g4i6k8m0
Create Date: 2026-09-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d1f3h5j7l9n1"
down_revision = "c0e2g4i6k8m0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("app_package_version", "published")


def downgrade() -> None:
    # Every build returns as published, which is the old default for an upload
    # with nothing to compare against. The holds themselves are not recoverable.
    op.add_column(
        "app_package_version",
        sa.Column(
            "published",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
