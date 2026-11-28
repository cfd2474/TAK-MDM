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

"""Applying the permission model to each admin request (W495).

`app.security.permissions` says what each route needs and who may have it;
this module asks that question for the request in hand, with the categories
stored for the caller, and refuses with 403 when the answer is no.

Mounted on every admin router in `main.py`, after the CSRF check, so a refused
request is audited and CSRF-checked like any other.
"""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.base import get_session
from app.security.admin_auth import AdminIdentity, admin_required
from app.security.permissions import (
    GrantSource,
    Permission,
    allows,
    endpoint_key,
    permission_for,
)
from app.security import scope_guard
from app.services.admin_scopes import DeviceScope, StoredGrants

logger = logging.getLogger(__name__)


def get_grant_source(session: Session = Depends(get_session)) -> GrantSource:
    """FastAPI dependency: the categories super admins stored."""
    return StoredGrants(session)


def get_device_scope(
    identity: AdminIdentity = Depends(admin_required),
    session: Session = Depends(get_session),
) -> DeviceScope:
    """FastAPI dependency: the devices this request may see and act on.

    Everything for a super admin, read once per request for a standard one.
    """
    if not identity.is_standard:
        return DeviceScope.everything()
    return DeviceScope.for_username(session, identity.username)


class Gate:
    """A check a route makes itself, when the permission depends on the body.

    `authorize` decides from the route alone. A route that does two kinds of
    thing — the API command queue sends a ping or a wipe through one path —
    asks the gate for the stronger one once it knows which it is doing.
    """

    def __init__(self, identity: AdminIdentity, granted: frozenset[Permission]):
        self._identity = identity
        self._granted = granted

    def may(self, permission: Permission) -> bool:
        return allows(self._identity, permission, self._granted)

    def require(self, permission: Permission) -> None:
        if self.may(permission):
            return
        logger.warning(
            "standard admin %s refused: needs %s", self._identity.username,
            permission.value,
        )
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "your administrator role does not include this action",
        )


def get_gate(
    identity: AdminIdentity = Depends(admin_required),
    grants: GrantSource = Depends(get_grant_source),
) -> Gate:
    """FastAPI dependency: a `Gate` for this request's administrator."""
    if not identity.is_standard:
        return Gate(identity, frozenset())
    return Gate(identity, grants.categories_for(identity))


def authorize(
    request: Request,
    identity: AdminIdentity = Depends(admin_required),
    grants: GrantSource = Depends(get_grant_source),
    scope: DeviceScope = Depends(get_device_scope),
    session: Session = Depends(get_session),
) -> AdminIdentity:
    """Router dependency: refuse a standard admin what they were not given.

    Two questions, in order: may they do this kind of thing at all
    (`permissions`), and is the device, group or command in the URL theirs
    (`scope_guard`)? A super admin returns at once, before any lookup, so their
    requests behave exactly as before W495.
    """
    if not identity.is_standard:
        return identity
    endpoint = request.scope.get("endpoint")
    permission = permission_for(endpoint)
    granted = grants.categories_for(identity)
    if allows(identity, permission, granted):
        scope_guard.check(request, scope, session, identity.username)
        return identity
    if permission is None:
        # A route nobody classified. Logged at ERROR: it is a missing decision
        # in the code, not a person trying something.
        logger.error(
            "standard admin %s refused %s %s: endpoint %s has no permission in "
            "ROUTE_PERMISSIONS",
            identity.username, request.method, request.url.path,
            endpoint_key(endpoint) if endpoint else "unknown",
        )
    else:
        logger.warning(
            "standard admin %s refused %s %s: needs %s",
            identity.username, request.method, request.url.path, permission.value,
        )
    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        "your administrator role does not include this action",
    )
