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

"""app_package_version.source and source_url

Where a build came from (W97).

⚠️ **NULL means "uploaded by hand", which is the honest answer for everything
that exists today.** Every row predates third-party import, and an operator asking
"where did this come from" deserves "somebody uploaded it" rather than a guess.

Recorded because provenance stops being obvious the moment a build can arrive
without a person choosing the file: an APK fetched from a remote repository and
one an operator carried in on a laptop are different things to trust, and only the
record can say which is which afterwards.

Revision ID: b8d0f2h4j6l8
Revises: z6b8d0f2h4j6
"""

from alembic import op
import sqlalchemy as sa

revision = "b8d0f2h4j6l8"
down_revision = "z6b8d0f2h4j6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_package_version", sa.Column("source", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "app_package_version", sa.Column("source_url", sa.String(length=1024), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("app_package_version", "source_url")
    op.drop_column("app_package_version", "source")
