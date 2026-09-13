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

"""Provisioning payload generation.

Two ways onto a device, both carrying the same thing — a server URL and an
enrollment token — into the agent's admin extras bundle:

* **QR provisioning**, scanned from the setup wizard after tapping the welcome
  screen six times. Works on any device, needs no Samsung account.
* **Knox Mobile Enrollment**, which auto-enrolls on first boot and survives a
  factory reset. Gated on the pending Knox partner account (R3).

Both are pure functions of settings plus a token secret, so they are trivially
testable and carry no database dependency.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.artifacts.apk import component_class
from app.config import Settings

# Android's documented provisioning extras. Names are load-bearing — the setup
# wizard silently ignores keys it does not recognise.
_COMPONENT = "android.app.extra.PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME"
_CHECKSUM = "android.app.extra.PROVISIONING_DEVICE_ADMIN_SIGNATURE_CHECKSUM"
_DOWNLOAD = "android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_DOWNLOAD_LOCATION"
_EXTRAS = "android.app.extra.PROVISIONING_ADMIN_EXTRAS_BUNDLE"
_SKIP_ENCRYPTION = "android.app.extra.PROVISIONING_SKIP_ENCRYPTION"
_LEAVE_SYSTEM_APPS = "android.app.extra.PROVISIONING_LEAVE_ALL_SYSTEM_APPS_ENABLED"
_WIFI_SSID = "android.app.extra.PROVISIONING_WIFI_SSID"
_WIFI_PASSWORD = "android.app.extra.PROVISIONING_WIFI_PASSWORD"
_WIFI_SECURITY = "android.app.extra.PROVISIONING_WIFI_SECURITY_TYPE"


class ProvisioningError(ValueError):
    """Raised when settings cannot produce a usable provisioning payload."""


def admin_extras(settings: Settings, secret: str) -> dict[str, str]:
    """What the agent receives on first run to find and authenticate to the server."""
    extras = {
        "server_url": settings.server_url,
        "enrollment_token": secret,
    }

    # With a self-signed development server the agent has no way to trust the TLS
    # certificate, and provisioning happens long before it could be told separately.
    # A publicly-issued certificate needs none of this.
    #
    # ⚠️ **An explicit `False` wins over the file being there** (W143). Behind a
    # proxy holding a publicly-issued certificate — an InfraTAK module behind
    # Caddy — pinning this deployment's own CA makes every device fail the
    # handshake during provisioning, with nothing on the tablet to explain why.
    # `pki/server.crt` may still exist from the init step, so its presence cannot
    # be the whole answer.
    if settings.include_server_ca is False:
        return extras

    tls_cert = Path(settings.pki_dir) / "server.crt"
    if tls_cert.exists():
        extras["server_ca_pem"] = tls_cert.read_text()
    elif settings.include_server_ca is True:
        raise ProvisioningError(
            "include_server_ca is set, but no server certificate exists at "
            f"{tls_cert}. Devices would be provisioned with nothing to trust."
        )

    return extras


def qr_payload(
    settings: Settings,
    secret: str,
    *,
    wifi_ssid: str | None = None,
    wifi_password: str | None = None,
    wifi_security: str = "WPA",
    leave_system_apps_enabled: bool = True,
    declared_receivers: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """The JSON encoded into a Device Owner provisioning QR code.

    ``declared_receivers`` are the receivers the uploaded agent APK actually
    contains. When supplied, the configured admin component is checked against
    them: naming a class the APK does not have produces only "something went
    wrong" on the tablet, after a download, an install, and a factory reset.
    """
    if declared_receivers:
        wanted = component_class(settings.agent_admin_receiver)
        if wanted not in declared_receivers:
            raise ProvisioningError(
                f"the agent APK declares no receiver named {wanted!r} "
                f"(configured as {settings.agent_admin_receiver!r}). Remember that a "
                f"leading dot expands against the package root. Declared receivers: "
                f"{', '.join(r for r in declared_receivers if r.startswith(settings.agent_package_name))}"
            )

    if not settings.agent_signature_checksum:
        # Android refuses to provision without this, and the failure on-device is
        # opaque. Better to fail here, where the cause is obvious.
        raise ProvisioningError(
            "agent_signature_checksum is not configured; Android will reject "
            "provisioning without the base64url SHA-256 of the agent signing certificate"
        )

    payload: dict[str, Any] = {
        _COMPONENT: settings.agent_admin_receiver,
        _CHECKSUM: settings.agent_signature_checksum,
        _DOWNLOAD: settings.agent_apk_url,
        _EXTRAS: admin_extras(settings, secret),
        _SKIP_ENCRYPTION: False,
        _LEAVE_SYSTEM_APPS: leave_system_apps_enabled,
    }

    if wifi_ssid:
        payload[_WIFI_SSID] = wifi_ssid
        payload[_WIFI_SECURITY] = wifi_security
        if wifi_password:
            payload[_WIFI_PASSWORD] = wifi_password

    return payload


def kme_payload(settings: Settings, secret: str) -> dict[str, Any]:
    """Values for a Knox Mobile Enrollment MDM profile.

    The profile itself is created in Samsung's KME console, not here — this supplies
    the three fields that console asks for, so they are never hand-transcribed.
    """
    return {
        "mdm_package_name": settings.agent_package_name,
        "mdm_apk_url": settings.agent_apk_url,
        # KME passes this through to the agent verbatim as its custom JSON payload.
        "custom_json_data": admin_extras(settings, secret),
    }
