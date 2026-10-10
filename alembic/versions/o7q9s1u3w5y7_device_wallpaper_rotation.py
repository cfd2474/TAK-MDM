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

"""device_wallpaper_rotation

Whether a device's wallpaper turns with the screen (W361). On a One UI phone it
does only after a person has set a wallpaper once through Samsung's own app.
`not_applicable`, `ready`, `pending`, or NULL for an agent too old to say.

Revision ID: o7q9s1u3w5y7
Revises: n6p8r0t2v4x6
"""

from alembic import op
import sqlalchemy as sa

revision = "o7q9s1u3w5y7"
down_revision = "n6p8r0t2v4x6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("device", sa.Column("wallpaper_rotation", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("device", "wallpaper_rotation")
