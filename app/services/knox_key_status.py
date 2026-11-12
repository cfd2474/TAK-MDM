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

"""Whether this instance's Knox key is current, as the fleet reports it (W480).

⚠️ **The devices are the only authority.** Samsung offers an MDM no public call
to check a key; what ATLAS knows is what each Samsung device said when it
activated. So "valid" here means "at least one device is active on this key",
and the expiry is an estimate: a KPE Premium key 📖 *"expires 2 years from the
date of activation"*, counted from the earliest activation ATLAS has seen.

Matching a device to the key uses Samsung's masked key, whose last group is
shown (`…-1N1TI-HEK69`): the last five characters of the configured key.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Device
from app.services import knox_license

#: 📖 KPE Premium: "It expires 2 years from the date of activation."
KEY_TERM = timedelta(days=730)

OK, WARN, BAD, OFF = "ok", "warn", "bad", "off"

#: W483: shown on the dashboard tile, Admin and the policy editor.
NO_KEY_DETAIL = (
    "Samsung Knox is on but no license key is set; Samsung devices skip every "
    "Knox setting until one is"
)
#: W483: where an operator gets a key (KPE Premium is free).
LICENSE_HELP_URL = "https://docs.samsungknox.com/admin/knox-platform-for-enterprise/before-you-begin/knox-platform-for-enterprise-licenses/"


@dataclass(frozen=True)
class KeyStatus:
    level: str
    headline: str
    detail: str
    on_key: int = 0
    other_key: int = 0
    failed: int = 0
    failure_codes: dict[int, int] = field(default_factory=dict)
    first_activation: datetime | None = None
    expires_about: datetime | None = None


def status(session: Session) -> KeyStatus:
    if not knox_license.enabled(session):
        return KeyStatus(OFF, "Knox is off", "Turn Samsung Knox on in Admin to use a key.")
    key = knox_license.configured_key(session)
    if not key:
        # W483 (operator): red. Samsung devices skip every Knox setting until
        # a key is set, so Knox on without one is a fault, not "not set up".
        return KeyStatus(BAD, "No key", NO_KEY_DETAIL)
    tail = key[-5:].upper()
    rows = session.execute(select(
        Device.oem_license_status, Device.oem_license_masked_key,
        Device.oem_license_activated_at, Device.oem_license_error_code,
    ).where(Device.oem_license_status.is_not(None))).all()

    on_key, other_key, failed = 0, 0, 0
    codes: Counter[int] = Counter()
    first: datetime | None = None
    for st, masked, activated, code in rows:
        if st == "ACTIVE" and masked and masked.upper().endswith(tail):
            on_key += 1
            if activated and (first is None or activated < first):
                first = activated
        elif st in ("ACTIVE", "OTHER_KEY"):
            other_key += 1
        elif st == "FAILED":
            failed += 1
            if code is not None:
                codes[int(code)] += 1

    expires = first + KEY_TERM if first else None
    if on_key:
        level, headline = OK, "Valid"
        detail = f"Active on {on_key} device{'s' if on_key != 1 else ''} with this key (…{tail})"
        if expires:
            detail += f"; expires about {expires:%Y-%m-%d}"
    elif failed:
        level, headline = BAD, "Refused"
        common = ", ".join(f"{c}" for c, _ in codes.most_common(3)) or "no code"
        detail = f"Samsung refused this key on {failed} device{'s' if failed != 1 else ''} (code {common})"
    else:
        level, headline = WARN, "Not confirmed"
        detail = f"No device has activated this key (…{tail}) yet"
    if other_key and on_key:
        level = WARN
        detail += f"; {other_key} device{'s' if other_key != 1 else ''} still on another key"
    return KeyStatus(level, headline, detail, on_key, other_key, failed, dict(codes), first, expires)
