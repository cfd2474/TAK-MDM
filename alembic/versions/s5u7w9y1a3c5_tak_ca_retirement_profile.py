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

"""tak_ca_retirement_profile

The operator's answers for a CA rotation (W459): whether ATAK applies the TAK
Server's config pref and its channels pref (`enable-channels.pref`) during the
re-enrollment. NULL on a retirement started before W459: ATAK behaves as it is
set.

Revision ID: s5u7w9y1a3c5
Revises: r4t6v8x0z2b4
"""

from alembic import op
import sqlalchemy as sa

revision = "s5u7w9y1a3c5"
down_revision = "r4t6v8x0z2b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tak_ca_retirement", sa.Column("accept_config", sa.Boolean(), nullable=True))
    op.add_column("tak_ca_retirement", sa.Column("accept_channels", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("tak_ca_retirement", "accept_channels")
    op.drop_column("tak_ca_retirement", "accept_config")
