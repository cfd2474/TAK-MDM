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

"""device_compliance_rules

The device's reported security posture and its COMPLIANCE rules verdict (W323).
All nullable: NULL until an agent new enough reports, or a rule applies.

Revision ID: e7g9i1k3m5o7
Revises: d6f8h0j2l4n6
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.db.base import UtcDateTime

revision = "e7g9i1k3m5o7"
down_revision = "d6f8h0j2l4n6"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column("device", sa.Column("posture", _JSON, nullable=True))
    op.add_column("device", sa.Column("rules_status", sa.String(length=16), nullable=True))
    op.add_column("device", sa.Column("rules_results", _JSON, nullable=True))
    op.add_column("device", sa.Column("rules_checked_at", UtcDateTime(), nullable=True))
    op.add_column("device", sa.Column("rules_failing_since", UtcDateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("device", "rules_failing_since")
    op.drop_column("device", "rules_checked_at")
    op.drop_column("device", "rules_results")
    op.drop_column("device", "rules_status")
    op.drop_column("device", "posture")
