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

"""device.supported_abis and device.sdk_int

What a device can actually run, so a build that cannot install on it can be
identified before it is sent (W96, R19).

⚠️ **Both nullable, and NULL means "the agent has not said".** Every enrolled
device is NULL until it checks in on an agent new enough to report — which is not
the same as a device that supports nothing, and must never be read that way. The
check-in handler only overwrites what is actually reported, for the same reason
`atak_version` does.

`sdk_int` is separate from the existing `os_version` on purpose: that column holds
`Build.VERSION.RELEASE` ("14"), a marketing name, and comparing a build's
`min_sdk` needs the API level as a number.

Revision ID: z6b8d0f2h4j6
Revises: x4z6b8d0f2h4
"""

from alembic import op
import sqlalchemy as sa

revision = "z6b8d0f2h4j6"
down_revision = "x4z6b8d0f2h4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "device", sa.Column("supported_abis", sa.String(length=128), nullable=True)
    )
    op.add_column("device", sa.Column("sdk_int", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("device", "sdk_int")
    op.drop_column("device", "supported_abis")
