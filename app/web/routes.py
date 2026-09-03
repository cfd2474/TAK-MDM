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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import qrcode
import qrcode.image.svg
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import (
    get_db,
    get_enrollment_qr_guard,
    get_session_factory,
    get_storage,
    get_token_vault,
)
from app.security import admin_auth, csrf
from app.security.admin_auth import AdminIdentity, admin_required
from app.security.enrollment_qr import EnrollmentQrGuard
from app.security.token_vault import TokenVault
from app.artifacts.storage import ArtifactStorage
from app.config import Settings, get_settings
from app.db.models import (
    AppPackage,
    AppPackageVersion,
    Assignment,
    AssignmentScope,
    CommandStatus,
    CommandType,
    Device,
    DeviceGroup,
    EnrollmentState,
    AppGroup,
    CustomAttribute,
    DeviceCertificate,
    ManagedFile,
    Policy,
    PolicyVersion,
    ProfileAssignment,
    Tag,
    TakGovLinkStatus,
)
from app.policies import creator_catalog
from app.policies import form_parse, form_schema
from app.policies.registry import PolicyTypeError, registry
from app.services import agent_update as agent_update_service
from app.services import import_jobs
from app.services import tak_gov
from app.services import tak_gov_link
from app.services import app_groups as app_group_service
from app.services import commands as command_service
from app.services import content_admin
from app.services import custom_attributes as attribute_service
from app.services import files as file_service
from app.services import guides as guide_service
from app.services import reports as report_service
from app.services import settings_store
from app.services import device_identity
from app.services import device_logs as log_service
from app.services import effective_policy as eff
from app.services import fleet as fleet_service
from app.services import packages as package_service
from app.services import policy_admin
from app.services import profiles as profile_service
from app.services import provisioning
from app.services.enrollment import (
    EnrollmentError,
    get_primary_token,
    mint_qr_secret,
    retire_and_create_primary,
    revoke_device_certificates,
    revoke_token,
)

router = APIRouter(tags=["admin-ui"], include_in_schema=False)

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
_TEMPLATES.env.filters["pretty_json"] = lambda value: json.dumps(value, indent=2, sort_keys=True)


def _spec_rows(spec: Any, policy_type: str | None = None) -> list[dict[str, str]]:
    """A policy spec as flat label/value rows for a readable, no-JSON summary.

    Given the policy type, field labels come from the spec's own ``title`` (the
    same text the editor shows); otherwise the raw key is de-underscored.
    """
    labels: dict[str, str] = {}
    if policy_type:
        try:
            labels = {f.name: f.label for f in form_schema.form_fields(policy_type)}
        except Exception:
            labels = {}
    rows: list[dict[str, str]] = []

    def render(value: Any) -> str:
        if isinstance(value, bool):
            return "yes" if value else "no"
        if isinstance(value, list):
            if not value:
                return "(none)"
            if all(not isinstance(v, (dict, list)) for v in value):
                return ", ".join(str(v) for v in value)
            return "; ".join(
                ", ".join(f"{k}={render(v2)}" for k, v2 in v.items())
                if isinstance(v, dict) else render(v)
                for v in value
            )
        if isinstance(value, dict):
            return ", ".join(f"{k}={render(v)}" for k, v in value.items())
        return str(value)

    for key, value in (spec or {}).items():
        rows.append(
            {"label": labels.get(key, key.replace("_", " ")), "value": render(value)}
        )
    return rows


_TEMPLATES.env.filters["spec_rows"] = _spec_rows
_TEMPLATES.env.filters["category_label"] = lambda key: (
    creator_catalog.get(key).label if creator_catalog.get(key) else key
)


def _render(
    request: Request, template: str, identity: AdminIdentity | None = None, **context: Any
) -> HTMLResponse:
    """Render a page, and make sure it carries a usable CSRF token.

    Issued here, on every page, rather than by each route that happens to contain a
    form. A page that renders a form without a token would fail on submit with a
    403 — loudly, which is the right failure — but issuing centrally means it does
    not happen at all.
    """
    context["identity"] = identity
    settings = get_settings()

    token = admin_auth.issue_csrf_token(identity, settings) if identity else ""
    context["csrf_token"] = token

    response = _TEMPLATES.TemplateResponse(request, template, context)
    if token:
        response.set_cookie(
            csrf.COOKIE_NAME,
            token,
            max_age=csrf.DEFAULT_TTL_SECONDS,
            # Lax, not Strict: the console is reached by following links, and Strict
            # would drop the cookie on arrival from Authentik's redirect, leaving
            # the first form submit mysteriously broken.
            samesite="lax",
            # Only over HTTPS in deployment. Left off when no origin is configured,
            # because local development runs on plain http and a Secure cookie would
            # silently never be set.
            secure=bool(settings.console_origin.startswith("https://")),
            httponly=False,
        )
    return response


