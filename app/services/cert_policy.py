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

"""How long device certificates last, and when devices renew them (W419).

Edited on the Admin page, stored as settings; the environment values
(`TAKMDM_DEVICE_CERT_VALIDITY_DAYS`, `TAKMDM_DEVICE_CERT_RENEW_WITHIN_DAYS`) are
the defaults, so an install that never edits them behaves exactly as before.

⚠️ **Every reader goes through here.** Enrolment, renewal and reinstatement
issue certificates; check-in tells each device its renewal window. Reading the
environment in one of them and the setting in another would issue certificates
of one length while telling devices to renew on another's schedule.

⚠️ **The lifetime applies to certificates issued from now on.** Existing ones
keep their dates until they renew. The window reaches every device at its next
check-in, because the agent takes it from each one (W174).

⚠️ **The window, not the lifetime, is the offline guarantee.** A device renews
once `window` days remain, so it holds between `window` and `lifetime` days at
any moment. One that goes dark just before renewing survives only `window`
days. That is what `describe` says, because it is the part people miss.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import Settings
from app.services import settings_store

VALIDITY_KEY = "pki.device_cert_validity_days"
WINDOW_KEY = "pki.device_cert_renew_within_days"

#: Bounds for the lifetime. A week is the shortest that still leaves room for a
#: window and a device that checks in less than daily; 825 days is the old
#: pre-W174 lifetime and the most any platform trusts a leaf for.
MIN_VALIDITY = 7
MAX_VALIDITY = 825


class PolicyError(ValueError):
    """The numbers can't be saved; the message says why, for the operator."""


@dataclass(frozen=True)
class CertPolicy:
    validity_days: int
    renew_within_days: int

    @property
    def renews_every_days(self) -> int:
        return self.validity_days - self.renew_within_days

    def describe(self) -> str:
        return (
            f"Devices renew about every {self.renews_every_days} days. A device can "
            f"stay offline for at least {self.renew_within_days} and up to "
            f"{self.validity_days} days before its certificate expires."
        )


def _int(session: Session, key: str, default: int) -> int:
    try:
        return int(settings_store.get(session, key, "") or default)
    except ValueError:
        return default


def current(session: Session, settings: Settings) -> CertPolicy:
    """What is in force: the Admin page's numbers, or the environment's."""
    return CertPolicy(
        validity_days=_int(session, VALIDITY_KEY, settings.device_cert_validity_days),
        renew_within_days=_int(session, WINDOW_KEY, settings.device_cert_renew_within_days),
    )


def validate(validity_days: int, renew_within_days: int) -> CertPolicy:
    if not MIN_VALIDITY <= validity_days <= MAX_VALIDITY:
        raise PolicyError(
            f"A certificate lifetime must be between {MIN_VALIDITY} and "
            f"{MAX_VALIDITY} days."
        )
    if renew_within_days < 1:
        raise PolicyError("Devices must renew at least 1 day before expiry.")
    if renew_within_days >= validity_days:
        # At or above the lifetime every certificate is born due, and the whole
        # fleet renews on every check-in for ever.
        raise PolicyError(
            "The renewal window must be shorter than the certificate lifetime, or "
            "every device would renew on every check-in."
        )
    return CertPolicy(validity_days, renew_within_days)


def save(session: Session, validity_days: int, renew_within_days: int, *, by: str) -> CertPolicy:
    policy = validate(validity_days, renew_within_days)
    settings_store.put(session, VALIDITY_KEY, str(policy.validity_days), updated_by=by)
    settings_store.put(session, WINDOW_KEY, str(policy.renew_within_days), updated_by=by)
    return policy
