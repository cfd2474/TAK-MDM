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

"""version_downloaded_as

The device Google Play served a library build for (W387). Builds fetched from
Play before this recorded it only inside `source_url`, as
"… (via apkeep, as <device>)", so that text is read back into the column.

Revision ID: u7x9z1b3d5f7
Revises: t5v7x9z1b3d5
"""

import re

from alembic import op
import sqlalchemy as sa

revision = "u7x9z1b3d5f7"
down_revision = "t5v7x9z1b3d5"
branch_labels = None
depends_on = None

_AS = re.compile(r"\(via apkeep, as (.+)\)\s*$")


def downloaded_as(source_url: str | None) -> str | None:
    """The device named in an apkeep source URL, or None."""
    found = _AS.search(source_url or "")
    return found.group(1).strip()[:128] or None if found else None


def upgrade() -> None:
    op.add_column("app_package_version", sa.Column("downloaded_as", sa.String(128), nullable=True))
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT id, source_url FROM app_package_version WHERE source_url LIKE '%(via apkeep, as %'"
    )).fetchall()
    for row_id, url in rows:
        device = downloaded_as(url)
        if device:
            bind.execute(
                sa.text("UPDATE app_package_version SET downloaded_as = :d WHERE id = :i"),
                {"d": device, "i": row_id},
            )


def downgrade() -> None:
    op.drop_column("app_package_version", "downloaded_as")
