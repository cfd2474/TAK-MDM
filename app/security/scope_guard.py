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

"""Keeping a standard admin to their own devices on routes that name one (W495).

`permissions` decides *which kind of action* a route is. This decides whether
the device, device group or command named in the URL is one the caller may
reach. It reads only the path, so a route cannot forget to call it.

⚠️ **Every path parameter a standard admin can reach is classified**, and
`tests/test_admin_scope_guard.py` fails on one that is not. A new parameter is
a new way to name an object, and it must be decided before it ships.

⚠️ **Out of scope answers 404, not 403.** A standard admin must not learn
which device ids exist outside their scope by watching the status change.
"""

from __future__ import annotations

import enum
import logging
import uuid

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Assignment,
    DeviceCommand,
    EnrollmentQrRecipe,
    EnrollmentToken,
)
from app.services import enrollment_scope, policy_scope
from app.services.admin_scopes import DeviceScope

logger = logging.getLogger(__name__)


class ParamKind(str, enum.Enum):
    DEVICE = "device"
    DEVICE_GROUP = "device group"
    COMMAND = "command"
    #: Every target in scope (operator decision 2, `policy_scope`).
    POLICY = "policy"
    PROFILE = "profile"
    #: The source of a copy: theirs, or a template shared with them (B8).
    POLICY_COPY_SOURCE = "policy to copy"
    PROFILE_COPY_SOURCE = "profile to copy"
    #: `/api/v1/assignments/{id}`: its target in scope and its policy too.
    ASSIGNMENT = "assignment"
    #: Places devices only in groups in scope (`enrollment_scope`).
    ENROLLMENT_TOKEN = "enrollment token"
    ENROLLMENT_QR = "enrollment QR"
    #: Names something under `/devices/{device_id}/`, and the handler refuses
    #: one that does not belong to that device (checked for W495 B3).
    CHECKED_AGAINST_DEVICE = "checked against the device"
    #: An assignment under `/groups/{group_id}/`; the handler refuses one of
    #: another group (`_remove_group_assignment`, `rerank_for_group`).
    CHECKED_AGAINST_GROUP = "checked against the group"
    #: A section key under `/profiles/{profile_id}/`; the profile is checked.
    CHECKED_AGAINST_PROFILE = "checked against the profile"
    #: Library items, guides, reports, schemas: not device data.
    NOT_DEVICE = "not device data"


_DEVICE_CHILDREN = frozenset({
    "bundle_id", "extract_id", "log_id", "assignment_id", "assignment_ref",
    "action", "section_key", "table_key", "field_name", "policy_type",
})
_BY_NAME = {
    "device_id": ParamKind.DEVICE,
    "command_id": ParamKind.COMMAND,
    "policy_id": ParamKind.POLICY,
    "profile_id": ParamKind.PROFILE,
    "token_id": ParamKind.ENROLLMENT_TOKEN,
    "recipe_id": ParamKind.ENROLLMENT_QR,
}
_NOT_DEVICE = frozenset({
    "file_id", "package_id", "shortcut_id", "storefront_id", "version_id",
    "job_id", "name", "key", "category", "slug",
})
_DEVICE_GROUP_PATHS = ("/groups/", "/api/v1/groups/")
_APP_GROUP_PATHS = ("/app-groups/", "/api/v1/app-groups/")


#: Routes that copy the object they name, and change nothing about it (B8).
_COPY_ROUTES = {
    ("/profiles/{profile_id}/clone", "profile_id"): ParamKind.PROFILE_COPY_SOURCE,
    ("/api/v1/policies/{policy_id}/clone", "policy_id"): ParamKind.POLICY_COPY_SOURCE,
}


def classify(path: str, param: str) -> ParamKind | None:
    """What a path parameter names on the route `path`, or None if undecided."""
    if (path, param) in _COPY_ROUTES:
        return _COPY_ROUTES[(path, param)]
    if param in _BY_NAME:
        return _BY_NAME[param]
    if param == "group_id":
        if path.startswith(_DEVICE_GROUP_PATHS):
            return ParamKind.DEVICE_GROUP
        if path.startswith(_APP_GROUP_PATHS):
            return ParamKind.NOT_DEVICE
        return None
    if param in _DEVICE_CHILDREN and "{device_id}" in path:
        return ParamKind.CHECKED_AGAINST_DEVICE
    if param in ("assignment_id", "assignment_ref"):
        if path.startswith("/groups/{group_id}/assignments/"):
            return ParamKind.CHECKED_AGAINST_GROUP
        if path.startswith("/api/v1/assignments/"):
            return ParamKind.ASSIGNMENT
        return None
    if param == "category_key" and "{profile_id}" in path:
        return ParamKind.CHECKED_AGAINST_PROFILE
    if param in _NOT_DEVICE:
        return ParamKind.NOT_DEVICE
    return None


def _as_uuid(value) -> uuid.UUID | None:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except ValueError:
        return None


def _not_found(request: Request, username: str, kind: ParamKind) -> HTTPException:
    logger.warning(
        "standard admin %s refused %s %s: %s outside their scope",
        username, request.method, request.url.path, kind.value,
    )
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{kind.value} not found")


def check(request: Request, scope: DeviceScope, session: Session, username: str) -> None:
    """Raise 404 when the URL names an object outside `scope`.

    A value that is not a UUID is left to the route, which refuses it.
    """
    if scope.unrestricted:
        return
    route = request.scope.get("route")
    path = getattr(route, "path", "")
    for param, raw in request.path_params.items():
        kind = classify(path, param)
        if kind is None:
            # Unclassified: refuse rather than guess. The test names it.
            logger.error(
                "standard admin %s refused %s %s: path parameter %r on %s is "
                "not classified in scope_guard", username, request.method,
                request.url.path, param, path,
            )
            raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
        value = _as_uuid(raw)
        if value is None or kind not in _CHECKS:
            continue
        if not _CHECKS[kind](session, scope, value):
            raise _not_found(request, username, kind)


def _command(session: Session, scope: DeviceScope, value: uuid.UUID) -> bool:
    device_id = session.scalar(
        select(DeviceCommand.device_id).where(DeviceCommand.id == value)
    )
    return device_id is not None and scope.has_device(device_id)


def _assignment(session: Session, scope: DeviceScope, value: uuid.UUID) -> bool:
    row = session.get(Assignment, value)
    if row is None:
        return False
    return (
        policy_scope.of_assignment(row).within(scope)
        and policy_scope.policy_within(session, scope, row.policy_id)
    )


#: How each guarded kind is checked. ⚠️ A missing object answers 404 either
#: here or in the route, the same as one outside scope, so the two cannot be
#: told apart.
_CHECKS = {
    ParamKind.DEVICE: lambda session, scope, v: scope.has_device(v),
    ParamKind.DEVICE_GROUP: lambda session, scope, v: scope.has_group(v),
    ParamKind.COMMAND: _command,
    ParamKind.POLICY: policy_scope.policy_within,
    ParamKind.PROFILE: policy_scope.profile_within,
    ParamKind.POLICY_COPY_SOURCE: policy_scope.policy_copyable,
    ParamKind.PROFILE_COPY_SOURCE: policy_scope.profile_copyable,
    ParamKind.ASSIGNMENT: _assignment,
    ParamKind.ENROLLMENT_TOKEN: lambda session, scope, v: enrollment_scope.token_within(
        scope, session.get(EnrollmentToken, v)),
    ParamKind.ENROLLMENT_QR: lambda session, scope, v: enrollment_scope.recipe_within(
        scope, session.get(EnrollmentQrRecipe, v)),
}
