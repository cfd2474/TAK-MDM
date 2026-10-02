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

"""The devices Google Play downloads can be made "as" (W312).

Operator, 2026-10-02: option 3. Download a Play app as a real fleet device, so
Play serves the build and splits that device would get, chosen per download from
a Type → Manufacturer → Model picker. Plus one fixed profile, apkeep's Galaxy S25
Ultra, called **Flagship Smartphone**, for downloads before any device has
enrolled.

**Where the profiles come from.** Each agent reports how Play sees it (the
`device_profile` check-in field, `DeviceProfilePlan` on the agent). One profile is
kept per `Build.MODEL`, and the newest capture wins: a model's profile changes
only with its OS, and the newest OS is the one the fleet is moving to.

**How apkeep takes one.** An INI file with a `[section]` per device, chosen with
`-o device=<section>,device_properties_file=<path>`. Read from rs-google-play's
source: `from_device_properties_file` and the build-time loader for the bundled
profiles both go through `configparser::Ini::new()` and `DeviceProperties::parse`,
so a file written exactly like the bundled one behaves exactly like it.
⚠️ `Ini::new()` is case-insensitive, so section names are lower-case here, and
fingerprints carry the bundled `\\:` escape.

⚠️ **What a device sends is untrusted.** Keys are limited to the property-name
shape, values can't carry a line break (that would let one profile write a
second section into the file), and the size is bounded. A profile that fails is
dropped and logged, never a refused check-in.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Device, PlayDeviceProfile
from app.services import device_type

logger = logging.getLogger(__name__)

#: apkeep's bundled Galaxy S25 Ultra, presented as "Flagship Smartphone".
FLAGSHIP = "sm_s25u"
FLAGSHIP_LABEL = "Flagship Smartphone"

#: Form value prefix for a captured profile: `fleet:<MODEL>`.
FLEET_PREFIX = "fleet:"

_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_.]{0,63}$")
_MAX_KEYS = 200
_MAX_BYTES = 256 * 1024

#: The keys a profile is useless without. A report missing one is refused.
REQUIRED = ("Build.MODEL", "Build.FINGERPRINT", "Build.VERSION.SDK_INT", "Platforms")


@dataclass(frozen=True)
class Choice:
    """One entry in the download picker."""

    value: str          # what the form submits
    kind: str           # Smartphone, Tablet or Unknown
    manufacturer: str
    label: str          # what the operator reads
    model: str          # Build.MODEL, or "" for the Flagship


def clean(report: Any) -> dict[str, str] | None:
    """A device's report, made safe to store and to write into an INI file.

    None when it can't be used: wrong shape, too big, or missing a key Play needs.
    """
    if not isinstance(report, dict) or len(report) > _MAX_KEYS:
        return None
    props: dict[str, str] = {}
    size = 0
    for key, value in report.items():
        if not isinstance(key, str) or not _KEY.match(key):
            return None
        if not isinstance(value, (str, int, float, bool)):
            return None
        text = str(value)
        if "\n" in text or "\r" in text:
            return None
        size += len(key) + len(text)
        props[key] = text
    if size > _MAX_BYTES or any(not props.get(k) for k in REQUIRED):
        return None
    return props


def record(session: Session, device: Device, report: Any) -> PlayDeviceProfile | None:
    """Keep this device's profile as its model's, replacing an older capture."""
    props = clean(report)
    if props is None:
        logger.warning("device profile from %s refused: unusable report", device.serial_number)
        return None
    model = props["Build.MODEL"].strip()
    key = model_key(model)
    row = session.scalar(select(PlayDeviceProfile).where(PlayDeviceProfile.model_key == key))
    if row is None:
        row = PlayDeviceProfile(model_key=key)
        session.add(row)
    row.model = model
    row.manufacturer = props.get("Build.MANUFACTURER", "")
    row.properties = props
    row.captured_from = device.serial_number
    row.captured_at = datetime.now(timezone.utc)
    session.flush()
    return row


def model_key(model: str) -> str:
    return " ".join((model or "").split()).upper()


def _describe(row: PlayDeviceProfile) -> Choice:
    entry = device_type.lookup(row.model)
    if entry:
        manufacturer, label, kind = entry["brand"], entry["name"], entry["type"]
    else:
        manufacturer = (row.manufacturer or "").strip().title() or "Other"
        label = row.model
        kind = device_type.classify(row.model) or "Unknown"
    if label != row.model:
        label = f"{label} ({row.model})"
    return Choice(f"{FLEET_PREFIX}{row.model_key}", kind, manufacturer, label, row.model)


def captured(session: Session) -> list[Choice]:
    """Every captured model, for the picker."""
    rows = session.scalars(select(PlayDeviceProfile).order_by(PlayDeviceProfile.model_key))
    return [_describe(row) for row in rows]


def choices(session: Session) -> list[Choice]:
    """The Flagship first, then every captured model."""
    flagship = Choice(FLAGSHIP, "Smartphone", "Samsung", FLAGSHIP_LABEL, "")
    return [flagship, *captured(session)]


@dataclass(frozen=True)
class Resolved:
    """What apkeep needs for one download."""

    device: str                       # apkeep's `device=` value
    properties_ini: str | None = None  # a custom file's contents, or None for built-in
    label: str = ""


def resolve(session: Session, value: str | None) -> Resolved | None:
    """The form's choice, as apkeep options. None for a value that isn't a choice.

    A bare name is an apkeep built-in (the Flagship, or a profile chosen before
    W312); `fleet:<MODEL>` is a captured profile.
    """
    chosen = (value or "").strip()
    if not chosen:
        return None
    if not chosen.startswith(FLEET_PREFIX):
        label = FLAGSHIP_LABEL if chosen == FLAGSHIP else chosen
        return Resolved(device=chosen, label=label)
    key = model_key(chosen[len(FLEET_PREFIX):])
    row = session.scalar(select(PlayDeviceProfile).where(PlayDeviceProfile.model_key == key))
    if row is None:
        return None
    section = section_name(row.model_key)
    return Resolved(
        device=section,
        properties_ini=ini(section, row.properties),
        label=_describe(row).label,
    )


def section_name(key: str) -> str:
    """A section name apkeep can be told: lower-case, no INI metacharacters."""
    return "atlas_" + re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")


def ini(section: str, properties: dict[str, str]) -> str:
    """The file apkeep reads, written like the bundled device.properties."""
    lines = [f"[{section}]"]
    for key in sorted(properties):
        value = str(properties[key]).replace("\r", "").replace("\n", "")
        # The bundled file escapes ':' (it's Aurora's Java-properties export);
        # matched so both kinds of profile take the same path through the parser.
        lines.append(f"{key}={value.replace(':', chr(92) + ':')}")
    return "\n".join(lines) + "\n"
