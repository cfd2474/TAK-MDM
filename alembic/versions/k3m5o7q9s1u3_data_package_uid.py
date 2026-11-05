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

"""data_package_uid

A data package's manifest UID on its library row (W344), so a duplicate upload
is recognised without opening every stored zip. Existing rows stay empty and are
filled the first time a duplicate check reads them.

Revision ID: k3m5o7q9s1u3
Revises: j2l4n6p8r0t2
"""

from alembic import op
import sqlalchemy as sa

revision = "k3m5o7q9s1u3"
down_revision = "j2l4n6p8r0t2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("managed_file", sa.Column("package_uid", sa.String(255), nullable=True))
    op.create_index("ix_managed_file_package_uid", "managed_file", ["package_uid"])


def downgrade() -> None:
    op.drop_index("ix_managed_file_package_uid", table_name="managed_file")
    op.drop_column("managed_file", "package_uid")
