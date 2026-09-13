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

from contextlib import suppress

import csv
import io
import shutil
import os
import zipfile
import json
from concurrent.futures import ThreadPoolExecutor
import tempfile
import uuid
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections.abc import Iterator
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
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
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
from app.version import build_info
from app.artifacts import app_restrictions
from app.artifacts.storage import ArtifactStorage
from app.config import Settings, get_settings
from app.db.models import (
    enrollment_token_group,
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
    PartRole,
    Policy,
    PolicyProfile,
    PolicyVersion,
    ProfileAssignment,
    Storefront,
    TakGovLinkStatus,
)
from app.policies import creator_catalog
from app.policies import form_parse, form_schema
from app.policies.registry import PolicyTypeError, registry
from app.services import agent_update as agent_update_service
from app.services import device_health
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.artifacts import dted
from app.artifacts import mission_package
from app.services import atak_compat
from app.services import bypass_pin
from app.services import atak_config
from app.services import data_packages as data_package_service
from app.services import import_jobs
from app.services import tak_gov
from app.services import tak_gov_link
from app.services import app_groups as app_group_service
from app.services import storefronts as storefront_service
from app.services.app_sources import repos as app_repos
from app.services import commands as command_service
from app.services import content_admin
from app.services import custom_attributes as attribute_service
from app.services import files as file_service
from app.services import geocoding
from app.services import guides as guide_service
from app.services import reports as report_service
from app.services import settings_store
from app.services import device_identity
from app.services import device_logs as log_service
from app.services import locations as location_service
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
    reveal_secret,
    token_for_group,
    revoke_device_certificates,
    revoke_token,
)

router = APIRouter(tags=["admin-ui"], include_in_schema=False)

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
_TEMPLATES.env.filters["pretty_json"] = lambda value: json.dumps(value, indent=2, sort_keys=True)


def _spec_rows(
    spec: Any,
    policy_type: str | None = None,
    names: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    """A policy spec as flat label/value rows for a readable, no-JSON summary.

    Given the policy type, field labels come from the spec's own ``title`` (the
    same text the editor shows); otherwise the raw key is de-underscored.
    """
    # Referenced ids rendered as the thing they name. A wallpaper summary reading
    # "45cc5418-3aae-…" tells an operator nothing about which picture it is.
    names = names or {}
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
        return names.get(str(value), str(value))

    for key, value in (spec or {}).items():
        rows.append(
            {"label": labels.get(key, key.replace("_", " ")), "value": render(value)}
        )
    return rows


_TEMPLATES.env.filters["spec_rows"] = _spec_rows
# A filter, not context: Jinja macros do not inherit the page context, and the
# version picker lives inside one. Parsing stays in Python either way.
_TEMPLATES.env.filters["atak_target"] = atak_compat.plugin_target
#: ATAK's own versionName -> the line a plugin would have to target (W141).
_TEMPLATES.env.filters["atak_line_of"] = atak_compat.atak_line
_TEMPLATES.env.filters["category_label"] = lambda key: (
    creator_catalog.get(key).label if creator_catalog.get(key) else key
)


def _declared_plugin_api(package) -> str | None:
    """The `plugin-api` an uploaded app's deployed build declares, if any (W90).

    ⚠️ **It lives on the *version*, not the package.** Reading `package.plugin_api`
    in a template is not an error — Jinja resolves a missing attribute to
    Undefined, which is falsy — so the plugin marker in the settings picker simply
    never appeared, on a library made almost entirely of plugins.

    Best-effort by design: a build uploaded before `plugin_api` was recorded has
    it NULL until `backfill_plugin_api` runs, and the picker must not imply the
    unmarked apps are the non-plugins.
    """
    # ⚠️ Not `package_service.newest`, which takes a session it does not
    # currently use. A filter has none to give, and passing None would work only
    # until that function grows a query — at which point it would fail inside a
    # template render, which is the worst place to find out.
    if not package.versions:
        return None
    return max(package.versions, key=lambda v: v.version_code).plugin_api


_TEMPLATES.env.filters["plugin_api"] = _declared_plugin_api


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
    # The running revision, for the footer (W102). Injected here for the same
    # reason the CSRF token is: every page needs it, and a page that forgot would
    # simply show nothing rather than fail, so nobody would notice.
    context["build"] = build_info()
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
@router.get("/fleet", response_class=HTMLResponse)
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
        # The Groups tab (W122; tags removed in W123).
        group_rows=_group_rows(session),
        # Computed here rather than in the template: "enrolled but never arrived"
        # is a judgement about how devices fail, not a formatting choice, and it
        # is tested where it lives.
        stalled={
            r.device.id for r in rows if device_health.enrollment_stalled(r.device)
        },
        stalled_reason=device_health.stalled_reason(),
        counts={
            "devices": len(rows),
            "policies": len(list(session.scalars(select(Policy).where(Policy.archived_at.is_(None))))),
            "packages": len(list(session.scalars(select(AppPackage)))),
            "files": len(
                list(session.scalars(select(ManagedFile).where(ManagedFile.in_library)))
            ),
        },
    )


#: How far back the history page looks when nobody has said otherwise. Matches
#: the reference portal, and is the window that answers "where has it been today".
_DEFAULT_HISTORY_HOURS = 48


def _parse_day(value: str | None) -> datetime | None:
    """A `type=date` value at midnight UTC, or None if it is absent or malformed.

    ⚠️ Malformed reads as absent rather than as an error. The field is a date
    picker; anything else in it came from a hand-edited URL, and falling back to
    the default window is more useful than a 422 on a read-only page.
    """
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc)


