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

"""Which build Google Play served to which model, for every app (W519)

W517's `gms_model_build` recorded this for Google Play services only. W519 makes
it general: `model_build` adds the parts Play served to the model (`parts`, a JSON list of the
split names; null when not known, so every part is sent, as before), the fleet
download the build came from (`fetch_id`) and when (`fetched_at`).

Existing rows are kept, with `parts` null: their parts were never recorded.

Revision ID: h6n8t0v2x4z6
Revises: g5m7s9u1w3y5
"""

from alembic import op
import sqlalchemy as sa

revision = "h6n8t0v2x4z6"
down_revision = "g5m7s9u1w3y5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("gms_model_build", "model_build")
    op.add_column("model_build", sa.Column("parts", sa.Text(), nullable=True))
    op.add_column("model_build", sa.Column("fetch_id", sa.Uuid(), nullable=True))
    op.add_column("model_build", sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_model_build_fetch_id", "model_build", ["fetch_id"])


def downgrade() -> None:
    op.drop_index("ix_model_build_fetch_id", table_name="model_build")
    op.drop_column("model_build", "fetched_at")
    op.drop_column("model_build", "fetch_id")
    op.drop_column("model_build", "parts")
    op.rename_table("model_build", "gms_model_build")
