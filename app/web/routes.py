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

"""Server-rendered admin portal.

Deliberately plain: Jinja templates and a little vanilla JavaScript inside the
existing application, so there is no Node toolchain, no build step, and no second
container to keep running. The whole console ships with `docker compose up`.

Every route here is guarded by `admin_required`, applied at router registration in
`app.main` so a new page is protected by default. In deployment that means an
Authentik proxy provider in front; `admin_auth_mode=disabled` leaves it open and is
for local development only.

The console is also blocked at the device-facing port: it lives at `/` on the same
application devices reach at :8443, so nginx default-denies there and opts back in
only the device endpoints.
"""

from __future__ import annotations

import io
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import qrcode
import qrcode.image.svg
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_storage, get_token_vault
from app.security.admin_auth import AdminIdentity, admin_required
from app.security.token_vault import TokenVault
from app.artifacts.storage import ArtifactStorage
from app.config import Settings, get_settings
from app.db.models import (
    AppPackage,
    Assignment,
    AssignmentScope,
    CommandStatus,
    CommandType,
    Device,
    DeviceGroup,
    EnrollmentState,
    EnrollmentToken,
    ManagedFile,
    Policy,
    PolicyVersion,
    Tag,
)
from app.policies.registry import PolicyTypeError, registry
from app.services import commands as command_service
from app.services import device_identity
from app.services import device_logs as log_service
from app.services import effective_policy as eff
from app.services import packages as package_service
from app.services import provisioning
from app.services.enrollment import (
    create_token,
    revoke_device_certificates,
    reveal_secret,
)

router = APIRouter(tags=["admin-ui"], include_in_schema=False)

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
_TEMPLATES.env.filters["pretty_json"] = lambda value: json.dumps(value, indent=2, sort_keys=True)


def _render(
    request: Request, template: str, identity: AdminIdentity | None = None, **context: Any
) -> HTMLResponse:
    context["identity"] = identity
    return _TEMPLATES.TemplateResponse(request, template, context)


# --------------------------------------------------------------------------- #
# Fleet
# --------------------------------------------------------------------------- #


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> HTMLResponse:
    devices = list(session.scalars(select(Device).order_by(Device.serial_number)))
    return _render(
        request,
        "devices.html",
        identity=identity,
        devices=devices,
        policy_count=session.scalar(
            select(Policy).where(Policy.archived_at.is_(None)).limit(1)
        )
        is not None,
        counts={
            "devices": len(devices),
            "policies": len(list(session.scalars(select(Policy).where(Policy.archived_at.is_(None))))),
            "packages": len(list(session.scalars(select(AppPackage)))),
            "files": len(list(session.scalars(select(ManagedFile)))),
        },
    )


