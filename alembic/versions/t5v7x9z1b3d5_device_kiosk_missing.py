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

"""device_kiosk_missing

Built-in kiosk tiles (the device's own apps) this device reported not having
(W374). NULL when the agent is too old to say.

Revision ID: t5v7x9z1b3d5
Revises: s3u5w7y9a1c3
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "t5v7x9z1b3d5"
down_revision = "s3u5w7y9a1c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("device", sa.Column("kiosk_missing", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True))


def downgrade() -> None:
    op.drop_column("device", "kiosk_missing")
