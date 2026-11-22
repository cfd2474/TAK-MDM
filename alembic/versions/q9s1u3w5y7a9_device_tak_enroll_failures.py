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

"""device_tak_enroll_failures

TAK Server enrollments that failed on a device, by connection, with the
fingerprint of the login that failed (W365). While the login is unchanged its
password is not sent to that device again. NULL means none have failed.

Revision ID: q9s1u3w5y7a9
Revises: p8r0t2v4x6z8
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "q9s1u3w5y7a9"
down_revision = "p8r0t2v4x6z8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "device",
        sa.Column(
            "tak_enroll_failures",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("device", "tak_enroll_failures")
