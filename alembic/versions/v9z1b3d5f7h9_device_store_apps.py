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

"""device_store_apps

Apps the user installed from the ATLAS store, as the device reports them
(W398). NULL when the agent is too old to say.

Revision ID: v9z1b3d5f7h9
Revises: u7x9z1b3d5f7
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "v9z1b3d5f7h9"
down_revision = "u7x9z1b3d5f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("device", sa.Column("store_apps", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True))


def downgrade() -> None:
    op.drop_column("device", "store_apps")
