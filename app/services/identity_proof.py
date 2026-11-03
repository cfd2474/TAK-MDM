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

"""Whether a device's secure hardware proves which device it is (W448, audit H1).

An enrollment credential plus a serial number, which is printed on the label,
was enough to take over a device's record. What a stranger cannot produce is
this device's secure hardware signing this device's serial or IMEI. So a record
is "provable" when an ID-attested chain that :func:`key_attestation.
verify_identity` believes names an identifier the record already holds.

Pure apart from :func:`known_identifiers`, which only reads.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Device, DeviceIdentifier
from app.services.key_attestation import UNIQUE_IDS, IdentityVerdict

_LABELS = {"serial": "serial", "imei": "IMEI", "second_imei": "IMEI", "meid": "MEID"}


@dataclass(frozen=True)
class Proof:
    provable: bool
    #: In words an operator can act on.
    reason: str
    #: What the hardware attested, shown on the device page.
    ids: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"provable": self.provable, "reason": self.reason, "ids": self.ids}


def _norm(value: str) -> str:
    return value.strip().upper()


def judge(verdict: IdentityVerdict | None, known: Iterable[str | None], *,
          unsupported: str | None = None) -> Proof:
    """Does ``verdict`` prove a device holding ``known`` identifiers?

    ``verdict`` is None when the agent sent no ID-attested chain; ``unsupported``
    is then the agent's reason, such as the hardware refusing ID attestation.
    """
    if verdict is None:
        if unsupported:
            return Proof(False, f"This device can't attest its identity ({unsupported})")
        return Proof(False, "The agent sent no identity attestation")
    if not verdict.ok:
        return Proof(False, "; ".join(verdict.problems), verdict.ids)

    have = {_norm(v) for v in known if v}
    for name in UNIQUE_IDS:
        value = verdict.ids.get(name)
        if value and _norm(value) in have:
            return Proof(True, f"The hardware attests {_LABELS[name]} {value}", verdict.ids)
    attested = ", ".join(
        f"{_LABELS[n]} {verdict.ids[n]}" for n in UNIQUE_IDS if verdict.ids.get(n)
    )
    return Proof(
        False, f"The hardware attests {attested}, which this device's record does not hold",
        verdict.ids,
    )


def known_identifiers(session: Session, device: Device) -> list[str]:
    """Every identifier the record answers to: what enrollment matches on, plus its columns."""
    values = list(session.scalars(
        select(DeviceIdentifier.value).where(DeviceIdentifier.device_id == device.id)
    ))
    return values + [v for v in (device.serial_number, device.imei) if v]