@router.get("/devices/{device_id}", response_class=HTMLResponse)
def device_detail(
    device_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> HTMLResponse:
    """The stacking view: what reaches this device, and why each value won."""
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")

    payload = eff.get_effective(session, device)
    session.commit()

    # Ordered exactly as the resolver ordered them, so the page shows real
    # precedence rather than a plausible-looking guess at it.
    considered = payload.get("considered", [])

    return _render(
        request,
        "device_detail.html",
        identity=identity,
        device=device,
        considered=considered,
        values=payload.get("values", {}),
        provenance=payload.get("provenance", {}),
        conflicts=payload.get("conflicts", []),
        apps=payload.get("apps", []),
        files=payload.get("files", {"required": [], "available": []}),
        log_bundles=log_service.list_for_device(session, device_id),
        pending_log_request=_has_open_log_request(session, device_id),
        identifiers=device_identity.for_device(session, device_id),
    )


def _has_open_log_request(session: Session, device_id: uuid.UUID) -> bool:
    """True while a COLLECT_LOGS command is still awaiting an answer.

    Shown so an operator who clicks twice understands the first request is still
    in flight, rather than assuming nothing happened and queueing another.
    """
    return any(
        command.command_type is CommandType.COLLECT_LOGS
        and command.status in (CommandStatus.PENDING, CommandStatus.DISPATCHED)
        for command in command_service.list_for_device(session, device_id)
    )


@router.post("/devices/{device_id}/collect-logs")
def request_logs(
    device_id: uuid.UUID,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    """Ask a device to upload its diagnostic log.

    The doorbell (F3) wakes a parked device in the same second, so this is
    normally answered within a check-in rather than at the next poll.
    """
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")

    command_service.enqueue(session, device, command_type=CommandType.COLLECT_LOGS)
    session.commit()
    return _redirect(f"/devices/{device_id}#logs")


@router.post("/devices/{device_id}/retire")
def retire_device_form(
    device_id: uuid.UUID,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    """Take a device out of service and revoke its certificates."""
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")

    device.enrollment_state = EnrollmentState.RETIRED
    revoke_device_certificates(session, device, reason="device retired")
    session.commit()
    return _redirect(f"/devices/{device_id}")


@router.post("/devices/{device_id}/delete")
def delete_device_form(
    device_id: uuid.UUID,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    """Remove a device record permanently.

    Retirement is the normal answer; this exists for records that should never have
    existed — a failed enrolment that registered before erroring, or a test device.
    Refused unless the device is already retired, so removing a working tablet takes
    two deliberate acts rather than one misplaced click.
    """
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")

    if device.enrollment_state is not EnrollmentState.RETIRED:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "retire the device before deleting it"
        )

    revoke_device_certificates(session, device, reason="device deleted")
    session.delete(device)
    session.commit()
    return _redirect("/")


@router.get("/devices/{device_id}/logs/{bundle_id}", response_class=HTMLResponse)
def view_log(
    device_id: uuid.UUID,
    bundle_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> HTMLResponse:
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")

    bundle = log_service.get(session, bundle_id)
    # Checked against the device too, so a guessed id cannot read another
    # device's logs (the same rule as D34).
    if bundle is None or bundle.device_id != device_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "log bundle not found")

    return _render(
        request, "device_log.html", identity=identity, device=device, bundle=bundle
    )


# --------------------------------------------------------------------------- #
# Policies
# --------------------------------------------------------------------------- #


@router.get("/policies", response_class=HTMLResponse)
def list_policies(
    request: Request,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> HTMLResponse:
    policies = list(
        session.scalars(select(Policy).where(Policy.archived_at.is_(None)).order_by(Policy.name))
    )
    return _render(
        request,
        "policies.html",
        identity=identity,
        policies=policies,
        policy_types=[registry.get(name).describe() for name in registry.names()],
    )


@router.post("/policies")
def create_policy(
    name: str = Form(...),
    policy_type: str = Form(...),
    description: str = Form(default=""),
    spec: str = Form(default="{}"),
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    try:
        parsed = json.loads(spec or "{}")
        validated = registry.validate_spec(policy_type, parsed)
    except (json.JSONDecodeError, PolicyTypeError) as exc:
        return _redirect(f"/policies?error={_quote(str(exc))}")

    policy = Policy(name=name, policy_type=policy_type, description=description or None)
    policy.versions.append(
        PolicyVersion(
            version=1,
            spec=validated,
            published_by=None if identity.is_anonymous else identity.username,
        )
    )
    session.add(policy)
    try:
        session.commit()
    except Exception:
        session.rollback()
        return _redirect(f"/policies?error={_quote(f'a policy named {name!r} already exists')}")

    return _redirect(f"/policies/{policy.id}")


@router.get("/policies/{policy_id}", response_class=HTMLResponse)
def policy_detail(
    policy_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> HTMLResponse:
    policy = session.get(Policy, policy_id)
    if policy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "policy not found")

    assignments = list(
        session.scalars(select(Assignment).where(Assignment.policy_id == policy.id))
    )
    assigned = {
        "device": {a.device_id for a in assignments if a.scope is AssignmentScope.DEVICE},
        "group": {a.group_id for a in assignments if a.scope is AssignmentScope.GROUP},
        "tag": {a.tag_id for a in assignments if a.scope is AssignmentScope.TAG},
    }

    return _render(
        request,
        "policy_detail.html",
        identity=identity,
        policy=policy,
        definition=registry.get(policy.policy_type).describe(),
        devices=list(session.scalars(select(Device).order_by(Device.serial_number))),
        groups=list(session.scalars(select(DeviceGroup).order_by(DeviceGroup.name))),
        tags=list(session.scalars(select(Tag).order_by(Tag.name))),
        assigned=assigned,
        current_rank=assignments[0].rank if assignments else 0,
    )


@router.post("/policies/{policy_id}/versions")
def publish_version(
    policy_id: uuid.UUID,
    spec: str = Form(...),
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    policy = session.get(Policy, policy_id)
    if policy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "policy not found")

    try:
        validated = registry.validate_spec(policy.policy_type, json.loads(spec or "{}"))
    except (json.JSONDecodeError, PolicyTypeError) as exc:
        return _redirect(f"/policies/{policy_id}?error={_quote(str(exc))}")

    latest = policy.latest_version
    session.add(
        PolicyVersion(
            policy_id=policy.id,
            version=(latest.version + 1) if latest else 1,
            spec=validated,
            published_by=None if identity.is_anonymous else identity.username,
        )
    )
    session.flush()
    eff.invalidate_for_policy(session, policy.id)
    session.commit()
    return _redirect(f"/policies/{policy_id}?published=1")


@router.post("/policies/{policy_id}/targets")
def set_targets(
    policy_id: uuid.UUID,
    request: Request,
    rank: int = Form(default=0),
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    """Bulk assignment (F2): one policy, many targets, one action."""
    policy = session.get(Policy, policy_id)
    if policy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "policy not found")

    form = _sync_form(request)
    selected = {
        AssignmentScope.DEVICE: _uuids(form.getlist("device_ids")),
        AssignmentScope.GROUP: _uuids(form.getlist("group_ids")),
        AssignmentScope.TAG: _uuids(form.getlist("tag_ids")),
    }

    existing = {
        (a.scope, a.device_id or a.group_id or a.tag_id): a
        for a in session.scalars(select(Assignment).where(Assignment.policy_id == policy.id))
    }
    requested = {(scope, target) for scope, ids in selected.items() for target in ids}

    affected: set[uuid.UUID] = set()

    # Replace semantics: the form describes the policy's complete target set, so
    # unticking a box has to actually unassign.
    for key, assignment in existing.items():
        if key not in requested:
            affected |= eff.devices_targeted_by(session, assignment)
            session.delete(assignment)

    column = {
        AssignmentScope.DEVICE: "device_id",
        AssignmentScope.GROUP: "group_id",
        AssignmentScope.TAG: "tag_id",
    }
    for scope, target_id in requested:
        if (scope, target_id) in existing:
            existing[(scope, target_id)].rank = rank
            affected |= eff.devices_targeted_by(session, existing[(scope, target_id)])
            continue
        assignment = Assignment(
            policy_id=policy.id, scope=scope, rank=rank, **{column[scope]: target_id}
        )
        session.add(assignment)
        session.flush()
        affected |= eff.devices_targeted_by(session, assignment)

    session.flush()
    eff.invalidate(session, affected)
    session.commit()
    return _redirect(f"/policies/{policy_id}?assigned={len(requested)}")


# --------------------------------------------------------------------------- #
# Enrollment
# --------------------------------------------------------------------------- #


@router.get("/enrollment", response_class=HTMLResponse)
def enrollment_page(
    request: Request,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> HTMLResponse:
    return _render(
        request,
        "enrollment.html",
        identity=identity,
        tokens=list(
            session.scalars(select(EnrollmentToken).order_by(EnrollmentToken.created_at.desc()))
        ),
        groups=list(session.scalars(select(DeviceGroup).order_by(DeviceGroup.name))),
        tags=list(session.scalars(select(Tag).order_by(Tag.name))),
        qr_svg=None,
        payload=None,
        secret=None,
    )


@router.post("/enrollment")
def create_enrollment(
    request: Request,
    name: str = Form(...),
    max_uses: int | None = Form(default=None),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    vault: TokenVault = Depends(get_token_vault),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    """Mint a token, then hand off to its QR page.

    One place renders QR codes, whether the token was made a second ago or last
    week — so there is no "you should have saved it" path through the UI.
    """
    form = _sync_form(request)
    issued = create_token(
        session,
        name=name,
        ttl_hours=settings.enrollment_token_ttl_hours,
        max_uses=max_uses,
        group_ids=_uuids(form.getlist("group_ids")),
        tag_ids=_uuids(form.getlist("tag_ids")),
        created_by=None if identity.is_anonymous else identity.username,
        vault=vault,
    )
    session.commit()
    return _redirect(f"/enrollment/{issued.token.id}/qr")


@router.get("/enrollment/{token_id}/qr", response_class=HTMLResponse)
def token_qr(
    token_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    vault: TokenVault = Depends(get_token_vault),
    storage: ArtifactStorage = Depends(get_storage),
    identity: AdminIdentity = Depends(admin_required),
) -> HTMLResponse:
    return _render_token_qr(request, token_id, session, settings, vault, identity, storage)


@router.post("/enrollment/{token_id}/qr", response_class=HTMLResponse)
def token_qr_with_wifi(
    token_id: uuid.UUID,
    request: Request,
    wifi_ssid: str = Form(default=""),
    wifi_password: str = Form(default=""),
    wifi_security: str = Form(default="WPA"),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    vault: TokenVault = Depends(get_token_vault),
    storage: ArtifactStorage = Depends(get_storage),
    identity: AdminIdentity = Depends(admin_required),
) -> HTMLResponse:
    """Re-render the QR with Wi-Fi credentials embedded.

    The credentials are used for this render only and never persisted: a Wi-Fi
    password in the database would be a second recoverable secret, and the tablet
    only needs it once, to reach the server during provisioning.
    """
    return _render_token_qr(
        request, token_id, session, settings, vault, identity, storage,
        wifi_ssid=wifi_ssid.strip() or None,
        wifi_password=wifi_password or None,
        wifi_security=wifi_security,
    )


def _render_token_qr(
    request: Request,
    token_id: uuid.UUID,
    session: Session,
    settings: Settings,
    vault: TokenVault,
    identity: AdminIdentity,
    storage: ArtifactStorage,
    *,
    wifi_ssid: str | None = None,
    wifi_password: str | None = None,
    wifi_security: str = "WPA",
) -> HTMLResponse:
    token = session.get(EnrollmentToken, token_id)
    if token is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "enrollment token not found")

    context: dict[str, Any] = {
        "token": token,
        "wifi_ssid": wifi_ssid,
        "wifi_security": wifi_security,
        "qr_svg": None,
        "payload": None,
        "secret": None,
        "problem": None,
    }

    # Refuse to render a QR that cannot enrol. Handing someone a scannable code
    # that will fail costs them a factory reset before they discover it.
    unusable = token.unusable_reason(now=datetime.now(timezone.utc))
    if unusable:
        context["problem"] = f"No QR: {unusable}. Create a new token instead."
        return _render(request, "token_qr.html", identity=identity, **context)

    secret = reveal_secret(token, vault)
    if secret is None:
        context["problem"] = (
            "This token's secret cannot be recovered — it was created before "
            "secrets were stored recoverably, or under a different vault key. "
            "Create a new token."
        )
        return _render(request, "token_qr.html", identity=identity, **context)

    try:
        payload = provisioning.qr_payload(
            settings,
            secret,
            wifi_ssid=wifi_ssid,
            wifi_password=wifi_password,
            wifi_security=wifi_security,
            declared_receivers=package_service.declared_receivers(
                session, storage, settings.agent_package_name
            ),
        )
    except provisioning.ProvisioningError as exc:
        context["problem"] = str(exc)
        return _render(request, "token_qr.html", identity=identity, **context)

    context["payload"] = payload
    context["secret"] = secret
    context["qr_svg"] = _qr_svg(json.dumps(payload))
    return _render(request, "token_qr.html", identity=identity, **context)


def _qr_svg(text: str) -> str:
    """Render the provisioning payload as an inline SVG.

    SVG rather than PNG so no image library is needed, and inline so the page works
    with no external requests — the console may well be used on an isolated network.
    """
    code = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=8,
        border=2,
        image_factory=qrcode.image.svg.SvgPathImage,
    )
    code.add_data(text)
    code.make(fit=True)

    buffer = io.BytesIO()
    code.make_image().save(buffer)
    return buffer.getvalue().decode()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _redirect(location: str) -> RedirectResponse:
    # 303 so the browser follows a POST with a GET and a refresh does not resubmit.
    return RedirectResponse(location, status_code=status.HTTP_303_SEE_OTHER)


def _quote(text: str) -> str:
    from urllib.parse import quote

    return quote(text[:300])


def _uuids(values: list[str]) -> list[uuid.UUID]:
    parsed = []
    for value in values:
        try:
            parsed.append(uuid.UUID(value))
        except (ValueError, AttributeError):
            continue
    return parsed


def _sync_form(request: Request):
    """Read the submitted form from a synchronous endpoint.

    The rest of the app is sync, so these handlers run in a threadpool where there
    is no running loop to await Starlette's async form parser on.
    """
    import anyio

    return anyio.from_thread.run(request.form)
