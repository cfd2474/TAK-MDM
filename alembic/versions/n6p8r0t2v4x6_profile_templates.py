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

"""profile_templates

A policy built in the creator can be a template (W359). Every existing profile is
a live policy, which the server default records.

Revision ID: n6p8r0t2v4x6
Revises: m5o7q9s1u3w5
"""

from alembic import op
import sqlalchemy as sa

revision = "n6p8r0t2v4x6"
down_revision = "m5o7q9s1u3w5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "policy_profile",
        sa.Column("is_template", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("policy_profile", "is_template")
