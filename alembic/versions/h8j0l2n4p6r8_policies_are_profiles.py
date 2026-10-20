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

"""every device policy is a composite profile (W21)

The console now has one kind of policy: the composite. Each existing
single-concern policy becomes a one-section profile with the same name, and its
assignments move to the profile. Resolution is unchanged — the resolver already
expands a profile into one input per section, identical to a standalone
assignment. Templates are left alone: they stay single-concern blueprints and
clone into a profile.

Revision ID: h8j0l2n4p6r8
Revises: g7i9k1m3o5q7
Create Date: 2026-09-02 21:30:00.000000
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "h8j0l2n4p6r8"
down_revision: str | None = "g7i9k1m3o5q7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Registry policy type -> creator-catalog category key. Frozen here so a later
# rename in the app cannot change what this migration did.
_SECTION = {
    "PASSWORD": "password",
    "RESTRICTIONS": "restrictions",
    "APP_CATALOG": "app_management",
    "FILES": "file_management",
    "NETWORKS": "networks",
}


def upgrade() -> None:
    conn = op.get_bind()

    policies = conn.execute(
        sa.text(
            "SELECT id, name, description, archived_at, policy_type "
            "FROM policy WHERE profile_id IS NULL AND is_template = false"
        )
    ).fetchall()

    for p in policies:
        profile_id = uuid.uuid4()
        conn.execute(
            sa.text(
                "INSERT INTO policy_profile (id, name, description, created_at, archived_at) "
                "VALUES (:id, :name, :description, now(), :archived_at)"
            ),
            {
                "id": profile_id,
                "name": p.name,
                "description": p.description,
                "archived_at": p.archived_at,
            },
        )
        conn.execute(
            sa.text(
                "UPDATE policy SET profile_id = :pid, profile_section = :section "
                "WHERE id = :id"
            ),
            {
                "pid": profile_id,
                "section": _SECTION.get(p.policy_type, p.policy_type.lower()),
                "id": p.id,
            },
        )

        for a in conn.execute(
            sa.text(
                "SELECT id, scope, device_id, group_id, tag_id, rank, enabled "
                "FROM assignment WHERE policy_id = :id"
            ),
            {"id": p.id},
        ).fetchall():
            conn.execute(
                sa.text(
                    "INSERT INTO profile_assignment "
                    "(id, profile_id, scope, device_id, group_id, tag_id, rank, enabled, created_at) "
                    "VALUES (:id, :pid, :scope, :dev, :grp, :tag, :rank, :enabled, now())"
                ),
                {
                    "id": uuid.uuid4(),
                    "pid": profile_id,
                    "scope": a.scope,
                    "dev": a.device_id,
                    "grp": a.group_id,
                    "tag": a.tag_id,
                    "rank": a.rank,
                    "enabled": a.enabled,
                },
            )
            conn.execute(
                sa.text("DELETE FROM assignment WHERE id = :id"), {"id": a.id}
            )


def downgrade() -> None:
    conn = op.get_bind()

    sections = conn.execute(
        sa.text(
            "SELECT p.id AS policy_id, p.profile_id "
            "FROM policy p JOIN policy_profile pr ON pr.id = p.profile_id "
            "WHERE p.is_template = false"
        )
    ).fetchall()

    for s in sections:
        for a in conn.execute(
            sa.text(
                "SELECT id, scope, device_id, group_id, tag_id, rank, enabled "
                "FROM profile_assignment WHERE profile_id = :pid"
            ),
            {"pid": s.profile_id},
        ).fetchall():
            conn.execute(
                sa.text(
                    "INSERT INTO assignment "
                    "(id, policy_id, scope, device_id, group_id, tag_id, rank, enabled, created_at) "
                    "VALUES (:id, :pol, :scope, :dev, :grp, :tag, :rank, :enabled, now())"
                ),
                {
                    "id": uuid.uuid4(),
                    "pol": s.policy_id,
                    "scope": a.scope,
                    "dev": a.device_id,
                    "grp": a.group_id,
                    "tag": a.tag_id,
                    "rank": a.rank,
                    "enabled": a.enabled,
                },
            )
        conn.execute(
            sa.text("DELETE FROM profile_assignment WHERE profile_id = :pid"),
            {"pid": s.profile_id},
        )
        conn.execute(
            sa.text(
                "UPDATE policy SET profile_id = NULL, profile_section = NULL WHERE id = :id"
            ),
            {"id": s.policy_id},
        )
        conn.execute(
            sa.text("DELETE FROM policy_profile WHERE id = :pid"),
            {"pid": s.profile_id},
        )