@router.get("/devices/{device_id}/location-history", response_class=HTMLResponse)
def location_history(
    device_id: uuid.UUID,
    request: Request,
    from_mode: str = "now",
    from_date: str | None = None,
    to_date: str | None = None,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> HTMLResponse:
    """Where a device has been, over a window that runs backwards from `From`."""
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")

    now = datetime.now(timezone.utc)
    newest = now if from_mode != "date" else (_parse_day(from_date) or now)
    oldest = _parse_day(to_date) or (now - timedelta(hours=_DEFAULT_HISTORY_HOURS))

    range_error = None
    if oldest > newest:
        # ⚠️ Refused rather than quietly swapped. Swapping would show a window the
        # operator did not ask for while the form kept displaying what they typed,
        # and they would read the result as the answer to their question.
        range_error = '"To" must be on or before "From".'
        stored: list = []
    else:
        stored = location_service.history(session, device_id, newest=newest, oldest=oldest)

    points = location_service.downsample(stored, now=now)

    return _render(
        request,
        "location_history.html",
        identity=identity,
        device=device,
        points=points,
        total=len(stored),
        thinned=len(points) < len(stored),
        from_mode="date" if from_mode == "date" else "now",
        from_date=(newest.strftime("%Y-%m-%d")),
        to_date=oldest.strftime("%Y-%m-%d"),
        range_error=range_error,
        map_json=json.dumps(
            {
                **location_service.tile_config(session),
                # Somewhere to point when there is nothing to show. The reference
                # portal uses Denver; this uses the last known position when there
                # is one, which is more useful and no more arbitrary.
                "fallbackLat": points[0].latitude if points else 39.7392,
                "fallbackLon": points[0].longitude if points else -104.9903,
                "points": [
                    {
                        "number": p.number,
                        "latitude": p.latitude,
                        "longitude": p.longitude,
                        "when": p.recorded_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
                    }
                    for p in points
                ],
            }
        ),
    )


@router.get("/devices/{device_id}/location-history.csv")
def location_history_csv(
    device_id: uuid.UUID,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> StreamingResponse:
    """Every stored point for a device, unthinned.

    ⚠️ **Deliberately ignores the range and the downsampling.** The map thins old
    stretches so a year of track is legible; an export that did the same would
    hand someone a file they believe is complete and is not. The button says "all
    history" and this is what makes that true.
    """
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")

    def rows():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            ["number", "recorded_at_utc", "received_at_utc", "latitude",
             "longitude", "accuracy_m", "provider", "source"]
        )
        yield buffer.getvalue()

        for index, point in enumerate(location_service.history(session, device_id), start=1):
            buffer.seek(0)
            buffer.truncate(0)
            writer.writerow([
                index,
                point.recorded_at.strftime("%Y-%m-%d %H:%M:%S"),
                point.received_at.strftime("%Y-%m-%d %H:%M:%S"),
                f"{point.latitude:.6f}",
                f"{point.longitude:.6f}",
                "" if point.accuracy_m is None else f"{point.accuracy_m:.1f}",
                point.provider or "",
                point.source.value,
            ])
            yield buffer.getvalue()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    name = f"location-history-{device.serial_number}-{stamp}.csv"
    return StreamingResponse(
        rows(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
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
    considered = _annotate_removability(session, device, payload.get("considered", []))

    return _render(
        request,
        "device_detail.html",
        identity=identity,
        device=device,
        considered=considered,
        values=payload.get("values", {}),
        provenance=payload.get("provenance", {}),
        conflicts=_name_storefronts_in(session, payload.get("conflicts", [])),
        apps=payload.get("apps", []),
        atak_mismatches={m.package_name: m.message for m in atak_compat.for_device(session, device)},
        files=payload.get("files", {"required": [], "available": []}),
        log_bundles=log_service.list_for_device(session, device_id),
        pending_log_request=_has_open_log_request(session, device_id),
        identifiers=device_identity.for_device(session, device_id),
        attributes=attribute_service.values_for_device(session, device_id),
        disenrolling=_disenroll_pending(session, device),
        **_location_panel(session, device, payload.get("values", {})),
    )


def _disenroll_pending(session: Session, device: Device):
    """The reset already on its way, if any — so the page says so rather than
    offering the button again."""
    from app.services import disenroll

    return disenroll.pending(session, device)


def _describe_age(delta: timedelta) -> str:
    """A fix's age in words. Rounded down, because a position is never fresher
    than it is."""
    seconds = int(delta.total_seconds())
    if seconds < 90:
        return "just now" if seconds < 30 else f"{seconds} seconds ago"
    minutes = seconds // 60
    if minutes < 90:
        return f"{minutes} minutes ago"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} hours ago"
    return f"{hours // 24} days ago"


#: A fix older than this is called out on the page. Chosen against the check-in
#: interval rather than picked: a device reporting normally delivers within a
#: cycle or two, so beyond this something is off — tracking disabled, no GPS
#: indoors, or a device that has stopped talking.
_STALE_AFTER = timedelta(hours=1)


def _location_panel(session: Session, device: Device, values: dict) -> dict:
    """What the device page needs to draw a position, or explain its absence."""
    latest = location_service.latest(session, device.id)
    tracking = (values.get("TRACKING_FENCING") or {}).get("reporting_interval_minutes")

    panel: dict[str, object] = {
        "latest_location": latest,
        "tracking_interval": tracking or 0,
        "location_age": "",
        "location_stale": False,
        "latest_map_json": "{}",
    }
    if latest is None:
        return panel

    age = datetime.now(timezone.utc) - latest.recorded_at.replace(
        tzinfo=latest.recorded_at.tzinfo or timezone.utc
    )
    panel["location_age"] = _describe_age(age)
    panel["location_stale"] = age > _STALE_AFTER
    panel["latest_map_json"] = json.dumps(
        {
            **location_service.tile_config(session),
            "latitude": latest.latitude,
            "longitude": latest.longitude,
            "accuracyM": latest.accuracy_m,
            "label": device.name or device.serial_number,
        }
    )
    return panel


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


#: The one-shot actions the device page offers, and what each is called there.
#:
#: ⚠️ An allowlist, not "any CommandType the caller names". These routes are
#: reached by a form post from a page an admin is already on; letting the path
#: segment select any command in the enum would put `wipe` one crafted URL away
#: from a button that says "Play sound".
_DEVICE_ACTIONS: dict[str, tuple[CommandType, str]] = {
    "ping": (CommandType.PING, "The device will sound an alarm for 30 seconds."),
    "lock": (CommandType.LOCK, "The device will lock its screen."),
    "locate": (CommandType.LOCATE, "The device will report its position."),
}


@router.get("/policies/geocode")
def geocode_lookup(
    q: str = "",
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> JSONResponse:
    """Turn a typed address into candidate coordinates, for the fence editor.

    ⚠️ **The browser calls this, not the geocoder.** Proxying it here means the
    operator's own address is never disclosed to a third-party service — only this
    server's. It also keeps the endpoint a deployment setting rather than
    something baked into a script the browser fetched.

    Admin-only, like every other console route: this spends a shared, rate-limited
    third-party service, and an open proxy for it is not something to leave lying
    around.
    """
    try:
        places = geocoding.search(session, q)
    except geocoding.GeocodingError as exc:
        # 200 with an error field, not a 5xx: the editor shows this to the
        # operator beside the box they typed in, and a failed lookup is an
        # ordinary outcome rather than a broken page.
        return JSONResponse({"error": str(exc), "results": []})

    return JSONResponse(
        {
            "results": [
                {"label": p.label, "latitude": p.latitude, "longitude": p.longitude}
                for p in places
            ]
        }
    )


@router.get("/policies/geocode/suggest")
def geocode_suggest(
    q: str = "",
    lat: float | None = None,
    lon: float | None = None,
    bbox: str = "",
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> JSONResponse:
    """Address suggestions for a partial string (W110).

    ⚠️ **Never raises, never 500s.** This is called while somebody is typing, so
    a failure has to be silence rather than an error — the Find button is where a
    broken lookup gets reported, once, where it can be read.

    `lat`/`lon` bias results toward what the operator is looking at, which is the
    difference between "Cor" meaning Corona, California and meaning a global list.
    """
    near = (lat, lon) if lat is not None and lon is not None else None

    # A malformed box is dropped rather than refused. This is a convenience
    # endpoint called while somebody types, and an unbounded search is a
    # perfectly good answer to give them.
    bounds = None
    parts = [part for part in bbox.split(",") if part.strip()]
    if len(parts) == 4:
        try:
            bounds = tuple(float(part) for part in parts)
        except ValueError:
            bounds = None

    places = geocoding.suggest(session, q, near=near, bbox=bounds)
    return JSONResponse(
        {
            "results": [
                {"label": p.label, "latitude": p.latitude, "longitude": p.longitude}
                for p in places
            ]
        }
    )


@router.post("/devices/{device_id}/action/{action}")
def device_action_form(
    device_id: uuid.UUID,
    action: str,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    """Queue one of the device page's one-shot actions (W107).

    The doorbell (F3) wakes a parked device in the same second, so a ping is
    normally sounding within a few seconds rather than at the next poll.
    """
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")

    chosen = _DEVICE_ACTIONS.get(action)
    if chosen is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown action")

    command_type, _ = chosen
    command_service.enqueue(session, device, command_type=command_type)
    session.commit()
    return _redirect(f"/devices/{device_id}?action={action}#actions")


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


def _annotate_removability(
    session: Session, device: Device, considered: list[dict]
) -> list[dict]:
    """Mark which rows this page may unassign, and say where the rest come from.

    ⚠️ **Only a device-scoped assignment is removable here** (W118). A group or
    tag assignment belongs to the group or the tag, so deleting it would
    unassign the policy from **every device** sharing it — a fleet-wide change
    behind a button that looks like a per-device tidy-up. A profile section is
    not an `Assignment` at all; its id is the synthetic
    `profile:{pa.id}:{section.id}`.

    The other three get an origin string instead, because "where does this come
    from" is what the operator actually needs in order to go and change it.
    """
    ids = []
    for row in considered:
        raw = str(row.get("assignment_id", ""))
        if not raw.startswith("profile:"):
            with suppress(ValueError):
                ids.append(uuid.UUID(raw))

    assignments = {}
    if ids:
        assignments = {
            str(a.id): a
            for a in session.scalars(select(Assignment).where(Assignment.id.in_(ids)))
        }

    out = []
    for row in considered:
        row = dict(row)
        raw = str(row.get("assignment_id", ""))

        if raw.startswith("profile:"):
            row["removable"] = False
            row["origin"] = _profile_origin(session, raw)
            out.append(row)
            continue

        assignment = assignments.get(raw)
        if assignment is None:
            # Resolved from something this lookup cannot see. Never offer to
            # delete a row we could not confirm.
            row["removable"] = False
            row["origin"] = ""
            out.append(row)
            continue

        if assignment.device_id == device.id:
            row["removable"] = True
            row["origin"] = ""
        elif assignment.group_id is not None:
            group = session.get(DeviceGroup, assignment.group_id)
            row["removable"] = False
            row["origin"] = f"via group {group.name}" if group else "via a group"
        else:
            row["removable"] = False
            row["origin"] = ""
        out.append(row)
    return out


def _profile_origin(session: Session, assignment_id: str) -> str:
    """"section of profile X" for a `profile:{pa.id}:{section.id}` row."""
    parts = assignment_id.split(":")
    if len(parts) != 3:
        return "from a profile"
    try:
        pa = session.get(ProfileAssignment, uuid.UUID(parts[1]))
    except ValueError:
        return "from a profile"
    if pa is None:
        return "from a profile"
    profile = session.get(PolicyProfile, pa.profile_id)
    return f"section of profile {profile.name}" if profile else "from a profile"


def _group_or_404(session: Session, group_id: uuid.UUID) -> DeviceGroup:
    group = session.get(DeviceGroup, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "group not found")
    return group


def _group_rows(session: Session) -> list[dict[str, Any]]:
    rows = []
    for c in session.scalars(select(DeviceGroup).order_by(DeviceGroup.name)):
        rows.append(
            {
                "container": c,
                "device_count": len(c.devices),
                "policy_count": session.scalar(
                    select(func.count())
                    .select_from(Assignment)
                    .where(Assignment.group_id == c.id)
                )
                or 0,
            }
        )
    return rows


def _create_group(
    session: Session, name: str, description: str = ""
) -> RedirectResponse:
    label = name.strip()
    if not label:
        return _redirect("/fleet?error=" + _quote("a group needs a name") + "#tab-groups")

    if session.scalar(select(DeviceGroup).where(DeviceGroup.name == label)) is not None:
        # The column is unique, so this would otherwise be an IntegrityError
        # and a 500 rather than a message.
        return _redirect(
            "/fleet?error="
            + _quote(f"a group called {label} already exists")
            + "#tab-groups"
        )

    group = DeviceGroup(name=label, description=description.strip() or None)
    session.add(group)
    session.commit()
    return _redirect(f"/groups/{group.id}")


def _render_group_detail(
    request: Request,
    session: Session,
    identity: AdminIdentity,
    group_id: uuid.UUID,
) -> HTMLResponse:
    """One group or tag: its devices, and what membership actually buys them.

    ⚠️ **The policy list is the point, not decoration.** W118 tells an operator
    that a policy reaching a device comes *"via group Field Tablets"* and cannot
    be removed from the device page. That is only useful advice if the container
    has somewhere to go, and this is it.
    """
    container = _group_or_404(session, group_id)

    member_ids = {d.id for d in container.devices}
    devices = list(session.scalars(select(Device).order_by(Device.serial_number)))

    assignments = list(
        session.scalars(
            select(Assignment)
            .where(Assignment.group_id == container.id)
            .order_by(Assignment.rank.desc())
        )
    )

    # ⚠️ Counted for the delete panel. A token scoped to a group keeps working
    # after the group is deleted and simply stops placing devices in it — the
    # one cascade whose effect is invisible everywhere else.
    token_count = session.scalar(
        select(func.count())
        .select_from(enrollment_token_group)
        .where(enrollment_token_group.c.group_id == container.id)
    ) or 0

    assignable = list(
        session.scalars(
            select(Policy)
            .where(Policy.archived_at.is_(None), Policy.is_template.is_(False))
            .order_by(Policy.name)
        )
    )

    return _render(
        request,
        "group_detail.html",
        identity=identity,
        container=container,
        label="group",
        description=container.description,
        prefix="/groups",
        tab="groups",
        devices=[{"device": d, "member": d.id in member_ids} for d in devices],
        member_count=len(member_ids),
        token_count=token_count,
        assignable=assignable,
        assignments=[
            {
                "assignment": a,
                "policy": a.policy,
                "version": a.pinned_version.version
                if a.pinned_version
                else (
                    a.policy.latest_version.version
                    if a.policy and a.policy.latest_version
                    else None
                ),
            }
            for a in assignments
        ],
    )


def _set_group_devices(
    request: Request, session: Session, group_id: uuid.UUID
) -> RedirectResponse:
    """Replace membership with exactly what was ticked.

    ⚠️ **Replace, not add** — `PUT /groups/{id}/devices` sets the whole list and
    the form mirrors that. An "Add device" button would imply incremental
    semantics the endpoint does not have.

    Delegates to the same `_apply_membership` the API uses, which invalidates
    the effective-policy cache for **both** the devices leaving and the ones
    joining — the mistake W118 made by hand.
    """
    from app.api.routers.inventory import _apply_membership

    container = _group_or_404(session, group_id)

    form = _sync_form(request)
    ids: list[uuid.UUID] = []
    for raw in form.getlist("device_ids"):
        with suppress(ValueError):
            ids.append(uuid.UUID(raw))

    _apply_membership(session, container, ids)
    return _redirect(f"/groups/{group_id}?saved=1")


def _assign_policy_to_group(
    session: Session, group_id: uuid.UUID, policy_id: uuid.UUID, rank: int
) -> RedirectResponse:
    """Assign one policy to this group.

    Delegates to the API's `create_assignment` rather than building the row
    here: that validates the policy, refuses a template, resolves a pinned
    version and invalidates every affected device.
    """
    from app.api.routers.assignments import create_assignment
    from app.api.schemas import AssignmentCreate

    _group_or_404(session, group_id)

    try:
        create_assignment(
            AssignmentCreate(
                policy_id=policy_id, scope="group", target_id=group_id, rank=rank
            ),
            session,
        )
    except HTTPException as exc:
        return _redirect(f"/groups/{group_id}?error=" + _quote(str(exc.detail)))

    return _redirect(f"/groups/{group_id}?assigned=1")


def _remove_group_assignment(
    session: Session, group_id: uuid.UUID, assignment_id: uuid.UUID
) -> RedirectResponse:
    """Unassign a policy from this group.

    ⚠️ **Allowed here, and refused on the device page** (W118). The click changes
    every member either way; the difference is whether the page the operator is
    looking at makes that obvious. Here it does, and the button says how many
    devices it reaches.

    Still checks the assignment really belongs to *this* group, so a
    hand-edited URL cannot reach a device-scoped row from here.
    """
    from app.api.routers.assignments import delete_assignment

    assignment = session.get(Assignment, assignment_id)
    if assignment is None:
        return _redirect(
            f"/groups/{group_id}?error=" + _quote("that assignment no longer exists")
        )

    if assignment.group_id != group_id:
        return _redirect(
            f"/groups/{group_id}?error="
            + _quote("that assignment does not belong to this group")
        )

    name = assignment.policy.name if assignment.policy else "the policy"
    delete_assignment(assignment_id, session)
    return _redirect(f"/groups/{group_id}?unassigned=" + _quote(name))


def _delete_group(
    session: Session, group_id: uuid.UUID, confirm: str
) -> RedirectResponse:
    """Delete a group, and everything that hangs off it.

    ⚠️ **The cascades, one of which is silent.** `device_group.id` is referenced
    with `ondelete="CASCADE"` from membership, `Assignment`, `ProfileAssignment`
    and `enrollment_token_group`. The first three are visible on the page. The fourth is not: a token scoped to the group stays
    live and simply stops placing devices in it, so a tablet enrolled afterwards
    lands without the policy stack and nothing says why. The page counts those
    tokens before asking.

    ⚠️ **Members are captured before the delete, not after.** Once the cascade
    runs the membership rows are gone and there is no way to learn whose
    effective policy just changed — the same ordering the API's
    `delete_assignment` uses.

    Typing the name is the confirmation, as with disenroll: this changes policy
    on every member at once. A single unassign stays a plain click, because
    ceremony should track consequence rather than destructiveness in general.
    """
    container = _group_or_404(session, group_id)

    if confirm.strip() != container.name:
        return _redirect(
            f"/groups/{group_id}?error=" + _quote("type the group name exactly to confirm")
        )

    affected = {d.id for d in container.devices}
    name = container.name
    session.delete(container)
    session.flush()
    eff.invalidate(session, affected)
    session.commit()
    return _redirect("/fleet?deleted=" + _quote(name) + "#tab-groups")


# --------------------------------------------------------------------------- #
# Groups
# --------------------------------------------------------------------------- #


@router.get("/groups", response_class=HTMLResponse)
def groups_page() -> RedirectResponse:
    """The list lives on the Manage page's Groups tab now (W122).

    Kept as a redirect rather than removed: Fleet, the group detail page and
    W121's QR page all link here, and the tab bar reads `#tab-<name>` from the
    hash, so a deep link lands on the right tab.
    """
    return _redirect("/fleet#tab-groups")


@router.post("/groups")
def create_group_form(
    name: str = Form(...),
    description: str = Form(default=""),
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    return _create_group(session, name, description)


@router.get("/groups/{group_id}", response_class=HTMLResponse)
def group_detail_page(
    group_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> HTMLResponse:
    return _render_group_detail(request, session, identity, group_id)


@router.post("/groups/{group_id}/devices")
def set_group_devices_form(
    group_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    return _set_group_devices(request, session, group_id)


@router.post("/groups/{group_id}/assignments")
def assign_policy_to_group_form(
    group_id: uuid.UUID,
    policy_id: uuid.UUID = Form(...),
    rank: int = Form(default=0),
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    return _assign_policy_to_group(session, group_id, policy_id, rank)


@router.post("/groups/{group_id}/assignments/{assignment_id}/remove")
def remove_group_assignment_form(
    group_id: uuid.UUID,
    assignment_id: uuid.UUID,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    return _remove_group_assignment(session, group_id, assignment_id)


@router.post("/groups/{group_id}/delete")
def delete_group_form(
    group_id: uuid.UUID,
    confirm: str = Form(default=""),
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    return _delete_group(session, group_id, confirm)


@router.post("/devices/{device_id}/assignments/{assignment_id}/remove")
def remove_device_assignment(
    device_id: uuid.UUID,
    assignment_id: str,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    """Unassign one policy from this device (W118).

    ⚠️ **The scope check is here, not only in the template.** A hidden button is
    not a control. This refuses anything that is not a device-scoped assignment
    pointing at *this* device, for the reason `_DEVICE_ACTIONS` is an allowlist:
    otherwise a hand-edited URL could delete a **group** assignment from here and
    silently unassign the policy across every device in that group.

    No confirmation step, deliberately — unlike disenroll two sections down.
    Re-assigning restores it and the device converges on the next check-in, so
    ceremony here would be friction without a payoff.
    """
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")

    try:
        parsed = uuid.UUID(assignment_id)
    except ValueError:
        # A profile section id, or junk. Neither names a row we may delete.
        return _redirect(
            f"/devices/{device_id}?error="
            + _quote("that policy does not come from a direct assignment")
        )

    assignment = session.get(Assignment, parsed)
    if assignment is None:
        return _redirect(
            f"/devices/{device_id}?error=" + _quote("that assignment no longer exists")
        )

    if assignment.device_id != device.id:
        return _redirect(
            f"/devices/{device_id}?error="
            + _quote(
                "that policy is inherited from a group or tag; "
                "change it there rather than on this device"
            )
        )

    name = assignment.policy.name if assignment.policy else "the policy"

    # ⚠️ Resolve the affected devices *before* the row is gone, then invalidate —
    # the same three steps the API's delete takes. A first version deleted the
    # row and committed, and the device went on serving a stale cached effective
    # policy: the row vanished from this table and nothing reached the tablet.
    # Caught by the test that checks the desired state changes rather than
    # checking the row disappeared.
    affected = eff.devices_targeted_by(session, assignment)
    session.delete(assignment)
    session.flush()
    eff.invalidate(session, affected)
    session.commit()
    return _redirect(f"/devices/{device_id}?unassigned=" + _quote(name))


@router.post("/devices/{device_id}/disenroll")
def disenroll_device_form(
    device_id: uuid.UUID,
    confirm: str = Form(default=""),
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    """Factory reset the device and forget it (W104).

    ⚠️ **Typing the serial is the confirmation.** This erases a tablet, and a
    dialog anyone can dismiss by reflex is not proportionate to that — the
    operator has to name the specific device they mean, which cannot be done by
    accident on the wrong row.

    The record is *not* removed here. It goes when the device acknowledges the
    reset, which is the only moment the server can know the instruction arrived.
    """
    from app.services import disenroll

    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")

    if confirm.strip() != device.serial_number:
        return _redirect(
            f"/devices/{device_id}?error="
            + _quote("type the serial number exactly to confirm the factory reset")
        )

    disenroll.request(session, device)
    session.commit()
    return _redirect(f"/devices/{device_id}?disenrolling=1")


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
    return _redirect("/fleet")


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
        file_names=_managed_file_names(session),
    )


def _sections_of(profile) -> dict:
    """`{category key: section}` for a profile, or empty for the creator."""
    if profile is None:
        return {}
    return {section.profile_section: section for section in profile.sections}


def _category_warnings(
    session: Session | None,
    storage: ArtifactStorage | None,
    category,
    spec: dict,
    whole_spec: dict,
) -> list[str]:
    """Anything about this category the operator should know *before* publishing.

    ⚠️ **This is where an ATAK Config problem is allowed to be loud.** The same
    checks run again at check-in, inside the device's own request, where they can
    only degrade to "no ATAK configuration" — a device must not fail to check in
    because a policy is wrong. That makes the console the only place the operator
    ever finds out, so the warning has to actually appear here.
    """
    if category.policy_type != "ATAK_CONFIG" or not spec:
        return []
    if session is None or storage is None:
        return []
    return atak_config.render(session, storage, whole_spec).warnings


def _catalog_view(
    profile=None,
    session: Session | None = None,
    storage: ArtifactStorage | None = None,
) -> list[dict[str, Any]]:
    """The creator/editor category rail (W12): each wired category with its
    sub-pages (one per ui_group), a per-sub-page 'has data' flag, and the
    section's current spec."""
    view: list[dict[str, Any]] = []
    # ⚠️ Every section, not just this one. Which ATAK build the settings are for
    # is settled by the policy's *own* required apps, so the ATAK Config category
    # cannot be judged without seeing App Management beside it.
    whole_spec = {
        creator_catalog.get(key).policy_type: section.latest_version.spec
        for key, section in _sections_of(profile).items()
        if creator_catalog.get(key) and section.latest_version
    }
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
                "warnings": _category_warnings(
                    session, storage, category, spec, whole_spec
                ),
                # Order is the category's own declaration (D94), which is why
                # a stub can name the sub-page it follows: "Plugin behavior" sits
                # at the top of ATAK Config and "Geofencing" sits *below* Device
                # location tracking, both because that is how they were asked for.
                "pages": _ordered_sub_pages(category, pages, managed),
                "section": section,
                "spec": spec,
                "has_data": bool(spec),
            }
        )
    return view


def _ordered_sub_pages(category, pages, managed: set[str]) -> list[dict]:
    """A category's sub-pages, stubs placed where the category says they go.

    A stub with no ``after`` leads, which is the long-standing behaviour and what
    ATAK Config wants. A stub naming a real sub-page follows it — that is how
    Geofencing sits below Device location tracking rather than above it (W106).

    ⚠️ A stub whose ``after`` names nothing on the page still appears, at the end.
    Silently dropping it would hide a sub-topic an operator was told to expect,
    and a misplaced entry is a far smaller problem than a missing one.
    """
    real = [{"page": p, "has_data": p.slug in managed, "stub": False} for p in pages]

    leading = [s for s in category.stub_pages if s.after is None]
    following: dict[str, list] = {}
    for stub in category.stub_pages:
        if stub.after is not None:
            following.setdefault(stub.after, []).append(stub)

    out = [{"page": s, "has_data": False, "stub": True} for s in leading]
    for entry in real:
        out.append(entry)
        for stub in following.pop(entry["page"].slug, []):
            out.append({"page": stub, "has_data": False, "stub": True})

    # Whatever named a sub-page that is not here, rather than vanishing.
    for orphans in following.values():
        out.extend({"page": s, "has_data": False, "stub": True} for s in orphans)
    return out


def _managed_file_names(session: Session) -> dict[str, str]:
    """id -> display name, so a spec summary shows the picture, not its uuid.

    Deliberately *not* filtered to the library: a wallpaper uploaded inside the
    policy editor (W46) is exactly the case this exists for, and hiding it here
    would put a uuid back on the screen it was written to keep it off.
    """
    return {
        str(managed.id): managed.name
        for managed in session.scalars(select(ManagedFile))
    }


def _form_catalogs(session: Session) -> dict[str, Any]:
    """Uploaded apps and files, for the policy form's list controls."""
    packages = list(session.scalars(select(AppPackage).order_by(AppPackage.package_name)))
    # ⚠️ Partitioned here, not in Jinja (W141). "Is a plugin" is a query — any
    # build declaring a `plugin-api`, or one imported from TAK.gov — and a
    # template that tried to work it out per row would ask the database inside a
    # loop and still get provenance wrong.
    plugin_names = atak_compat.plugin_packages(session)
    return {
        "app_packages": packages,
        # One threaded parameter rather than three: these travel together
        # through `policy_subform` -> `_control` -> `_live_control`, and every
        # extra positional argument is another hop to forget.
        "app_kinds": {
            # Required apps picks from these: ATAK and its plugins have their own
            # section, and offering them here is what the refusals prevent.
            "plain": [
                p for p in packages
                if not atak_compat.is_atak(p.package_name)
                and p.package_name not in plugin_names
            ],
            "atak": [p for p in packages if atak_compat.is_atak(p.package_name)],
            "plugins": [p for p in packages if p.package_name in plugin_names],
        },
        # The shelves an APP_CATALOG policy may hand out (W140).
        "storefronts": storefront_service.list_all(session),
        # Library only: a policy-editor upload must not show up in the FILES
        # picker as something to deploy to a device (W46).
        "managed_files": list(
            session.scalars(
                select(ManagedFile).where(ManagedFile.in_library).order_by(ManagedFile.name)
            )
        ),
        "file_names": _managed_file_names(session),
        # The geofence picker's map source, resolved the same way every other map
        # on the console resolves it, so one setting governs all of them (W109).
        "geofence_tiles": json.dumps(location_service.tile_config(session)),
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
    storage: ArtifactStorage = Depends(get_storage),
    identity: AdminIdentity = Depends(admin_required),
) -> HTMLResponse:
    """The guided profile creator: pick categories, fill the wired ones (DW5)."""
    return _render(
        request,
        "profile_editor.html",
        identity=identity,
        mode="new",
        profile=None,
        catalog=_catalog_view(session=session, storage=storage),
        app_groups=_app_group_hints(session),
        **_form_catalogs(session),
    )


@router.get("/policies/app-activities")
def app_activities(
    package: str,
    session: Session = Depends(get_db),
    storage: ArtifactStorage = Depends(get_storage),
    identity: AdminIdentity = Depends(admin_required),
) -> JSONResponse:
    """Activities the app declares, for the kiosk activity picker (W62).

    Read from the APK on demand and memoised by the version, like the
    managed-config scan. The names are facts about the build, so an operator
    picks from what is actually there instead of typing a class from memory.
    """
    key = ("activities", package)
    cached = _APP_CONFIG_SCANS.get(key)
    if cached is None:
        cached = package_service.declared_activities(session, storage, package)
        _APP_CONFIG_SCANS[key] = cached
        if len(_APP_CONFIG_SCANS) > _APP_CONFIG_SCAN_LIMIT:
            _APP_CONFIG_SCANS.popitem(last=False)
    else:
        _APP_CONFIG_SCANS.move_to_end(key)

    return JSONResponse({"package_name": package, "activities": cached})


def _pref_schema_payload(schema, package_name: str, warnings: list[str]) -> dict:
    """One scanned APK's settings, in the shape the editor's table reads."""
    return {
        "package_name": package_name,
        "preference_group": schema.preference_group if schema else None,
        "sections": [
            {
                "title": section.title,
                "fields": [
                    {
                        "key": f.key,
                        "label": f.label,
                        "summary": f.summary,
                        "control": f.control,
                        "default": f.default,
                        # The app's own option list, when it resolved. Empty means
                        # free text — an empty dropdown offers nothing at all.
                        "options": [{"label": o.label, "value": o.value} for o in f.options],
                    }
                    for f in section.fields
                ],
            }
            for screen in (schema.screens if schema else ())
            for section in screen.sections
        ],
        "warnings": warnings,
    }


@router.get("/policies/pref-schema")
def pref_schema(
    package: str | None = None,
    session: Session = Depends(get_db),
    storage: ArtifactStorage = Depends(get_storage),
    identity: AdminIdentity = Depends(admin_required),
) -> JSONResponse:
    """The settings an ATAK build — or one of its plugins — declares (W90).

    One endpoint for both tables. With no `package` it answers for the ATAK build
    in the library, which is the core-settings case; with one it answers for that
    plugin. The two differ only in which APK is scanned, and giving them separate
    routes would mean two copies of the same shaping code drifting apart.

    ⚠️ **Warnings are part of the answer, not an error.** "No ATAK build is
    uploaded" and "this plugin declares nothing" are both ordinary states an
    operator needs to read on the page — returning 404 for them would put the
    explanation in a console nobody has open.
    """
    if package is None:
        candidates = atak_config.atak_packages(session)
        if not candidates:
            return JSONResponse(
                _pref_schema_payload(
                    None,
                    "",
                    [
                        "No ATAK build is in the app library, so there are no "
                        "settings to show. Upload one from the Apps section."
                    ],
                )
            )
        if len(candidates) > 1:
            names = ", ".join(p.package_name for p in candidates)
            return JSONResponse(
                _pref_schema_payload(
                    None,
                    "",
                    [
                        f"The library holds more than one ATAK build ({names}). "
                        f"Add the one this policy targets to its required apps, "
                        f"so its settings can be read."
                    ],
                )
            )
        found = candidates[0]
    else:
        found = session.scalar(
            select(AppPackage).where(AppPackage.package_name == package)
        )
        if found is None:
            return JSONResponse(
                {"error": f"{package} is not an uploaded app"}, status_code=404
            )

    schema = atak_config.schema_for(session, storage, found)
    warnings: list[str] = []
    if schema is None:
        warnings.append(
            f"{found.package_name} has no published build to read settings from."
        )
    elif not schema.declares_any:
        warnings.append(
            f"{found.package_name} declares no settings in its resources. Only "
            f"what an app puts in res/xml can be read — settings it writes from "
            f"code, or keeps in its own store, are invisible here."
        )

    return JSONResponse(_pref_schema_payload(schema, found.package_name, warnings))


@router.get("/policies/app-config-schema")
def app_config_schema(
    package: str,
    session: Session = Depends(get_db),
    storage: ArtifactStorage = Depends(get_storage),
    identity: AdminIdentity = Depends(admin_required),
) -> JSONResponse:
    """The keys an app declares, for the editor's Add-configuration frame (W49)."""
    found = session.scalar(select(AppPackage).where(AppPackage.package_name == package))
    if found is None:
        return JSONResponse({"error": f"{package} is not an uploaded app"}, status_code=404)

    declared = _declared_app_config(session, storage, found)
    if declared is None or not declared.declares_any:
        return JSONResponse(
            {
                "package_name": package,
                "keys": [],
                # Said plainly: an app with no declared schema is not a failure of
                # this console, and the operator should not go hunting for one.
                "note": "this build declares no managed configuration",
            }
        )

    return JSONResponse(
        {
            "package_name": package,
            "keys": [
                {
                    "key": k.key,
                    "label": k.label,
                    "description": k.description,
                    "control": k.control,
                    "default": k.default,
                    "unsupported_reason": k.unsupported_reason,
                    # The app's own option list, when it could be resolved (W54).
                    # Empty means "free text" — the editor must not render an
                    # empty dropdown, which would offer nothing at all.
                    "options": [
                        {"label": o.label, "value": o.value} for o in k.options
                    ],
                }
                for k in declared.keys
            ],
        }
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
    storage: ArtifactStorage = Depends(get_storage),
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
    }
    return _render(
        request,
        "profile_editor.html",
        identity=identity,
        mode="edit",
        profile=profile,
        catalog=_catalog_view(profile, session=session, storage=storage),
        app_groups=_app_group_hints(session),
        **_form_catalogs(session),
        devices=list(session.scalars(select(Device).order_by(Device.serial_number))),
        groups=list(session.scalars(select(DeviceGroup).order_by(DeviceGroup.name))),
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
        # ⚠️ Every upsert first, then every removal — not category by category.
        # Catalog order puts Password before Tracking and fencing, so a single
        # save that both clears the Password section *and* releases the geofence
        # that needed it would delete the section while the fence still demanded
        # one, and refuse a change whose end state is perfectly legal. Writing
        # what is kept before deleting what is not makes the check see the state
        # the operator is actually asking for.
        parsed_by_category = {
            category: form_parse.parse_form(category.policy_type, form)
            for category in creator_catalog.wired_categories()
        }
        for category, parsed in parsed_by_category.items():
            if parsed:
                profile_service.upsert_section(session, profile, category.key, parsed, published_by=who)
        for category, parsed in parsed_by_category.items():
            if not parsed:
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
    try:
        profile_service.remove_section(session, profile, category_key)
        session.commit()
    except profile_service.ProfileError as exc:
        # ⚠️ This is the button an operator uses to delete the Password tab, and
        # it is the one path that did not report a refusal — it would have 500'd
        # on the very check that exists to protect a geofence lock.
        session.rollback()
        return _redirect(f"/profiles/{profile_id}?error={_quote(str(exc))}#cat-{category_key}")
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


@router.post("/profiles/{profile_id}/delete")
def delete_profile_form(
    profile_id: uuid.UUID,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    """Destroy an archived policy permanently. Refused unless it is archived."""
    profile = profile_service.get_profile(session, profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")
    try:
        profile_service.delete(session, profile)
    except profile_service.ProfileError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    session.commit()
    return _redirect("/policies#tab-archived")


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

    # Needs the library, so it cannot live on the spec with its ATAK-by-name
    # sibling (W141).
    misplaced = atak_compat.misplaced_plugins(session, validated)
    if misplaced:
        return _redirect(
            f"/policies/new/single?error={_quote(atak_compat.refusal_for(misplaced))}"
        )

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


@router.post("/policies/{policy_id}/delete")
def delete_policy_form(
    policy_id: uuid.UUID,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    """Destroy an archived policy and its version history permanently.

    Archiving is the normal answer (D20); this is for policies that never reached
    a device and whose history answers nothing. Refused unless already archived,
    which is what makes it two deliberate acts.
    """
    try:
        policy_admin.delete(session, policy_id)
    except policy_admin.PolicyAdminError as exc:
        status_code = (
            status.HTTP_404_NOT_FOUND
            if str(exc) == "policy not found"
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code, str(exc)) from exc
    session.commit()
    return _redirect("/policies#tab-archived")


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

    misplaced = atak_compat.misplaced_plugins(session, validated)
    if misplaced:
        return _redirect(
            f"/policies/{policy_id}?error={_quote(atak_compat.refusal_for(misplaced))}"
        )

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


@router.get("/enrollment/qr")
def generate_qr_get() -> RedirectResponse:
    """A GET here means something turned the POST back into a navigation.

    ⚠️ **This is the only POST route that renders a page**, so its URL stays in
    the address bar afterwards — and anything that replays that URL arrives as a
    GET. Observed live: an Authentik session lapsed mid-form, the edge sent the
    operator through the outpost, and they came back to a POST-only path. The
    app answered `{"detail": "Method Not Allowed"}` as JSON, which is not a
    sentence anybody can act on, in the middle of enrolling a device.

    ⚠️ **A redirect, not a fresh QR.** Minting issues a signed short-lived
    secret, and a GET that mints would hand one out to a reload, a bookmark or a
    browser prefetch. The Wi-Fi details are not carried over either: a password
    in a query string would be written to history and to every proxy log between
    here and the browser.
    """
    return _redirect("/enrollment")


@router.post("/enrollment/qr", response_class=HTMLResponse)
def generate_qr(
    request: Request,
    wifi_ssid: str = Form(default=""),
    wifi_password: str = Form(default=""),
    wifi_security: str = Form(default="WPA"),
    group_id: str = Form(default=""),
    persistent: bool = Form(default=False),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    storage: ArtifactStorage = Depends(get_storage),
    guard: EnrollmentQrGuard = Depends(get_enrollment_qr_guard),
    vault: TokenVault = Depends(get_token_vault),
    identity: AdminIdentity = Depends(admin_required),
) -> HTMLResponse:
    """Mint a fresh 15-minute QR, optionally scoped to a group (W121).

    Also what the Wi-Fi form on the QR page itself submits to: there is no
    per-QR row to re-render with credentials added, so embedding Wi-Fi simply
    mints a new secret with the credentials baked in. The one just displayed
    keeps working until its own 15 minutes elapse — nothing revokes it.

    ⚠️ **A group makes this resolve to a different token, not a different QR
    format.** The signed derivative carries only a token id, and the enrolment
    path already applies whatever groups that token is scoped to — so picking a
    group means issuing against the group's standing token instead of the
    primary. Nothing about the QR, the signature or enrolment changes.
    """
    group = None
    if group_id.strip():
        with suppress(ValueError):
            group = session.get(DeviceGroup, uuid.UUID(group_id.strip()))

    return _render_primary_qr(
        request, session, settings, storage, guard, identity,
        wifi_ssid=wifi_ssid.strip() or None,
        wifi_password=wifi_password or None,
        wifi_security=wifi_security,
        group=group,
        vault=vault,
        persistent=persistent,
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
    group: DeviceGroup | None = None,
    vault: TokenVault | None = None,
    persistent: bool = False,
) -> HTMLResponse:
    context: dict[str, Any] = {
        "primary": None,
        "wifi_ssid": wifi_ssid,
        "wifi_security": wifi_security,
        # ⚠️ Named beside the code. A QR is a picture and says nothing about
        # what it will do; one that silently enrols into the wrong group is the
        # failure this feature could most easily introduce.
        "group": group,
        "groups": list(
            session.scalars(select(DeviceGroup).order_by(DeviceGroup.name))
        ),
        "qr_svg": None,
        "payload": None,
        "secret": None,
        "qr_expires_at": None,
        # ⚠️ Seconds remaining, not a wall-clock instant. The countdown runs in a
        # browser whose clock the server does not control, and one a few minutes
        # off would show a confidently wrong time to the person holding the
        # tablet. Counting down from a duration is immune to that; the only error
        # is the page load itself.
        "qr_expires_in": None,
        # ⚠️ Drives what the page *says*, and the page saying the wrong thing is
        # the real hazard here: a QR that outlives the room it was shown in,
        # labelled with a countdown, is how a credential leaks without anyone
        # deciding to leak it.
        "persistent": persistent,
        "problem": None,
    }

    try:
        if group is not None:
            token = token_for_group(session, group, vault=vault)
            session.commit()
            primary = token
        else:
            primary = get_primary_token(session)
            if primary is None:
                raise EnrollmentError("no active enrollment token; create one first")

        if persistent:
            # ⚠️ The token's **own** secret, not a derivative (W137). That is
            # what makes the picture outlive the fifteen-minute window, and it
            # is also why re-rendering produces an identical QR rather than
            # another credential nobody can count.
            secret = reveal_secret(primary, vault) if vault is not None else None
            if secret is None:
                raise EnrollmentError(
                    "this token's secret cannot be recovered, so a persistent QR "
                    "cannot be made for it. Retire it and create a new one, which "
                    "will be sealed and can be shown again."
                )
        elif group is not None:
            secret = guard.issue(primary.id)
        else:
            primary, secret = mint_qr_secret(session, guard)
    except EnrollmentError as exc:
        context["problem"] = str(exc)
        return _render(request, "token_qr.html", identity=identity, **context)
    context["primary"] = primary

    _agent = package_service.agent_build_facts(
        session, storage, settings.agent_package_name
    )
    try:
        payload = provisioning.qr_payload(
            settings,
            secret,
            wifi_ssid=wifi_ssid,
            wifi_password=wifi_password,
            wifi_security=wifi_security,
            declared_receivers=_agent.receivers if _agent else None,
            uploaded_checksum=_agent.signature_checksum if _agent else None,
        )
    except provisioning.ProvisioningError as exc:
        context["problem"] = str(exc)
        return _render(request, "token_qr.html", identity=identity, **context)

    session.commit()
    context["payload"] = payload
    context["secret"] = secret
    if not persistent:
        context["qr_expires_at"] = datetime.now(timezone.utc) + timedelta(
            seconds=settings.enrollment_qr_ttl_seconds
        )
        context["qr_expires_in"] = settings.enrollment_qr_ttl_seconds
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


@router.get("/apps/versions/{version_id}/download")
def download_app_version(
    version_id: uuid.UUID,
    session: Session = Depends(get_db),
    storage: ArtifactStorage = Depends(get_storage),
    identity: AdminIdentity = Depends(admin_required),
) -> Response:
    """Hand the operator the bytes this version is made of (W128).

    ⚠️ **A version is not always one file.** A split app is several — Chrome
    arrives from Play as four — and serving only the base would hand back
    something Android refuses to install as `INSTALL_FAILED_MISSING_SPLIT`,
    while looking like a successful download. So one part is served as the APK
    it is, and several are zipped into the `.xapk` shape `inspect_bundle`
    already reads on the way back in. What comes out can be uploaded again.

    ⚠️ **Streamed from the artifact store, not read into memory.** These run to
    hundreds of megabytes; `collect_output` builds bundles in memory during an
    import because it must hash them, but a download has no such excuse.
    """
    version = session.get(AppPackageVersion, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "version not found")

    package = session.get(AppPackage, version.package_id)
    stem = f"{package.package_name}-{version.version_code}" if package else str(version_id)
    parts = sorted(version.files, key=lambda f: (f.role is not PartRole.BASE, f.file_name))

    if not parts:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "this version has no stored files"
        )

    if len(parts) == 1:
        part = parts[0]
        try:
            handle = storage.open(part.artifact_sha256)
        except Exception as exc:  # ArtifactNotFound and friends
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "the stored file is missing"
            ) from exc
        return StreamingResponse(
            handle,
            media_type="application/vnd.android.package-archive",
            headers={
                "Content-Disposition": f'attachment; filename="{stem}.apk"',
                "Content-Length": str(part.artifact.size_bytes)
                if part.artifact and part.artifact.size_bytes
                else "",
            },
        )

    # ⚠️ Assembled on disk, not streamed out of a BytesIO that gets truncated
    # between parts. A first version did exactly that, and `zipfile` records
    # member offsets from `fp.tell()` — resetting the buffer made every offset
    # in the central directory wrong. The archive still listed its names, so it
    # looked fine; it only failed when something tried to *read* a member back.
    # Caught by the round-trip test rather than by the one that opened it.
    #
    # ZIP_STORED because every part is already a compressed archive: deflating
    # again costs CPU over hundreds of megabytes and saves close to nothing.
    spool = tempfile.NamedTemporaryFile(suffix=".xapk", delete=False)
    try:
        with zipfile.ZipFile(spool, "w", zipfile.ZIP_STORED) as archive:
            for part in parts:
                with storage.open(part.artifact_sha256) as handle:
                    with archive.open(part.file_name, "w") as member:
                        shutil.copyfileobj(handle, member)
        spool.close()
    except Exception:
        spool.close()
        os.unlink(spool.name)
        raise

    def stream() -> Iterator[bytes]:
        try:
            with open(spool.name, "rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    yield chunk
        finally:
            os.unlink(spool.name)

    return StreamingResponse(
        stream(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{stem}.xapk"',
            "Content-Length": str(os.path.getsize(spool.name)),
        },
    )


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
        storefronts=storefront_service.list_all(session),
        groups=app_group_service.list_groups(session),
        tpc=_tpc_panel(request, session, vault),
        # Only the sources the 3rd party bar actually searches. Google Play has
        # its own tab (W101), and listing it here would promise a search this
        # panel does not perform.
        repo_sources=[r for r in app_repos.KNOWN if r.unified],
        # Whether Google Play can be searched at all. The panel offers no search
        # box without it: the request would fail at the credential and report
        # something that reads like Play being down (W145).
        googleplay=_googleplay_panel(session),
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


#: Declared-configuration scans, keyed by the base APK's content hash.
#:
#: ⚠️ Caches the **result**, never the APK bytes — a previous `lru_cache` over
#: bytes was removed for pinning more than a gigabyte. The result is a few
#: hundred small objects, and a build is immutable at its hash, so it cannot go
#: stale. Bounded, because an operator's library is not.
_APP_CONFIG_SCANS: OrderedDict[tuple[str, str], object] = OrderedDict()
_APP_CONFIG_SCAN_LIMIT = 32


def _declared_app_config(session: Session, storage: ArtifactStorage, package: AppPackage):
    """The managed configuration a package's newest build declares.

    Scanned from the APK rather than kept in a column, so it cannot drift from the
    build it describes — but memoised per artifact hash.

    This used to scan on every request, justified by "a full scan of a 20 MB APK
    measures ~20 ms". W54 invalidated that: `discover` now parses `resources.arsc`
    first, taking Outlook from 0.13 s to 1.40 s and ~186 MB of transient heap **per
    request** — and the package picker fires one request per arrow-key press.
    """
    version = package_service.newest(session, package)
    if version is None:
        return None
    base = next((f for f in version.files if f.role is PartRole.BASE), None)
    if base is None:
        return None

    key = (base.artifact_sha256, package.package_name)
    cached = _APP_CONFIG_SCANS.get(key)
    if cached is not None:
        _APP_CONFIG_SCANS.move_to_end(key)
        return cached

    try:
        with storage.open(base.artifact_sha256) as handle:
            data = handle.read()
    except (FileNotFoundError, OSError):
        return None

    found = app_restrictions.discover(data, package.package_name)
    _APP_CONFIG_SCANS[key] = found
    if len(_APP_CONFIG_SCANS) > _APP_CONFIG_SCAN_LIMIT:
        _APP_CONFIG_SCANS.popitem(last=False)
    return found


@router.post("/policies/image")
def upload_policy_image_form(
    file: UploadFile = File(...),
    session: Session = Depends(get_db),
    storage: ArtifactStorage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
    identity: AdminIdentity = Depends(admin_required),
) -> JSONResponse:
    """Take an image chosen inside a policy editor and hand back its id (W46).

    The operator picking a wallpaper is choosing a picture for *this policy*, not
    publishing an asset to the fleet's Content library — so the file is ingested
    with ``in_library=False`` and never appears there. Everything downstream is
    unchanged: it is an ordinary managed file with a content-addressed artifact,
    and the device cannot tell how it arrived.

    Returns the id rather than redirecting because the policy has not been saved
    yet; the form holds the id until the operator commits the whole policy.
    """
    data = file.file.read()
    if not data:
        return JSONResponse({"error": "the uploaded file is empty"}, status_code=422)
    if len(data) > settings.max_upload_bytes:
        return JSONResponse(
            {"error": f"upload exceeds {settings.max_upload_bytes} bytes"}, status_code=413
        )

    media_type = file.content_type or ""
    if not media_type.startswith("image/"):
        # Refused here rather than on the device, where a wallpaper that is not an
        # image fails as a generic apply error with nothing to act on.
        return JSONResponse(
            {"error": f"expected an image, got {media_type or 'an unknown type'}"},
            status_code=422,
        )

    try:
        managed = file_service.ingest_file(
            session,
            storage,
            data,
            name=(file.filename or "wallpaper").rsplit(".", 1)[0][:255],
            original_filename=file.filename or "wallpaper",
            media_type=media_type,
            in_library=False,
        )
        session.commit()
    except file_service.FileError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    return JSONResponse({"id": str(managed.id), "name": managed.name})


# --------------------------------------------------------------------------- #
# 3rd party app repo (W97)
# --------------------------------------------------------------------------- #


def _repo_source(name: str, settings: Settings, session=None, vault=None):
    """The source by name, built against the on-disk cache.

    `session` and `vault` are needed only by Google Play, which cannot exist
    without a linked account; every other source ignores them.
    """
    from app.services.app_sources import repos

    play = None
    if session is not None and vault is not None:
        from app.services import google_play_link

        play = google_play_link.credentials(session, vault)

    return repos.build(name or "fdroid", Path(str(settings.cache_dir)), play=play)


def _version_row(session: Session, version, preflight) -> dict:
    """One build, as the console needs to show it.

    ⚠️ Every compatibility fact is included even when it is *absent*, because
    "this source does not say" and "it runs anywhere" have to look different on
    the page — the same distinction the `abis` column keeps (W96).
    """
    return {
        "version_code": version.version_code,
        "version_name": version.version_name,
        # The handle the source needs to fetch this build. A versionCode for an
        # index, a version name for APKPure — the console never has to know which.
        "version_key": version.version_key,
        "display_version": version.display_version,
        "size": version.size,
        "abis": list(version.abis) if version.abis is not None else None,
        "min_sdk": version.min_sdk,
        "signer": version.signer_sha256,
        "verifiable": version.verifiable,
        "blocking": preflight.blocking,
        "warnings": preflight.warnings,
    }


@router.get("/apps/repo/search")
def repo_search(
    q: str = "",
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    vault: TokenVault = Depends(get_token_vault),
    identity: AdminIdentity = Depends(admin_required),
) -> JSONResponse:
    """Search every source at once (W98).

    ⚠️ **One failing source must not empty the page.** Each is caught on its own
    and reported beside the results that did arrive — a search that returns
    nothing because APKPure is unreachable, with no explanation, would send an
    operator hunting for an app that F-Droid was holding all along.
    """
    from app.services.app_sources import repos as app_repos
    from app.services.app_sources.base import SourceError

    query = (q or "").strip()
    if not query:
        return JSONResponse({"apps": [], "problems": []})

    rows: list[dict] = []
    problems: list[dict] = []

    # Google Play has its own tab (W101): it needs a linked account, and a row
    # costing a Google credential does not belong beside rows that cost nothing.
    targets = [
        (spec, _repo_source(spec.name, settings, session, vault))
        for spec in app_repos.KNOWN
        if spec.unified
    ]

    def ask(spec, client):
        """One source's answer, or the reason it had none."""
        if client is None:
            return spec, [], None
        try:
            return spec, client.search(query), None
        except SourceError as exc:
            return spec, [], str(exc)

    # ⚠️ Concurrently, because these wait on different things (W103). Serially,
    # a cold search paid the *sum* of every index parse — 11 seconds, which reads
    # as a hang. In parallel it costs the slowest one. Warm, this changes nothing;
    # it is the cold path that was unusable.
    with ThreadPoolExecutor(max_workers=max(1, len(targets))) as pool:
        answers = list(pool.map(lambda pair: ask(*pair), targets))

    for spec, found, problem in answers:
        if problem is not None:
            problems.append({"source": spec.name, "label": spec.label, "error": problem})
            continue
        for app in found:
            rows.append(
                {
                    "package_name": app.package_name,
                    "name": app.name,
                    "summary": app.summary,
                    "web_url": app.web_url,
                    "source": spec.name,
                    "source_label": spec.label,
                    "verifiable": spec.kind != "apkpure",
                    "picks_version": True,
                }
            )

    # ⚠️ Verifiable sources first — the same recommendation the catalogue's order
    # encodes. Within that, an exact package match before anything else.
    order = {spec.name: i for i, spec in enumerate(app_repos.KNOWN)}
    rows.sort(
        key=lambda r: (
            0 if r["package_name"].lower() == query.lower() else 1,
            order.get(r["source"], 99),
            r["name"].lower(),
        )
    )

    return JSONResponse({"apps": rows, "problems": problems})


@router.get("/apps/play/search")
def play_search(
    q: str = "",
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    vault: TokenVault = Depends(get_token_vault),
    identity: AdminIdentity = Depends(admin_required),
) -> JSONResponse:
    """Search Google Play by app name, or take an exact package id (W101).

    Its own route rather than a member of the unified search: Play needs a linked
    account, so "nothing found" and "nothing linked" are different answers and the
    tab has to be able to tell them apart.
    """
    from app.services.app_sources.base import SourceError

    query = (q or "").strip()
    if not query:
        return JSONResponse({"apps": [], "problems": []})

    client = _repo_source("google-play", settings, session, vault)
    if client is None:
        return JSONResponse(
            {
                "apps": [],
                "problems": [
                    {
                        "source": "google-play",
                        "label": "Google Play",
                        "error": "No Google account is linked. Link one under "
                        "Admin → Google Play before searching.",
                    }
                ],
            }
        )

    try:
        apps = client.search(query)
    except SourceError as exc:
        return JSONResponse(
            {
                "apps": [],
                "problems": [
                    {"source": "google-play", "label": "Google Play", "error": str(exc)}
                ],
            }
        )

    return JSONResponse(
        {
            "apps": [
                {
                    "package_name": a.package_name,
                    "name": a.name,
                    "summary": a.summary,
                    "web_url": a.web_url,
                    "source": "google-play",
                    "source_label": "Google Play",
                    # Play publishes no digest through this path, so a download is
                    # checked by reading the file rather than by comparison.
                    "verifiable": False,
                    # ⚠️ Play cannot enumerate versions at all — the source
                    # returns one placeholder whose code and name are only known
                    # once the file is read. Offering a "Versions" button that
                    # opens a list of one blank row is worse than offering
                    # nothing, so the client imports straight from here (W125).
                    "picks_version": False,
                }
                for a in apps
            ],
            "problems": [],
        }
    )


@router.get("/apps/repo/versions")
def repo_versions(
    package: str,
    source: str = "fdroid",
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    vault: TokenVault = Depends(get_token_vault),
    identity: AdminIdentity = Depends(admin_required),
) -> JSONResponse:
    from app.services import repo_import
    from app.services.app_sources.base import SourceError

    client = _repo_source(source, settings, session, vault)
    if client is None:
        return JSONResponse({"error": f"unknown source {source!r}"}, status_code=404)

    try:
        versions = client.versions(package)
    except SourceError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)

    return JSONResponse(
        {
            "source": client.name,
            "package_name": package,
            "versions": [
                _version_row(session, v, repo_import.preflight(session, v))
                for v in versions
            ],
        }
    )


@router.post("/apps/repo/import")
def repo_import_form(
    package: str = Form(...),
    version_key: str = Form(...),
    source: str = Form(default="fdroid"),
    label: str = Form(default=""),
    session: Session = Depends(get_db),
    session_factory=Depends(get_session_factory),
    storage: ArtifactStorage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
    vault: TokenVault = Depends(get_token_vault),
    identity: AdminIdentity = Depends(admin_required),
) -> JSONResponse:
    """Start an import and hand back a job to watch.

    ⚠️ **The version is looked up again here rather than taken from the form.**
    Everything the browser holds about a build is the catalogue's word relayed
    through a page; re-reading it means the download URL and the digest come from
    the index at the moment of import, not from whatever a form field says.
    """
    from app.services import import_jobs, repo_import
    from app.services.app_sources.base import SourceError

    client = _repo_source(source, settings, session, vault)
    if client is None:
        return JSONResponse({"error": f"unknown source {source!r}"}, status_code=404)

    try:
        versions = client.versions(package)
    except SourceError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)

    chosen = next((v for v in versions if v.version_key == version_key), None)
    if chosen is None:
        return JSONResponse(
            {"error": f"version {version_key} is no longer offered for {package}"},
            status_code=404,
        )

    checks = repo_import.preflight(session, chosen)
    if not checks.ok:
        # Refused here rather than after a download: the reasons are all knowable
        # from the listing, and spending bandwidth to arrive at the same answer
        # helps nobody.
        return JSONResponse({"error": checks.blocking[0]}, status_code=422)

    job = import_jobs.start_repo(
        session_factory,
        storage,
        source=client,
        version=chosen,
        label=label.strip() or package,
    )
    return JSONResponse(job.as_dict(), status_code=status.HTTP_202_ACCEPTED)


@router.get("/apps/repo/import/{job_id}")
def repo_import_status(
    job_id: str,
    identity: AdminIdentity = Depends(admin_required),
) -> JSONResponse:
    from app.services import import_jobs

    job = import_jobs.get(job_id)
    if job is None:
        return JSONResponse(
            {"state": "failed", "error": "the import job is no longer known — "
             "the server may have restarted. Press Import again."},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return JSONResponse(job.as_dict())


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
    """Add a package to the library.

    ⚠️ **It does nothing to the fleet** (W139). An upload used to deploy
    fleet-wide in silence, then gained a three-way publish question to control
    that. Both are gone: a device installs the build its policy names, so a new
    upload reaches a device only when someone chooses it in a policy.
    """
    data = file.file.read()
    if not data:
        return _redirect("/apps?error=the+uploaded+file+is+empty")
    if len(data) > settings.max_upload_bytes:
        return _redirect(f"/apps?error={_quote(f'upload exceeds {settings.max_upload_bytes} bytes')}")

    try:
        comparison = package_service.compare_upload(session, data)
        result = package_service.ingest(
            session, storage, data, label=label.strip() or None
        )
    except package_service.PackageError as exc:
        return _redirect(f"/apps?error={_quote(str(exc))}")

    eff.invalidate_all(session)
    session.commit()
    return _redirect(f"/apps?uploaded={_quote(_upload_summary(comparison, result))}")


def _upload_summary(
    comparison: package_service.VersionComparison, result: package_service.IngestResult
) -> str:
    """One sentence saying what the upload actually did.

    ⚠️ Which is: added a build to the library, and nothing else (W139). The
    sentence still names what devices are on, because "you now have two builds
    and they are running the other one" is the thing an operator wants to know
    next — but it no longer claims anything moved, because nothing did.
    """
    name = result.package.label or result.package.package_name
    code = result.version.version_code
    added = f"{name} {code} was added to the library"
    if comparison.device_count:
        plural = "" if comparison.device_count == 1 else "s"
        added += (
            f". {comparison.device_count} device{plural} follow a policy naming "
            f"{comparison.package_name} — edit it to deploy this build"
        )
    return added + "."


@router.post("/apps/preview-upload")
def preview_app_upload(
    file: UploadFile = File(...),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    identity: AdminIdentity = Depends(admin_required),
) -> JSONResponse:
    """What this upload would do, before it is taken.

    Nothing is stored. The console calls this to decide whether it needs to ask
    the operator anything at all — for a first upload of a package there is no
    decision to make, and a dialog with one option is just an extra click.
    """
    data = file.file.read()
    if not data:
        return JSONResponse({"error": "the uploaded file is empty"}, status_code=400)
    if len(data) > settings.max_upload_bytes:
        return JSONResponse(
            {"error": f"upload exceeds {settings.max_upload_bytes} bytes"}, status_code=400
        )
    try:
        c = package_service.compare_upload(session, data)
    except package_service.PackageError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    return JSONResponse(
        {
            "relation": c.relation,
            "package_name": c.package_name,
            "version_code": c.version_code,
            "version_name": c.version_name,
            "deployed_version_code": c.deployed_version_code,
            "deployed_version_name": c.deployed_version_name,
            "policy_names": list(c.policy_names),
            "device_count": c.device_count,
            "would_deploy": c.would_deploy,
        }
    )


# --------------------------------------------------------------------------- #
# Storefronts — versions of the ATLAS store a policy assigns (W140)
# --------------------------------------------------------------------------- #


@router.post("/storefronts")
def create_storefront_form(
    name: str = Form(...),
    description: str = Form(default=""),
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    """Create a shelf and go straight to it, where its apps are chosen.

    Empty on arrival, which is the honest state: a storefront with nothing on it
    offers nothing, and nobody has said what belongs there yet.
    """
    try:
        storefront = storefront_service.create(
            session, name=name, description=description
        )
    except storefront_service.StorefrontError as exc:
        return _redirect(f"/apps?error={_quote(str(exc))}#tab-store")
    session.commit()
    return _redirect(f"/storefronts/{storefront.id}")


@router.get("/storefronts/{storefront_id}", response_class=HTMLResponse)
def storefront_detail_page(
    storefront_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> HTMLResponse:
    storefront = storefront_service.get(session, storefront_id)
    if storefront is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "storefront not found")

    chosen = {str(item.package_id): str(item.version_id) for item in storefront.items}
    return _render(
        request,
        "storefront_detail.html",
        identity=identity,
        storefront=storefront,
        packages=list(
            session.scalars(select(AppPackage).order_by(AppPackage.package_name))
        ),
        chosen=chosen,
        # Which policies hand this shelf out, so deleting it is an informed act.
        used_by=_policies_naming_storefront(session, storefront_id),
    )


def _name_storefronts_in(session: Session, conflicts: list[dict]) -> list[dict]:
    """Swap storefront ids for their names before the device page renders them.

    ⚠️ **Otherwise the one conflict the operator asked to be warned about is the
    least readable thing on the page.** The generic renderer prints the winning
    and discarded values verbatim, which for every other field is a number or a
    package name and here is a pair of uuids — technically complete and no use
    to anyone deciding which policy to change.

    A name that no longer resolves is left as-is rather than blanked: a
    storefront deleted after the conflict was recorded is exactly when knowing
    the raw id still helps.
    """
    ids = {
        str(value)
        for conflict in conflicts
        if conflict.get("field") == "storefront_id"
        for value in [conflict.get("winning_value")]
        + [d.get("value") for d in conflict.get("discarded", [])]
        if value
    }
    if not ids:
        return conflicts

    names = {
        str(sf.id): sf.name
        for sf in session.scalars(select(Storefront).where(Storefront.id.in_(
            [uuid.UUID(i) for i in ids if _is_uuid(i)]
        )))
    }

    named = []
    for conflict in conflicts:
        if conflict.get("field") != "storefront_id":
            named.append(conflict)
            continue
        copy = dict(conflict)
        copy["winning_value"] = names.get(
            str(copy.get("winning_value")), copy.get("winning_value")
        )
        copy["discarded"] = [
            {**d, "value": names.get(str(d.get("value")), d.get("value"))}
            for d in copy.get("discarded", [])
        ]
        named.append(copy)
    return named


def _is_uuid(raw: str) -> bool:
    try:
        uuid.UUID(raw)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def _policies_naming_storefront(session: Session, storefront_id: uuid.UUID) -> list[str]:
    """Names of the policies whose current version assigns this storefront.

    ⚠️ Latest version only. An older version naming it is history, not a live
    instruction — reporting those would make a shelf look in use long after
    every policy had moved off it.
    """
    names: list[str] = []
    for policy in session.scalars(select(Policy).where(Policy.policy_type == "APP_CATALOG")):
        version = policy.latest_version
        if version is None:
            continue
        if (version.spec or {}).get("storefront_id") == str(storefront_id):
            names.append(policy.name)
    return sorted(names)


@router.post("/storefronts/{storefront_id}")
def rename_storefront_form(
    storefront_id: uuid.UUID,
    name: str = Form(...),
    description: str = Form(default=""),
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    storefront = storefront_service.get(session, storefront_id)
    if storefront is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "storefront not found")
    try:
        storefront_service.rename(
            session, storefront, name=name, description=description
        )
    except storefront_service.StorefrontError as exc:
        return _redirect(f"/storefronts/{storefront_id}?error={_quote(str(exc))}")
    session.commit()
    return _redirect(f"/storefronts/{storefront_id}?saved=1")


@router.post("/storefronts/{storefront_id}/items")
def set_storefront_items_form(
    storefront_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    """Replace the shelf with the ticked apps, each at the build chosen beside it.

    ⚠️ The version select is read only for a **ticked** app. An operator who
    changes a build and then unticks the app has said "not this one at all", and
    honouring the select would put it back on the shelf.
    """
    storefront = storefront_service.get(session, storefront_id)
    if storefront is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "storefront not found")

    form = _sync_form(request)
    version_ids: list[uuid.UUID] = []
    for package_id in form.getlist("include"):
        raw = (form.get(f"version__{package_id}") or "").strip()
        with suppress(ValueError):
            version_ids.append(uuid.UUID(raw))

    try:
        storefront_service.set_items(session, storefront, version_ids)
    except storefront_service.StorefrontError as exc:
        return _redirect(f"/storefronts/{storefront_id}?error={_quote(str(exc))}")
    session.commit()
    return _redirect(f"/storefronts/{storefront_id}?saved=1")


@router.post("/storefronts/{storefront_id}/delete")
def delete_storefront_form(
    storefront_id: uuid.UUID,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    storefront = storefront_service.get(session, storefront_id)
    if storefront is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "storefront not found")
    name = storefront.name
    storefront_service.delete(session, storefront)
    session.commit()
    return _redirect(f"/apps?deleted={_quote(name)}#tab-store")


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


@router.get("/content/{file_id}/raw")
def content_raw(
    file_id: uuid.UUID,
    session: Session = Depends(get_db),
    storage: ArtifactStorage = Depends(get_storage),
    identity: AdminIdentity = Depends(admin_required),
) -> StreamingResponse:
    """Serve a managed file's bytes to the console.

    Needed for the wallpaper preview: the device-facing artifact route is behind
    mTLS and unreachable from a browser. Admin-guarded like every other console
    route, and it streams rather than reading the blob into memory — a wallpaper is
    small, but nothing here enforces that.
    """
    managed = session.get(ManagedFile, file_id)
    if managed is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "file not found")
    try:
        handle = storage.open(managed.artifact_sha256)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "the stored artifact is missing"
        ) from exc
    return StreamingResponse(
        handle,
        media_type=managed.media_type or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{managed.original_filename}"'},
    )


@router.get("/content", response_class=HTMLResponse)
def content_page(
    request: Request,
    session: Session = Depends(get_db),
    storage: ArtifactStorage = Depends(get_storage),
    identity: AdminIdentity = Depends(admin_required),
) -> HTMLResponse:
    rows = content_admin.content_rows(session)
    return _render(
        request,
        "content.html",
        identity=identity,
        rows=rows,
        # What each package declares, so the page can show a package as a package
        # rather than as a zip of unknown provenance. Read through a cache keyed
        # on the artifact hash; an unreadable one is simply absent.
        manifests={
            str(row.file.id): data_package_service.manifest_of(storage, row.file)
            for row in rows
            if row.file.is_data_package
        },
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


@router.post("/policies/file/upload")
def upload_policy_file(
    file: UploadFile = File(...),
    name: str = Form(default=""),
    session: Session = Depends(get_db),
    storage: ArtifactStorage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
    identity: AdminIdentity = Depends(admin_required),
) -> JSONResponse:
    """Take a file chosen inside a policy editor and hand back its id (W91 B6).

    The General Files counterpart of the data-package upload: an id rather than a
    redirect, because the policy is unsaved and a redirect would take every other
    category's changes with it.

    ⚠️ **Ingested into the library**, unlike the wallpaper upload (W46). That one
    is `in_library=False` because picking an image for one policy is not
    publishing a fleet asset; a file deployed to devices is exactly that, and the
    operator asked for these to reach Content.

    ⚠️ **A zip carrying a manifest is refused here** and sent to the ATAK Data
    Packages sub-topic. Accepted as an ordinary file it would go wherever a
    hand-typed destination said — where ATAK is not watching, so **nothing would
    happen at all**: no import, no error, no trace. The steering note beside the
    control was not enough on its own, because the operator who needs it is the
    one who did not read it.
    """
    data = file.file.read()
    if not data:
        return JSONResponse({"error": "the uploaded file is empty"}, status_code=422)
    if len(data) > settings.max_upload_bytes:
        return JSONResponse(
            {"error": f"upload exceeds {settings.max_upload_bytes} bytes"}, status_code=413
        )
    if dted.looks_like_dted(data):
        # Same reasoning as the package refusal: accepted here it would unpack
        # wherever the destination said, and ATAK reads terrain from one
        # directory only. It would extract successfully and show no terrain.
        return JSONResponse(
            {
                "error": (
                    "this zip is ATAK terrain data — it holds DTED cell folders "
                    "like 'w115'. Upload it under ATAK DTED instead, which checks "
                    "the layout and unpacks it into ATAK's DTED directory. Placed "
                    "as a general file it would extract wherever the destination "
                    "said, where ATAK does not read terrain."
                )
            },
            status_code=422,
        )

    if mission_package.has_manifest(data):
        # ATAK's own test — `HasManifest` is a suffix match and nothing more — so
        # a package with a *broken* manifest is refused here too. It was still
        # built as a package, and the data-package tool will say exactly what is
        # wrong with it, which this route cannot.
        return JSONResponse(
            {
                "error": (
                    "this zip is an ATAK data package — it carries "
                    "MANIFEST/manifest.xml. Upload it under ATAK Data Packages "
                    "instead, which checks the manifest and delivers it to the "
                    "directory ATAK watches. Placed as a general file it would "
                    "go wherever the destination said, where ATAK is not looking."
                )
            },
            status_code=422,
        )

    try:
        managed = file_service.ingest_file(
            session,
            storage,
            data,
            name=(name or "").strip() or (file.filename or "unnamed"),
            original_filename=file.filename or "unnamed",
            media_type=file.content_type or "application/octet-stream",
        )
        session.commit()
    except file_service.FileError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    return JSONResponse(
        {
            "id": str(managed.id),
            "name": managed.name,
            # So the console can say "that looks like a data package" without
            # refusing it — the operator may have a reason.
            "is_archive": bool(managed.is_archive),
        }
    )


def _dted_repack_note(layout: dted.DtedLayout) -> str:
    """What to tell the operator about a rewrite they did not ask for.

    Saying nothing would be worse than saying too much: the archive they get back
    is not the one they uploaded, and the next person comparing checksums deserves
    to know why.
    """
    if not layout.needs_repack:
        return ""
    wrappers = ", ".join(repr(w) for w in layout.wrappers) or "a sub-folder"
    carried = (
        f" {layout.carried} other file{'' if layout.carried == 1 else 's'} kept as they were."
        if layout.carried
        else ""
    )
    return (
        f"The cells were inside {wrappers}, where ATAK would not have found them. "
        f"They have been moved to the top of the archive.{carried}"
    )


@router.post("/policies/dted/upload")
def upload_policy_dted(
    file: UploadFile = File(...),
    name: str = Form(default=""),
    session: Session = Depends(get_db),
    storage: ArtifactStorage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
    identity: AdminIdentity = Depends(admin_required),
) -> JSONResponse:
    """Take a DTED archive chosen inside a policy editor and hand back its id (W93).

    ⚠️ **Sorted out here because the failure is silent on the device.** ATAK
    unpacks DTED flat into one directory and looks nowhere else, so terrain buried
    a level down extracts perfectly, puts every file on disk, and shows nothing.
    No log says so afterwards.

    **W94 repacks rather than refuses.** A nested archive is what right-clicking a
    DTED folder in Windows produces, so it is the normal case, not an error. The
    cells are moved to the top here — at upload, on the server — which keeps the
    stored archive identical to what has to land on disk and leaves every fielded
    agent correct without an update.
    """
    data = file.file.read()
    if not data:
        return JSONResponse({"error": "the uploaded file is empty"}, status_code=422)
    if len(data) > settings.max_upload_bytes:
        return JSONResponse(
            {"error": f"upload exceeds {settings.max_upload_bytes} bytes"}, status_code=413
        )
    try:
        layout = dted.plan(data)
    except dted.DtedError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    chosen_name = (name or "").strip() or (file.filename or "DTED")
    try:
        if layout.needs_repack:
            # Streamed through a temp file: the sample inflates to 1.75 GB, and
            # holding that as bytes to hand to `ingest_file` would double it.
            with tempfile.TemporaryFile() as repacked:
                dted.repack(io.BytesIO(data), repacked, layout)
                repacked.seek(0)
                managed = file_service.ingest_stream(
                    session,
                    storage,
                    repacked,
                    name=chosen_name,
                    original_filename=file.filename or "dted.zip",
                    media_type="application/zip",
                )
        else:
            managed = file_service.ingest_file(
                session,
                storage,
                data,
                name=chosen_name,
                original_filename=file.filename or "dted.zip",
                media_type="application/zip",
            )
        session.commit()
    except file_service.FileError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    return JSONResponse(
        {
            "id": str(managed.id),
            "name": managed.name,
            "summary": layout.archive.summary,
            "repacked": layout.needs_repack,
            "note": _dted_repack_note(layout),
        }
    )


@router.post("/policies/data-package/upload")
def upload_policy_data_package(
    file: UploadFile = File(...),
    name: str = Form(default=""),
    session: Session = Depends(get_db),
    storage: ArtifactStorage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
    identity: AdminIdentity = Depends(admin_required),
) -> JSONResponse:
    """Take a package chosen inside a policy editor and hand back its id (W91).

    Returns the id rather than redirecting because the policy has not been saved
    yet — the form holds the id until the operator commits the whole thing. The
    same shape as the wallpaper upload W46 introduced, for the same reason: a
    redirect here would discard every unsaved change on a page that holds an
    entire policy.

    ⚠️ Ingested **into the library** (`in_library` left true), unlike the
    wallpaper. The operator asked for these to reach the Content section: a data
    package is fleet content someone may want to reuse or inspect, not an asset
    private to one policy.
    """
    data = file.file.read()
    if not data:
        return JSONResponse({"error": "the uploaded file is empty"}, status_code=422)
    if len(data) > settings.max_upload_bytes:
        return JSONResponse(
            {"error": f"upload exceeds {settings.max_upload_bytes} bytes"}, status_code=413
        )
    try:
        package = data_package_service.ingest_upload(
            session,
            storage,
            data,
            name=name,
            original_filename=file.filename or "package.zip",
        )
        session.commit()
    except mission_package.DataPackageError as exc:
        # The validator's own words: the operator is standing here, and "rejected"
        # on its own sends them hunting for a fault that may not be in the file.
        return JSONResponse({"error": str(exc)}, status_code=422)
    except file_service.FileError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    # The manifest's own content count, so the confirmation says what was
    # accepted rather than merely that something was.
    manifest = data_package_service.manifest_of(storage, package)
    return JSONResponse(
        {
            "id": str(package.id),
            "name": package.name,
            "contents": manifest.content_count if manifest else 0,
        }
    )


@router.post("/policies/data-package/create")
async def create_policy_data_package(
    request: Request,
    session: Session = Depends(get_db),
    storage: ArtifactStorage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
    identity: AdminIdentity = Depends(admin_required),
) -> JSONResponse:
    """Build a package from loose files, without leaving the policy editor (W91)."""
    form = await request.form()
    name = str(form.get("name") or "").strip()
    description = str(form.get("description") or "").strip()

    payloads: list[tuple[str, bytes]] = []
    total = 0
    for upload in form.getlist("files"):
        if not isinstance(upload, StarletteUploadFile):
            continue
        content = await upload.read()
        if not content:
            # An empty file input is a row the operator added and left blank, not
            # an error worth refusing the whole package for.
            continue
        total += len(content)
        if total > settings.max_upload_bytes:
            return JSONResponse(
                {"error": f"the package exceeds {settings.max_upload_bytes} bytes"},
                status_code=413,
            )
        payloads.append((upload.filename or "file", content))

    try:
        package = data_package_service.create(
            session, storage, name=name, files=payloads, description=description or None
        )
        session.commit()
    except mission_package.DataPackageError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    except file_service.FileError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    manifest = data_package_service.manifest_of(storage, package)
    return JSONResponse(
        {
            "id": str(package.id),
            "name": package.name,
            "contents": manifest.content_count if manifest else 0,
        }
    )


@router.post("/content/data-package/upload")
def upload_data_package_form(
    name: str = Form(default=""),
    description: str = Form(default=""),
    file: UploadFile = File(...),
    session: Session = Depends(get_db),
    storage: ArtifactStorage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    """Take an already-built ATAK data package, checked before it is catalogued (W91).

    ⚠️ **Validated here rather than at delivery.** A zip ATAK will not import
    fails on a tablet as nothing happening at all — no error, no import, no
    trace. The operator is standing in front of this form, so this is the only
    place the refusal can actually reach them.
    """
    data = file.file.read()
    if not data:
        return _redirect("/content?error=the+uploaded+file+is+empty")
    if len(data) > settings.max_upload_bytes:
        return _redirect(
            f"/content?error={_quote(f'upload exceeds {settings.max_upload_bytes} bytes')}"
        )
    try:
        package = data_package_service.ingest_upload(
            session,
            storage,
            data,
            name=name,
            original_filename=file.filename or "package.zip",
            description=description or None,
        )
        session.commit()
    except mission_package.DataPackageError as exc:
        return _redirect(f"/content?error={_quote(str(exc))}")
    except file_service.FileError as exc:
        return _redirect(f"/content?error={_quote(str(exc))}")
    return _redirect(f"/content?created={_quote(package.name)}")


@router.post("/content/data-package/create")
async def create_data_package_form(
    request: Request,
    session: Session = Depends(get_db),
    storage: ArtifactStorage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    """Build a data package out of loose files (W91).

    Read from the raw form rather than typed parameters because the file field is
    repeated, and the count is the operator's choice.
    """
    form = await request.form()
    name = str(form.get("name") or "").strip()
    description = str(form.get("description") or "").strip()

    # ⚠️ `starlette`'s UploadFile, not FastAPI's. FastAPI's is a *subclass*, and
    # `request.form()` yields the base class — so an isinstance check against the
    # subclass silently matches nothing and the package looks empty. It fails as
    # "a data package needs at least one file" while the operator is looking at
    # the files they just attached.
    uploads = [u for u in form.getlist("files") if isinstance(u, StarletteUploadFile)]
    payloads: list[tuple[str, bytes]] = []
    total = 0
    for upload in uploads:
        content = await upload.read()
        if not content:
            # A file input left empty submits as a zero-byte part; it is not an
            # error, it is a row the operator did not fill in.
            continue
        total += len(content)
        if total > settings.max_upload_bytes:
            return _redirect(
                f"/content?error={_quote(f'the package exceeds {settings.max_upload_bytes} bytes')}"
            )
        payloads.append((upload.filename or "file", content))

    try:
        package = data_package_service.create(
            session, storage, name=name, files=payloads, description=description or None
        )
        session.commit()
    except mission_package.DataPackageError as exc:
        return _redirect(f"/content?error={_quote(str(exc))}")
    except file_service.FileError as exc:
        return _redirect(f"/content?error={_quote(str(exc))}")
    return _redirect(f"/content?created={_quote(package.name)}")


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
    bypass_pin_value = bypass_pin.get_or_create(session)
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
        bypass_pin=bypass_pin_value,
        bypass_attempts_max=bypass_pin.MAX_ATTEMPTS,
        agent=_agent_update_panel(session, settings),
        takgov=_takgov_panel(session),
        googleplay=_googleplay_panel(session),
        attributes=attribute_service.list_attributes(session),
    )


def _googleplay_panel(session: Session) -> dict:
    from app.services import google_play_link

    link = google_play_link.get(session)
    session.commit()  # the row is created lazily on first view
    # ⚠️ The token itself is never part of this. The console shows *that* one is
    # held, never its value — there is no reason to render a durable credential
    # back into a page.
    return {"link": link}


@router.post("/admin/google-play/link")
def google_play_link_form(
    email: str = Form(...),
    oauth_token: str = Form(...),
    device_profile: str = Form(default=""),
    session: Session = Depends(get_db),
    vault: TokenVault = Depends(get_token_vault),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    """Spend the one-time token for a durable one and seal it (W99)."""
    from app.services import google_play_link

    try:
        google_play_link.link_account(
            session,
            vault,
            email=email,
            oauth_token=oauth_token,
            device_profile=device_profile or google_play_link.DEFAULT_DEVICE,
            linked_by=getattr(identity, "subject", None),
        )
        session.commit()
    except google_play_link.GooglePlayLinkError as exc:
        # Committed even on failure: `last_error` is the useful part, and the
        # oauth token is spent either way, so losing the explanation would leave
        # the operator retrying a value that cannot work.
        session.commit()
        return _redirect(f"/admin?tab=googleplay&play_error={_quote(str(exc))}")

    return _redirect("/admin?tab=googleplay&play_linked=1")


@router.post("/admin/google-play/unlink")
def google_play_unlink_form(
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> RedirectResponse:
    from app.services import google_play_link

    google_play_link.unlink(session)
    session.commit()
    return _redirect("/admin?tab=googleplay&play_unlinked=1")


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
    return _redirect("/admin?unbound=1#tab-takgov")


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

    ⚠️ The submodule is imported **explicitly**. `import anyio` alone does not bind
    `from_thread` in anyio 4.15 — its lazy loader raises `AttributeError: module
    'anyio' has no attribute 'from_thread'` — while 4.14 resolved it happily. That
    difference took out every console form that posts through here, and no test saw
    it: the venv had 4.14 and the container 4.15, because `anyio` arrives as an
    unpinned transitive dependency and a rebuild moved it. It is pinned now, and
    this import no longer depends on the loader's behaviour either way.
    """
    from anyio import from_thread

    return from_thread.run(request.form)
