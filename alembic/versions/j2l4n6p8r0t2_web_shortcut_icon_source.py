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

"""web_shortcut_icon_source

Where a web shortcut's icon came from (W337). Existing shortcuts were all made
with an uploaded picture, so they are "custom".

Revision ID: j2l4n6p8r0t2
Revises: i1k3m5o7q9s1
"""

from alembic import op
import sqlalchemy as sa

revision = "j2l4n6p8r0t2"
down_revision = "i1k3m5o7q9s1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("web_shortcut", sa.Column("icon_source", sa.String(8), nullable=False,
                                            server_default="custom"))


def downgrade() -> None:
    op.drop_column("web_shortcut", "icon_source")
