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

"""device OEM licence columns

What a device reports about its OEM licence — Knox today (W227). One set of
columns for both agent flavours: the AOSP build reports `NOT_APPLICABLE` rather
than nothing, so the console renders one status column and never has to guess
which build it is talking to.

⚠️ **All nullable, and NULL throughout means "the agent has not said".** That is
a third state and it is the one that matters here. `NOT_LICENSED` means the
device has no licence; `NOT_APPLICABLE` means it cannot have one; NULL means an
agent too old to report. Reading NULL as either of the others would send an
operator to buy a key for a tablet that already has one.

⚠️ `oem_license_status` is a plain string, not an enum column. An agent newer
than this server reporting a status it has not heard of must not fail its whole
check-in over one word — it would stop reporting convergence, battery and
location as well.

⚠️ **No column here holds the licence key.** `oem_license_masked_key` is the
vendor's own masking, which is what lets the console say *which* licence is
active without the secret making a return trip. The key itself is sealed in
`app_setting` and is never written to any other table — see
`app/services/knox_license.py`.

Revision ID: y2a4c6e8g0i2
Revises: w0y2a4c6e8g0
"""

from alembic import op
import sqlalchemy as sa

from app.db.base import UtcDateTime

revision = "y2a4c6e8g0i2"
down_revision = "w0y2a4c6e8g0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "device", sa.Column("oem_license_status", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "device",
        sa.Column("oem_license_masked_key", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "device", sa.Column("oem_license_activated_at", UtcDateTime(), nullable=True)
    )
    op.add_column(
        "device", sa.Column("oem_license_error_code", sa.Integer(), nullable=True)
    )
    op.add_column("device", sa.Column("oem_license_detail", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("device", "oem_license_detail")
    op.drop_column("device", "oem_license_error_code")
    op.drop_column("device", "oem_license_activated_at")
    op.drop_column("device", "oem_license_masked_key")
    op.drop_column("device", "oem_license_status")
