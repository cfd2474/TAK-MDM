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

"""device_delivery_pending

What a device still has to download (W355): apps and files left over when a
time-boxed sync ran out of budget. NULL = an agent too old to report it.

Revision ID: l4n6p8r0t2v4
Revises: k3m5o7q9s1u3
"""

from alembic import op
import sqlalchemy as sa

revision = "l4n6p8r0t2v4"
down_revision = "k3m5o7q9s1u3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("device", sa.Column("pending_apps", sa.Integer(), nullable=True))
    op.add_column("device", sa.Column("pending_files", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("device", "pending_files")
    op.drop_column("device", "pending_apps")