# --------------------------------------------------------------------------- #
# Fleet
# --------------------------------------------------------------------------- #


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> HTMLResponse:
    rows = fleet_service.fleet_rows(session)
    return _render(
        request,
        "manage.html",
        identity=identity,
        rows=rows,
        counts={
            "devices": len(rows),
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
        attributes=attribute_service.values_for_device(session, device_id),
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


@router.post("/devices/{device_id}/checkin")
def force_checkin_form(
    device_id: uuid.UUID,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    """Ring this device's long-poll so it checks in now, instead of waiting for
    its next park slice."""
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")

    parked = eff.request_checkin(session, {device_id})
    session.commit()
    return _redirect(
        f"/devices/{device_id}?checkin={'now' if device_id in parked else 'queued'}"
    )


@router.post("/devices/{device_id}/rename")
def rename_device_form(
    device_id: uuid.UUID,
    name: str = Form(default=""),
    next: str = Form(default=""),
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    """Set or clear a device's friendly name.

    The name also travels back to the device on its next check-in, where the
    ATLAS MDM app shows it. Note: a normally-installed Device Owner cannot write
    the OS "About phone > Device name" — that is a platform restriction
    (`setGlobalSetting` has a fixed whitelist that excludes it), deferred to the
    Knox layer (R3).
    """
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")

    device.name = name.strip() or None
    session.commit()
    dest = next if next.startswith("/") and not next.startswith("//") else f"/devices/{device_id}"
    return _redirect(dest)


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
    all_profiles = profile_service.list_profiles(session, include_archived=True)
    live = [p for p in all_profiles if p.archived_at is None]

    # For the archive-confirmation modal: which devices each live policy is on now.
    reaches: dict[str, list[str]] = {}
    for profile in live:
        device_ids = eff.devices_affected_by_profile(session, profile.id)
        devices = (
            session.scalars(select(Device).where(Device.id.in_(device_ids))).all()
            if device_ids
            else []
        )
        reaches[str(profile.id)] = sorted(d.name or d.serial_number for d in devices)

    return _render(
        request,
        "policies.html",
        identity=identity,
        profiles=live,
        archived_profiles=[p for p in all_profiles if p.archived_at is not None],
        reaches=reaches,
        device_policies=policy_admin.list_tab(session, "device"),
        templates=policy_admin.list_tab(session, "templates"),
        archived=policy_admin.list_tab(session, "archived"),
    )


def _catalog_view(profile=None) -> list[dict[str, Any]]:
    """The creator/editor category rail (W12): each wired category with its
    sub-pages (one per ui_group), a per-sub-page 'has data' flag, and the
    section's current spec."""
    view: list[dict[str, Any]] = []
    for category in creator_catalog.CATALOG:
        section = (
            profile_service.section_for(profile, category.key) if profile else None
        )
        spec = (
            section.latest_version.spec
            if section and section.latest_version
            else {}
        )
        pages = (
            form_schema.sub_pages(category.policy_type) if category.wired else []
        )
        managed = (
            form_schema.managed_group_slugs(category.policy_type, spec)
            if category.wired
            else set()
        )
        view.append(
            {
                "category": category,
                "pages": [
                    {"page": p, "has_data": p.slug in managed} for p in pages
                ],
                "section": section,
                "spec": spec,
                "has_data": bool(spec),
            }
        )
    return view


def _form_catalogs(session: Session) -> dict[str, Any]:
    """Uploaded apps and files, for the policy form's list controls."""
    return {
        "app_packages": list(
            session.scalars(select(AppPackage).order_by(AppPackage.package_name))
        ),
        "managed_files": list(
            session.scalars(select(ManagedFile).order_by(ManagedFile.name))
        ),
    }


def _app_group_hints(session: Session) -> list[dict[str, Any]]:
    """App groups as plain data for the App Management section's "insert" helper."""
    return [
        {"name": g.name, "packages": [p.package_name for p in g.packages]}
        for g in app_group_service.list_groups(session)
    ]


@router.get("/policies/new", response_class=HTMLResponse)
def new_policy_page(
    request: Request,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> HTMLResponse:
    """The guided profile creator: pick categories, fill the wired ones (DW5)."""
    return _render(
        request,
        "profile_editor.html",
        identity=identity,
        mode="new",
        profile=None,
        catalog=_catalog_view(),
        app_groups=_app_group_hints(session),
        **_form_catalogs(session),
    )


@router.get("/policies/new/single", response_class=HTMLResponse)
def new_single_policy_page(
    request: Request,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> HTMLResponse:
    """Advanced: a lone single-concern policy, outside any profile."""
    wired = [c for c in creator_catalog.CATALOG if c.wired]
    return _render(
        request,
        "policy_new.html",
        identity=identity,
        wired_types=[
            {
                "policy_type": c.policy_type,
                "label": c.label,
                "pages": form_schema.sub_pages(c.policy_type),
            }
            for c in wired
        ],
        app_groups=_app_group_hints(session),
        **_form_catalogs(session),
    )


@router.post("/profiles")
def create_profile_form(
    request: Request,
    name: str = Form(...),
    description: str = Form(default=""),
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    form = _sync_form(request)
    sections: dict[str, dict] = {}
    for category in creator_catalog.wired_categories():
        parsed = form_parse.parse_form(category.policy_type, form)
        if parsed:
            sections[category.key] = parsed

    try:
        profile = profile_service.create_profile(
            session,
            name=name,
            description=description or None,
            sections=sections,
            created_by=None if identity.is_anonymous else identity.username,
        )
        session.commit()
    except profile_service.ProfileError as exc:
        return _redirect(f"/policies/new?error={_quote(str(exc))}")
    except Exception:
        session.rollback()
        return _redirect(f"/policies/new?error={_quote(f'a profile named {name!r} already exists')}")

    return _redirect(f"/profiles/{profile.id}")


@router.get("/profiles/{profile_id}", response_class=HTMLResponse)
def profile_detail(
    profile_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> HTMLResponse:
    profile = profile_service.get_profile(session, profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")

    pas = list(
        session.scalars(
            select(ProfileAssignment).where(ProfileAssignment.profile_id == profile.id)
        )
    )
    assigned = {
        "device": {a.device_id for a in pas if a.scope is AssignmentScope.DEVICE},
        "group": {a.group_id for a in pas if a.scope is AssignmentScope.GROUP},
        "tag": {a.tag_id for a in pas if a.scope is AssignmentScope.TAG},
    }
    return _render(
        request,
        "profile_editor.html",
        identity=identity,
        mode="edit",
        profile=profile,
        catalog=_catalog_view(profile),
        app_groups=_app_group_hints(session),
        **_form_catalogs(session),
        devices=list(session.scalars(select(Device).order_by(Device.serial_number))),
        groups=list(session.scalars(select(DeviceGroup).order_by(DeviceGroup.name))),
        tags=list(session.scalars(select(Tag).order_by(Tag.name))),
        assigned=assigned,
        current_rank=pas[0].rank if pas else 0,
    )


@router.post("/profiles/{profile_id}/targets")
def set_profile_targets_form(
    profile_id: uuid.UUID,
    request: Request,
    rank: int = Form(default=0),
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    """Bulk assignment (F2): one profile, many targets, replace semantics."""
    profile = profile_service.get_profile(session, profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")

    form = _sync_form(request)
    selected = {
        AssignmentScope.DEVICE: _uuids(form.getlist("device_ids")),
        AssignmentScope.GROUP: _uuids(form.getlist("group_ids")),
        AssignmentScope.TAG: _uuids(form.getlist("tag_ids")),
    }
    existing = {
        (a.scope, a.device_id or a.group_id or a.tag_id): a
        for a in session.scalars(
            select(ProfileAssignment).where(ProfileAssignment.profile_id == profile.id)
        )
    }
    requested = {(scope, t) for scope, ids in selected.items() for t in ids}
    affected: set[uuid.UUID] = set()

    for key, assignment in existing.items():
        if key not in requested:
            affected |= eff.devices_targeted_by_profile_assignment(session, assignment)
            session.delete(assignment)

    column = {
        AssignmentScope.DEVICE: "device_id",
        AssignmentScope.GROUP: "group_id",
        AssignmentScope.TAG: "tag_id",
    }
    for scope, target_id in requested:
        if (scope, target_id) in existing:
            existing[(scope, target_id)].rank = rank
            affected |= eff.devices_targeted_by_profile_assignment(
                session, existing[(scope, target_id)]
            )
            continue
        assignment = ProfileAssignment(
            profile_id=profile.id, scope=scope, rank=rank, **{column[scope]: target_id}
        )
        session.add(assignment)
        session.flush()
        affected |= eff.devices_targeted_by_profile_assignment(session, assignment)

    session.flush()
    eff.invalidate(session, affected)
    session.commit()
    return _redirect(f"/profiles/{profile_id}?assigned={len(requested)}")


@router.post("/profiles/{profile_id}")
def save_profile_form(
    profile_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    """One save for the whole composite editor (W21): every wired category is on
    the page, so parse them all — upsert the ones with data, drop the ones the
    operator emptied — in a single transaction."""
    profile = profile_service.get_profile(session, profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")

    form = _sync_form(request)
    who = None if identity.is_anonymous else identity.username
    try:
        for category in creator_catalog.wired_categories():
            parsed = form_parse.parse_form(category.policy_type, form)
            if parsed:
                profile_service.upsert_section(session, profile, category.key, parsed, published_by=who)
            else:
                profile_service.remove_section(session, profile, category.key)
        eff.invalidate_for_profile(session, profile.id)
        session.commit()
    except profile_service.ProfileError as exc:
        session.rollback()
        return _redirect(f"/profiles/{profile_id}?error={_quote(str(exc))}")
    return _redirect(f"/profiles/{profile_id}?saved=policy")


@router.post("/profiles/{profile_id}/sections/{category_key}")
def upsert_section_form(
    profile_id: uuid.UUID,
    category_key: str,
    request: Request,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    profile = profile_service.get_profile(session, profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")
    category = creator_catalog.get(category_key)
    if category is None or not category.wired:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown or unwired category")

    parsed = form_parse.parse_form(category.policy_type, _sync_form(request))
    try:
        if parsed:
            profile_service.upsert_section(
                session,
                profile,
                category_key,
                parsed,
                published_by=None if identity.is_anonymous else identity.username,
            )
        else:
            # An emptied form means "this policy no longer manages this category".
            profile_service.remove_section(session, profile, category_key)
        session.commit()
    except profile_service.ProfileError as exc:
        return _redirect(f"/profiles/{profile_id}?error={_quote(str(exc))}#cat-{category_key}")
    return _redirect(f"/profiles/{profile_id}?saved={category_key}#cat-{category_key}")


@router.post("/profiles/{profile_id}/sections/{category_key}/remove")
def remove_section_form(
    profile_id: uuid.UUID,
    category_key: str,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    profile = profile_service.get_profile(session, profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")
    profile_service.remove_section(session, profile, category_key)
    session.commit()
    return _redirect(f"/profiles/{profile_id}#cat-{category_key}")


@router.post("/profiles/{profile_id}/archive")
def archive_profile_form(
    profile_id: uuid.UUID,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    profile = profile_service.get_profile(session, profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")
    profile_service.archive(session, profile)
    session.commit()
    return _redirect("/policies#tab-archived")


@router.post("/profiles/{profile_id}/restore")
def restore_profile_form(
    profile_id: uuid.UUID,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    profile = profile_service.get_profile(session, profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")
    profile_service.restore(session, profile)
    session.commit()
    return _redirect(f"/profiles/{profile_id}")


@router.post("/policies")
def create_policy(
    request: Request,
    name: str = Form(...),
    policy_type: str = Form(...),
    description: str = Form(default=""),
    is_template: bool = Form(default=False),
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    try:
        parsed = form_parse.parse_form(policy_type, _sync_form(request))
        validated = registry.validate_spec(policy_type, parsed)
    except PolicyTypeError as exc:
        return _redirect(f"/policies/new/single?error={_quote(str(exc))}")

    policy = Policy(
        name=name,
        policy_type=policy_type,
        description=description or None,
        is_template=is_template,
    )
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
        return _redirect(
            f"/policies/new?error={_quote(f'a policy named {name!r} already exists')}"
        )

    return _redirect(f"/policies/{policy.id}")


@router.post("/policies/{policy_id}/archive")
def archive_policy_form(
    policy_id: uuid.UUID,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    try:
        policy_admin.archive(session, policy_id)
    except policy_admin.PolicyAdminError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    session.commit()
    return _redirect("/policies#tab-archived")


@router.post("/policies/{policy_id}/restore")
def restore_policy_form(
    policy_id: uuid.UUID,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    try:
        policy_admin.restore(session, policy_id)
    except policy_admin.PolicyAdminError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    session.commit()
    return _redirect(f"/policies/{policy_id}")


@router.post("/policies/clone")
def clone_policy_form(
    source_id: uuid.UUID = Form(...),
    name: str = Form(...),
    as_template: bool = Form(default=False),
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    """Clone a policy or template. Used by the "use a template" picker in the New
    Policy modal and by "save as template" on the detail page."""
    try:
        policy = policy_admin.clone(
            session,
            source_id,
            name=name,
            as_template=as_template,
            published_by=None if identity.is_anonymous else identity.username,
        )
        session.commit()
    except policy_admin.PolicyAdminError as exc:
        return _redirect(f"/policies?error={_quote(str(exc))}")
    except Exception:
        session.rollback()
        return _redirect(f"/policies?error={_quote(f'a policy named {name!r} already exists')}")
    return _redirect(f"/policies/{policy.id}")


@router.get("/policies/{policy_id}", response_class=HTMLResponse, response_model=None)
def policy_detail(
    policy_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> HTMLResponse | RedirectResponse:
    policy = session.get(Policy, policy_id)
    if policy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "policy not found")

    # A section of a composite is managed only through that composite (W21).
    if policy.profile_id is not None:
        return _redirect(f"/profiles/{policy.profile_id}")

    assignments = list(
        session.scalars(select(Assignment).where(Assignment.policy_id == policy.id))
    )
    assigned = {
        "device": {a.device_id for a in assignments if a.scope is AssignmentScope.DEVICE},
        "group": {a.group_id for a in assignments if a.scope is AssignmentScope.GROUP},
        "tag": {a.tag_id for a in assignments if a.scope is AssignmentScope.TAG},
    }

    current_spec = policy.latest_version.spec if policy.latest_version else {}
    return _render(
        request,
        "policy_detail.html",
        identity=identity,
        policy=policy,
        pages=form_schema.sub_pages(policy.policy_type),
        current_spec=current_spec,
        managed_pages=form_schema.managed_group_slugs(policy.policy_type, current_spec),
        **_form_catalogs(session),
        devices=list(session.scalars(select(Device).order_by(Device.serial_number))),
        groups=list(session.scalars(select(DeviceGroup).order_by(DeviceGroup.name))),
        tags=list(session.scalars(select(Tag).order_by(Tag.name))),
        assigned=assigned,
        current_rank=assignments[0].rank if assignments else 0,
    )


@router.post("/policies/{policy_id}/versions")
def publish_version(
    policy_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    policy = session.get(Policy, policy_id)
    if policy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "policy not found")

    try:
        parsed = form_parse.parse_form(policy.policy_type, _sync_form(request))
        validated = registry.validate_spec(policy.policy_type, parsed)
    except PolicyTypeError as exc:
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
    settings: Settings = Depends(get_settings),
    identity: AdminIdentity = Depends(admin_required),
) -> HTMLResponse:
    """The one active enrollment token, or an empty state (Chunk 14).

    No list of ad-hoc tokens here any more: the operator's model is a single
    persistent credential, retired and replaced rather than multiplied. Its raw
    secret is never on this page — only "Generate QR", which mints a 15-minute
    derivative each time it is pressed.
    """
    return _render(
        request,
        "enroll.html",
        identity=identity,
        primary=get_primary_token(session),
        groups=list(session.scalars(select(DeviceGroup).order_by(DeviceGroup.name))),
        tags=list(session.scalars(select(Tag).order_by(Tag.name))),
        qr_ttl_seconds=settings.enrollment_qr_ttl_seconds,
        qr_svg=None,
        payload=None,
        secret=None,
        problem=None,
    )


@router.post("/enrollment/primary")
def create_primary(
    request: Request,
    name: str = Form(...),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    storage: ArtifactStorage = Depends(get_storage),
    vault: TokenVault = Depends(get_token_vault),
    guard: EnrollmentQrGuard = Depends(get_enrollment_qr_guard),
    identity: AdminIdentity = Depends(admin_required),
) -> HTMLResponse:
    """Retire whichever primary is live and stand up its replacement.

    Immediately mints and shows a QR for the new primary too — matching the
    established "creating a token redirects to its QR" pattern (D77) — so getting
    the fleet's one enrollment credential moving is a single action, not two.
    """
    form = _sync_form(request)
    retire_and_create_primary(
        session,
        name=name,
        group_ids=_uuids(form.getlist("group_ids")),
        tag_ids=_uuids(form.getlist("tag_ids")),
        created_by=None if identity.is_anonymous else identity.username,
        vault=vault,
    )
    session.commit()
    return _render_primary_qr(request, session, settings, storage, guard, identity)


@router.post("/enrollment/retire")
def retire_primary(
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    """Retire the active primary with nothing to replace it.

    A deliberate "go dark" action: no enrollment can succeed — by QR or by any
    already-issued one, since verification re-checks the primary on every use —
    until a new primary is created.
    """
    primary = get_primary_token(session)
    if primary is not None:
        revoke_token(session, primary)
        session.commit()
    return _redirect("/enrollment")


@router.post("/enrollment/qr", response_class=HTMLResponse)
def generate_qr(
    request: Request,
    wifi_ssid: str = Form(default=""),
    wifi_password: str = Form(default=""),
    wifi_security: str = Form(default="WPA"),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    storage: ArtifactStorage = Depends(get_storage),
    guard: EnrollmentQrGuard = Depends(get_enrollment_qr_guard),
    identity: AdminIdentity = Depends(admin_required),
) -> HTMLResponse:
    """Mint a fresh 15-minute QR for the active primary.

    Also what the Wi-Fi form on the QR page itself submits to: there is no
    per-QR row to re-render with credentials added, so embedding Wi-Fi simply
    mints a new secret with the credentials baked in. The one just displayed
    keeps working until its own 15 minutes elapse — nothing revokes it.
    """
    return _render_primary_qr(
        request, session, settings, storage, guard, identity,
        wifi_ssid=wifi_ssid.strip() or None,
        wifi_password=wifi_password or None,
        wifi_security=wifi_security,
    )


def _render_primary_qr(
    request: Request,
    session: Session,
    settings: Settings,
    storage: ArtifactStorage,
    guard: EnrollmentQrGuard,
    identity: AdminIdentity,
    *,
    wifi_ssid: str | None = None,
    wifi_password: str | None = None,
    wifi_security: str = "WPA",
) -> HTMLResponse:
    context: dict[str, Any] = {
        "primary": None,
        "wifi_ssid": wifi_ssid,
        "wifi_security": wifi_security,
        "qr_svg": None,
        "payload": None,
        "secret": None,
        "qr_expires_at": None,
        "problem": None,
    }

    try:
        primary, secret = mint_qr_secret(session, guard)
    except EnrollmentError as exc:
        context["problem"] = str(exc)
        return _render(request, "token_qr.html", identity=identity, **context)
    context["primary"] = primary

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

    session.commit()
    context["payload"] = payload
    context["secret"] = secret
    context["qr_expires_at"] = datetime.now(timezone.utc) + timedelta(
        seconds=settings.enrollment_qr_ttl_seconds
    )
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
# Apps — local packages, the ATLAS store, app groups (W5)
# --------------------------------------------------------------------------- #


@router.get("/apps", response_class=HTMLResponse)
def apps_page(
    request: Request,
    session: Session = Depends(get_db),
    vault: TokenVault = Depends(get_token_vault),
    identity: AdminIdentity = Depends(admin_required),
) -> HTMLResponse:
    packages = list(session.scalars(select(AppPackage).order_by(AppPackage.package_name)))
    return _render(
        request,
        "apps.html",
        identity=identity,
        packages=packages,
        store_packages=[p for p in packages if p.store_listed],
        groups=app_group_service.list_groups(session),
        tpc=_tpc_panel(request, session, vault),
    )


def _tpc_panel(request: Request, session: Session, vault: TokenVault) -> dict:
    """The TPC Plugins tab.

    The catalog is only fetched when the tab is actually asked for. Loading it on
    every visit to Apps would put a third-party network call — and a token
    refresh — in the path of unrelated work like uploading an APK.
    """
    link = tak_gov_link.get(session)
    linked = link.status is TakGovLinkStatus.LINKED
    product = request.query_params.get("product") or tak_gov.DEFAULT_PRODUCT
    if product not in tak_gov.PRODUCTS:
        product = tak_gov.DEFAULT_PRODUCT
    product_version = (request.query_params.get("product_version") or "").strip()
    if product_version not in tak_gov.PRODUCT_VERSIONS:
        product_version = tak_gov.DEFAULT_PRODUCT_VERSION

    panel = {
        "linked": linked,
        "status": link.status.value,
        "account_label": link.account_label,
        "products": tak_gov.PRODUCTS,
        "product_versions": tak_gov.PRODUCT_VERSIONS,
        "product": product,
        "product_version": product_version,
        "plugins": [],
        "error": None,
        "loaded": False,
        "imported": set(),
    }
    if linked and request.query_params.get("tab") == "tpc":
        panel["loaded"] = True
        plugins, error = tak_gov_link.catalog(
            session, vault, product=product, product_version=product_version
        )
        session.commit()  # a refresh may have rotated the token
        # Sorted here rather than left to the client sorter, so the order is the
        # same before JavaScript runs and for anyone who never gets it.
        panel["plugins"] = sorted(
            plugins, key=lambda x: (x.display_name or x.package_name).lower()
        )
        panel["error"] = error
        panel["imported"] = _already_imported(session, plugins)
    return panel


def _already_imported(session: Session, plugins: list) -> set[tuple[str, int]]:
    """(package_name, revision_code) pairs the local library already holds.

    Matched on revision_code against versionCode, which is what `tpc.md` says to
    key on and what Android's own upgrade rule uses. Shown so an operator can see
    at a glance what is new, rather than discovering it by pressing Import and
    reading "already uploaded".
    """
    wanted = {p.package_name for p in plugins}
    if not wanted:
        return set()
    rows = session.execute(
        select(AppPackage.package_name, AppPackageVersion.version_code)
        .join(AppPackageVersion, AppPackageVersion.package_id == AppPackage.id)
        .where(AppPackage.package_name.in_(wanted))
    )
    return {(name, code) for name, code in rows}


@router.post("/apps/tpc/import")
def import_tpc_plugin_form(
    identifier: str = Form(...),
    product: str = Form(default=tak_gov.DEFAULT_PRODUCT),
    product_version: str = Form(default=tak_gov.DEFAULT_PRODUCT_VERSION),
    label: str = Form(default=""),
    session_factory=Depends(get_session_factory),
    storage: ArtifactStorage = Depends(get_storage),
    vault: TokenVault = Depends(get_token_vault),
    identity: AdminIdentity = Depends(admin_required),
) -> JSONResponse:
    """Start an import and hand back a job to watch.

    Returns JSON rather than redirecting: a 433 MB plugin takes minutes, and a
    request held open for that long tells the operator nothing about whether it is
    working. The console opens a modal and polls the status route below.
    """
    if product not in tak_gov.PRODUCTS:
        product = tak_gov.DEFAULT_PRODUCT
    if product_version not in tak_gov.PRODUCT_VERSIONS:
        product_version = tak_gov.DEFAULT_PRODUCT_VERSION

    job = import_jobs.start(
        session_factory,
        vault,
        storage,
        identifier=identifier,
        label=label.strip() or identifier,
        product=product,
        product_version=product_version,
    )
    return JSONResponse(job.as_dict(), status_code=status.HTTP_202_ACCEPTED)


@router.get("/apps/tpc/import/{job_id}")
def import_tpc_plugin_status(
    job_id: str,
    identity: AdminIdentity = Depends(admin_required),
) -> JSONResponse:
    job = import_jobs.get(job_id)
    if job is None:
        # Most likely the server restarted mid-import. Say that, rather than 404ing
        # into a modal that spins forever.
        return JSONResponse(
            {"state": "failed", "error": "the import job is no longer known — "
             "the server may have restarted. Press Import again."},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return JSONResponse(job.as_dict())


@router.post("/apps/upload")
def upload_app_form(
    label: str = Form(default=""),
    file: UploadFile = File(...),
    session: Session = Depends(get_db),
    storage: ArtifactStorage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    data = file.file.read()
    if not data:
        return _redirect("/apps?error=the+uploaded+file+is+empty")
    if len(data) > settings.max_upload_bytes:
        return _redirect(f"/apps?error={_quote(f'upload exceeds {settings.max_upload_bytes} bytes')}")
    try:
        package_service.ingest(session, storage, data, label=label.strip() or None)
    except package_service.PackageError as exc:
        return _redirect(f"/apps?error={_quote(str(exc))}")
    eff.invalidate_all(session)
    session.commit()
    return _redirect("/apps")


@router.post("/apps/{package_id}/store")
def toggle_store_form(
    package_id: uuid.UUID,
    listed: str = Form(default=""),
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    package = session.get(AppPackage, package_id)
    if package is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "package not found")
    package.store_listed = listed == "true"
    session.commit()
    return _redirect("/apps#tab-" + ("store" if package.store_listed else "local"))


@router.post("/apps/{package_id}/delete")
def delete_app_form(
    package_id: uuid.UUID,
    session: Session = Depends(get_db),
    storage: ArtifactStorage = Depends(get_storage),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    package = session.get(AppPackage, package_id)
    if package is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "package not found")
    package_service.delete_package(session, storage, package)
    eff.invalidate_all(session)
    session.commit()
    return _redirect("/apps")


@router.post("/app-groups")
def create_app_group_form(
    request: Request,
    name: str = Form(...),
    description: str = Form(default=""),
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    form = _sync_form(request)
    try:
        group = app_group_service.create(
            session, name=name, description=description or None
        )
        app_group_service.set_members(session, group, _uuids(form.getlist("package_ids")))
        session.commit()
    except app_group_service.AppGroupError as exc:
        return _redirect(f"/apps?error={_quote(str(exc))}#tab-groups")
    except Exception:
        session.rollback()
        return _redirect(f"/apps?error={_quote(f'an app group named {name!r} already exists')}#tab-groups")
    return _redirect("/apps#tab-groups")


@router.post("/app-groups/{group_id}/members")
def set_app_group_members_form(
    group_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    group = app_group_service.get(session, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "app group not found")
    form = _sync_form(request)
    try:
        app_group_service.set_members(session, group, _uuids(form.getlist("package_ids")))
        session.commit()
    except app_group_service.AppGroupError as exc:
        return _redirect(f"/apps?error={_quote(str(exc))}#tab-groups")
    return _redirect("/apps#tab-groups")


@router.post("/app-groups/{group_id}/delete")
def delete_app_group_form(
    group_id: uuid.UUID,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    group = app_group_service.get(session, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "app group not found")
    app_group_service.delete(session, group)
    session.commit()
    return _redirect("/apps#tab-groups")


# --------------------------------------------------------------------------- #
# Content — managed files and where policies place them (W6)
# --------------------------------------------------------------------------- #


@router.get("/content", response_class=HTMLResponse)
def content_page(
    request: Request,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> HTMLResponse:
    return _render(
        request,
        "content.html",
        identity=identity,
        rows=content_admin.content_rows(session),
    )


@router.post("/content/upload")
def upload_content_form(
    name: str = Form(default=""),
    description: str = Form(default=""),
    file: UploadFile = File(...),
    session: Session = Depends(get_db),
    storage: ArtifactStorage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    data = file.file.read()
    if not data:
        return _redirect("/content?error=the+uploaded+file+is+empty")
    if len(data) > settings.max_upload_bytes:
        return _redirect(f"/content?error={_quote(f'upload exceeds {settings.max_upload_bytes} bytes')}")
    try:
        file_service.ingest_file(
            session,
            storage,
            data,
            name=name.strip() or file.filename or "unnamed",
            original_filename=file.filename or "unnamed",
            description=description or None,
            media_type=file.content_type or "application/octet-stream",
        )
        session.commit()
    except file_service.FileError as exc:
        return _redirect(f"/content?error={_quote(str(exc))}")
    return _redirect("/content")


@router.post("/content/{file_id}/edit")
def edit_content_form(
    file_id: uuid.UUID,
    name: str = Form(default=""),
    description: str = Form(default=""),
    default_dest_path: str = Form(default=""),
    default_persist: str = Form(default="inherit"),
    default_extract: str = Form(default=""),
    default_extract_to: str = Form(default=""),
    default_overwrite: str = Form(default=""),
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    managed = session.get(ManagedFile, file_id)
    if managed is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "file not found")

    if name.strip():
        managed.name = name.strip()
    managed.description = description or None
    managed.default_dest_path = default_dest_path.strip() or None
    managed.default_persist = {"yes": True, "no": False}.get(default_persist)
    managed.default_extract = True if default_extract == "true" else None
    managed.default_extract_to = default_extract_to.strip() or None
    managed.default_overwrite = default_overwrite or None
    session.commit()
    return _redirect("/content")


@router.post("/content/{file_id}/delete")
def delete_content_form(
    file_id: uuid.UUID,
    session: Session = Depends(get_db),
    storage: ArtifactStorage = Depends(get_storage),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    managed = session.get(ManagedFile, file_id)
    if managed is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "file not found")

    refs = content_admin.references(session, file_id)
    if refs:
        names = ", ".join(sorted({r.policy_name for r in refs}))
        return _redirect(
            f"/content?error={_quote(f'remove it from {names} before deleting')}"
        )

    file_service.delete_file(session, storage, managed)
    eff.invalidate_all(session)
    session.commit()
    return _redirect("/content")


# --------------------------------------------------------------------------- #
# Reports (W7)
# --------------------------------------------------------------------------- #


@router.get("/reports", response_class=HTMLResponse)
def reports_page(
    request: Request,
    identity: AdminIdentity = Depends(admin_required),
) -> HTMLResponse:
    return _render(
        request,
        "reports.html",
        identity=identity,
        reports=list(report_service.REPORTS.values()),
    )


@router.get("/reports/{key}")
def report_view(
    key: str,
    request: Request,
    format: str = "",
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
):
    report = report_service.get(key)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown report")

    columns, rows = report.build(session)

    if format == "csv":
        return Response(
            content=report_service.to_csv(columns, rows),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{key}.csv"'},
        )

    return _render(
        request,
        "report.html",
        identity=identity,
        report=report,
        columns=columns,
        rows=rows,
    )


# --------------------------------------------------------------------------- #
# Admin — certificates, integration settings, custom attributes (W8)
# --------------------------------------------------------------------------- #


@router.get("/admin", response_class=HTMLResponse)
def admin_page(
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    identity: AdminIdentity = Depends(admin_required),
) -> HTMLResponse:
    certs = list(
        session.execute(
            select(DeviceCertificate, Device.serial_number)
            .join(Device, DeviceCertificate.device_id == Device.id)
            .order_by(DeviceCertificate.issued_at.desc())
        )
    )
    groups = [
        {
            "group": group,
            "current": settings_store.group_values(session, key),
        }
        for key, group in settings_store.GROUPS.items()
    ]
    env_settings = {
        "TAKMDM_SERVER_URL": settings.server_url,
        "TAKMDM_ADMIN_AUTH_MODE": settings.admin_auth_mode,
        "TAKMDM_CONSOLE_ORIGIN": settings.console_origin or "(unset)",
        "TAKMDM_AGENT_PACKAGE_NAME": settings.agent_package_name,
        "TAKMDM_AGENT_SIGNATURE_CHECKSUM": settings.agent_signature_checksum or "(unset)",
    }
    return _render(
        request,
        "admin.html",
        identity=identity,
        certs=certs,
        ca={
            "common_name": settings.ca_common_name,
            "ca_validity_days": settings.ca_validity_days,
            "device_cert_validity_days": settings.device_cert_validity_days,
        },
        setting_groups=groups,
        env_settings=env_settings,
        agent=_agent_update_panel(session, settings),
        takgov=_takgov_panel(session),
        attributes=attribute_service.list_attributes(session),
    )


def _takgov_panel(session: Session) -> dict:
    link = tak_gov_link.get(session)
    session.commit()  # the row is created lazily on first view
    remaining = None
    if link.code_expires_at:
        remaining = max(
            0, int((link.code_expires_at - datetime.now(timezone.utc)).total_seconds())
        )
    return {"link": link, "expires_in_seconds": remaining}


@router.post("/admin/takgov/start")
def takgov_start_form(
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    try:
        tak_gov_link.start(session)
    except tak_gov.TakGovError as exc:
        return _redirect(f"/admin?error={_quote(str(exc))}#tab-takgov")
    session.commit()
    return _redirect("/admin#tab-takgov")


@router.post("/admin/takgov/poll")
def takgov_poll_form(
    session: Session = Depends(get_db),
    vault: TokenVault = Depends(get_token_vault),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    """One poll, driven by the operator saying they have entered the code.

    Deliberately not a background loop. The device-code window is about three
    minutes and the operator is standing right there, so a button is honest about
    what is happening and adds no long-lived task to babysit. If they press it
    early, `authorization_pending` leaves the link exactly as it was.
    """
    tak_gov_link.poll(
        session, vault, linked_by=None if identity.is_anonymous else identity.username
    )
    session.commit()
    return _redirect("/admin#tab-takgov")


@router.post("/admin/takgov/unlink")
def takgov_unlink_form(
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    tak_gov_link.unlink(session)
    session.commit()
    return _redirect("/admin#tab-takgov")


def _agent_update_panel(session: Session, settings: Settings) -> dict:
    """Everything the Agent updates tab shows.

    ``published_uploaded`` is reported rather than assumed: deleting the build a
    setting points at silently stops every offer, and that is exactly the kind of
    quiet nothing this feature must never do without saying so.
    """
    package_name = settings.agent_package_name
    builds = agent_update_service.versions(session, package_name)
    status = agent_update_service.rollout(session)
    published = next((v for v in builds if v.version_code == status.published), None)
    devices = list(
        session.scalars(
            select(Device)
            .where(Device.enrollment_state == EnrollmentState.ENROLLED)
            .order_by(Device.agent_version_code.is_(None).desc(), Device.agent_version_code)
        )
    )
    return {
        "package_name": package_name,
        "versions": builds,
        "rollout": status,
        "published_name": published.version_name if published else None,
        "published_uploaded": published is not None,
        "devices": devices,
    }


@router.post("/admin/agent/publish")
def publish_agent_build_form(
    version_code: str = Form(default=""),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    """Aim the fleet at an agent build, or (with a blank code) at nothing."""
    raw = version_code.strip()
    if not raw:
        agent_update_service.publish(
            session, None, updated_by=None if identity.is_anonymous else identity.username
        )
        session.commit()
        return _redirect("/admin?saved=agent#tab-agent")

    try:
        wanted = int(raw)
    except ValueError:
        return _redirect(f"/admin?error={_quote('agent versionCode must be a number')}#tab-agent")

    # Refuse to publish a build that is not in the library. The offer would be
    # dropped silently at every check-in, which looks identical to a fleet that
    # is simply slow to come back.
    if not any(v.version_code == wanted for v in agent_update_service.versions(
        session, settings.agent_package_name
    )):
        detail = f"no {settings.agent_package_name} build {wanted} has been uploaded"
        return _redirect(f"/admin?error={_quote(detail)}#tab-agent")

    agent_update_service.publish(
        session, wanted, updated_by=None if identity.is_anonymous else identity.username
    )
    session.commit()
    return _redirect("/admin?saved=agent#tab-agent")


@router.post("/admin/settings/{group_key}")
def save_admin_settings_form(
    group_key: str,
    request: Request,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    if group_key not in settings_store.GROUPS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown settings group")
    form = _sync_form(request)
    values = {f.key: (form.get(f.key) or "") for f in settings_store.GROUPS[group_key].fields}
    # Checkboxes: present means "on".
    for f in settings_store.GROUPS[group_key].fields:
        if f.kind == "bool":
            values[f.key] = "true" if form.get(f.key) else ""
    settings_store.save_group(
        session, group_key, values,
        updated_by=None if identity.is_anonymous else identity.username,
    )
    session.commit()
    return _redirect(f"/admin?saved={group_key}#tab-{group_key}")


@router.post("/admin/attributes")
def create_attribute_form(
    name: str = Form(...),
    attr_type: str = Form(default="string"),
    description: str = Form(default=""),
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    try:
        attribute_service.create(
            session, name=name, attr_type=attr_type, description=description or None
        )
        session.commit()
    except attribute_service.AttributeError_ as exc:
        return _redirect(f"/admin?error={_quote(str(exc))}#tab-attributes")
    except Exception:
        session.rollback()
        return _redirect(f"/admin?error={_quote(f'an attribute named {name!r} already exists')}#tab-attributes")
    return _redirect("/admin#tab-attributes")


@router.post("/admin/attributes/{attribute_id}/delete")
def delete_attribute_form(
    attribute_id: uuid.UUID,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    attribute = session.get(CustomAttribute, attribute_id)
    if attribute is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "attribute not found")
    attribute_service.delete(session, attribute)
    session.commit()
    return _redirect("/admin#tab-attributes")


@router.post("/admin/certs/{cert_id}/revoke")
def revoke_cert_form(
    cert_id: uuid.UUID,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    cert = session.get(DeviceCertificate, cert_id)
    if cert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "certificate not found")
    if cert.revoked_at is None:
        cert.revoked_at = datetime.now(timezone.utc)
        cert.revoked_reason = "revoked from the admin console"
        session.commit()
    return _redirect("/admin#tab-certificates")


@router.post("/devices/{device_id}/attributes")
def set_device_attribute_form(
    device_id: uuid.UUID,
    attribute_id: uuid.UUID = Form(...),
    value: str = Form(default=""),
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    if session.get(Device, device_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")
    attribute_service.set_value(session, device_id, attribute_id, value)
    session.commit()
    return _redirect(f"/devices/{device_id}#attributes")


# --------------------------------------------------------------------------- #
# Guides — how-to, FAQ, release notes (W9)
# --------------------------------------------------------------------------- #


@router.get("/guides", response_class=HTMLResponse)
def guides_page(
    request: Request,
    identity: AdminIdentity = Depends(admin_required),
) -> HTMLResponse:
    return _render(
        request,
        "guides.html",
        identity=identity,
        howto=guide_service.list_guides("howto"),
        faq=guide_service.list_guides("faq"),
        release_notes=guide_service.release_notes_html(),
    )


@router.get("/guides/{category}/{slug}", response_class=HTMLResponse)
def guide_view(
    category: str,
    slug: str,
    request: Request,
    identity: AdminIdentity = Depends(admin_required),
) -> HTMLResponse:
    if category not in guide_service.CATEGORIES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown guide category")
    found = guide_service.get_guide(category, slug)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "guide not found")
    title, body = found
    return _render(
        request, "guide.html", identity=identity, guide_title=title, guide_body=body
    )


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
