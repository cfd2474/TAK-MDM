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

"""device_attestation

Hardware key attestation per device (W323 chunk 3): the outstanding challenge,
when it was issued, the last verdict and when. All nullable.

Revision ID: f8h0j2l4n6p8
Revises: e7g9i1k3m5o7
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.db.base import UtcDateTime

revision = "f8h0j2l4n6p8"
down_revision = "e7g9i1k3m5o7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("device", sa.Column("attestation_challenge", sa.String(length=64), nullable=True))
    op.add_column("device", sa.Column("attestation_challenge_at", UtcDateTime(), nullable=True))
    op.add_column(
        "device",
        sa.Column("attestation", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
    )
    op.add_column("device", sa.Column("attested_at", UtcDateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("device", "attested_at")
    op.drop_column("device", "attestation")
    op.drop_column("device", "attestation_challenge_at")
    op.drop_column("device", "attestation_challenge")
