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

"""device: battery, second IMEI, phone number, telephony presence (W108)

Everything here is nullable, and NULL means "the agent has not said" — never
"the device does not have one". Every enrolled device is NULL until it checks in
on an agent new enough to report, which is the same rule `supported_abis` and
`atak_version` already follow (W32, W96).

⚠️ `has_telephony` is the column that makes the others readable. Without it, "this
tablet has no cellular radio" and "the IMEI could not be read" are the same blank
on the page — and an operator would go looking for a permission problem on a
Wi-Fi-only device, which is most of this fleet.

Revision ID: h4j6l8n0p2r4
Revises: f2h4j6l8n0p2
"""

from alembic import op
import sqlalchemy as sa

revision = "h4j6l8n0p2r4"
down_revision = "f2h4j6l8n0p2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("device", sa.Column("imei2", sa.String(length=32), nullable=True))
    op.add_column("device", sa.Column("phone_number", sa.String(length=32), nullable=True))
    op.add_column("device", sa.Column("has_telephony", sa.Boolean(), nullable=True))
    op.add_column("device", sa.Column("battery_level", sa.Integer(), nullable=True))
    op.add_column("device", sa.Column("battery_charging", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("device", "battery_charging")
    op.drop_column("device", "battery_level")
    op.drop_column("device", "has_telephony")
    op.drop_column("device", "phone_number")
    op.drop_column("device", "imei2")
