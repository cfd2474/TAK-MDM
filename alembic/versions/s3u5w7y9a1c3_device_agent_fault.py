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

"""device_agent_fault

The agent's last sync crashed applying the policy (an agent bug, not a policy
the device could not apply), as the agent reported it. NULL when its last sync
did not crash, or when the agent is too old to say.

Revision ID: s3u5w7y9a1c3
Revises: r1t3v5x7z9b1
"""

from alembic import op
import sqlalchemy as sa

revision = "s3u5w7y9a1c3"
down_revision = "r1t3v5x7z9b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("device", sa.Column("agent_fault", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("device", "agent_fault")
