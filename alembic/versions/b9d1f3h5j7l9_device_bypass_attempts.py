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

"""device.bypass_attempts

The bypass PIN's rate limit needs a second home (W117).

⚠️ **The credential changes halfway through provisioning**, which the first
version missed. `enrollment_token.bypass_attempts` covers a device that has not
enrolled yet; but the enrollment token is destroyed the moment enrolment
succeeds — deliberately, so a usable enrollment credential is not left lying on
the tablet — and the permission screen is normally reached *after* that. An
enrolled device authenticates the check with its client certificate instead, and
the attempt counter has to follow whichever identity was used.

Non-nullable, server-side default 0: existing devices start with a full
allowance and the counter is never "unknown".

⚠️ Chosen with `alembic heads`, not by reading the end of a directory listing.
The previous migration in this feature branched the history because
`ls alembic/versions | tail -3` sorts alphabetically rather than chronologically,
and the API container refused to start until it was corrected.

Revision ID: b9d1f3h5j7l9
Revises: a8c0e2g4i6k8
Create Date: 2026-09-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b9d1f3h5j7l9"
down_revision = "a8c0e2g4i6k8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "device",
        sa.Column("bypass_attempts", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("device", "bypass_attempts")
