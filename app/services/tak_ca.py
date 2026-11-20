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

"""Which certificate authority each device's TAK Server certificates come from (W453).

The ATLAS plugin reports the client certificate's issuer for each connection
ATAK holds (`cert_issuer`, plugin 1.5.0+, contract). That is what tells an
operator who has moved to a TAK Server's new intermediate CA.

⚠️ **A plugin that cannot say is "unknown", never "moved".** An older plugin
reports no issuer at all; reading its silence as "not on the old CA" would show
a device as moved that never was.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services import tak_enrollment
from app.services.plugin_status import PluginStatus, TakServer

#: The plugin capability that carries `cert_issuer` (contract).
CAPABILITY = tak_enrollment.REENROLL_CAPABILITY

UNKNOWN = "unknown"
UNKNOWN_WHY = "The ATLAS plugin on this device is older than 1.5.0 and does not report it."


@dataclass(frozen=True)
class IssuedBy:
    """One connection's certificate authority, as the console shows it."""

    #: The issuer's common name, "unknown", or None when no certificate is held.
    label: str | None
    #: The full DN, or why it is unknown. For a tooltip.
    detail: str | None = None
    #: The first 16 hex digits of the client certificate's SHA-256.
    fingerprint: str | None = None


def short_name(dn: str | None) -> str | None:
    """The CN of an RFC 2253 DN, or the DN itself when it has none."""
    if not dn:
        return None
    for part in dn.split(","):
        key, _, value = part.strip().partition("=")
        if key.upper() == "CN" and value:
            return value
    return dn


def reports_issuer(status: PluginStatus | None) -> bool:
    return status is not None and CAPABILITY in status.capabilities


def issued_by(status: PluginStatus | None, server: TakServer) -> IssuedBy:
    if not reports_issuer(status):
        return IssuedBy(UNKNOWN, UNKNOWN_WHY)
    if not server.cert_issuer:
        return IssuedBy(None)
    return IssuedBy(short_name(server.cert_issuer), server.cert_issuer,
                    (server.cert_sha256 or "")[:16] or None)


def issuer_text(status: PluginStatus | None, server: TakServer) -> str | None:
    """For an export: the full DN, "unknown", or None when no certificate is held."""
    return UNKNOWN if not reports_issuer(status) else server.cert_issuer


def device_label(status: PluginStatus | None) -> str:
    """Every CA this device's connections come from, for the device list.

    "" when the plugin reports no TAK Server connection (or never reported),
    "unknown" for a plugin too old to say.
    """
    if status is None or not status.tak_servers:
        return ""
    if not reports_issuer(status):
        return UNKNOWN
    names = {short_name(s.cert_issuer) for s in status.tak_servers if s.cert_issuer}
    return ", ".join(sorted(names))
