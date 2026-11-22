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

"""Which enrollment tokens and QR codes a standard administrator may use (W495 B4).

A device enrolled with a token lands in the token's groups. A QR made for a
group is issued against that group's standing token; one made with no group,
against the primary token. A standard
admin may use a token or QR only when **it places devices, and every group it
places them in is in their scope** — otherwise they would enroll devices they
could not then see.

⚠️ **No group means no.** A token without groups enrolls a device into no
group, which is outside every standard admin's scope. The primary token is
the server's own and never qualifies.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from app.db.models import EnrollmentQrRecipe, EnrollmentToken
from app.services.admin_scopes import DeviceScope


def groups_within(scope: DeviceScope, group_ids: Iterable[uuid.UUID]) -> bool:
    if scope.unrestricted:
        return True
    wanted = set(group_ids)
    return bool(wanted) and wanted <= scope.group_ids


def token_within(scope: DeviceScope, token: EnrollmentToken | None) -> bool:
    if scope.unrestricted:
        return True
    if token is None or token.is_primary:
        return False
    return groups_within(scope, (g.id for g in token.groups))


def recipe_within(scope: DeviceScope, recipe: EnrollmentQrRecipe | None) -> bool:
    """A saved QR: only one made for a group in scope.

    ⚠️ A QR made with no group is issued against the primary token
    (`generate_qr`), so it never qualifies, whatever its token says.
    """
    if scope.unrestricted:
        return True
    if recipe is None or recipe.group_id is None:
        return False
    return groups_within(scope, [recipe.group_id])
