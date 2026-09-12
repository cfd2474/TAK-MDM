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

"""Builds the device-facing desired-state document.

This is a *projection* of the effective policy, not the same object. The admin view
carries provenance, conflicts, and the assignments considered — everything needed to
answer "why is this value set?". The device needs none of it, and shipping it would
leak the fleet's policy structure (policy names, group topology, rank ordering) onto
every tablet, including any that gets lost.

So the device receives values only, plus the version it must converge on.

**The signed document is deterministic** for a given ``(device, state_version)``:
no timestamp, no nonce. Because ``state_version`` moves exactly when the resolved
values move (D17), the same version always yields byte-identical JSON and therefore
the same signature. That makes a bundle a cacheable, relayable artifact rather than
something that must be re-signed per request — which is the whole point of signing
independently of TLS (D9). Anything genuinely per-response, like the generation
timestamp, belongs in the envelope around the bundle, not inside it.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from sqlalchemy import select

from app.artifacts.storage import ArtifactStorage
from app.db.models import AppPackage, Device
from app.services import atak_config
from app.services import packages as package_service
from app.security.bundle import BundleSigner
from app.services import effective_policy as eff

# Bumped when the document's shape changes, so an old agent can refuse a format it
# does not understand rather than misapply it.
DESIRED_STATE_SCHEMA_VERSION = 1


def _with_declared_types(
    session: Session, storage: ArtifactStorage, policy: dict[str, Any]
) -> dict[str, Any]:
    """Attach each configured key's declared type to APP_CATALOG.app_configs (W49).

    ⚠️ **The device cannot coerce without this.** A Bundle holding the string
    "300" returns 0 from `getInt`, and "true" returns false from `getBoolean` —
    the app falls back to its own default and nothing reports a fault. Nor can the
    agent guess: "looks numeric" would corrupt a *string* key whose value happens
    to be digits, which is exactly the shape of Butterfly's
    `ApprovedEnterpriseDeviceSecret`.

    The type comes from the build being deployed, so it always describes the APK
    the device will actually run.
    """
    catalog = policy.get("APP_CATALOG")
    configs = (catalog or {}).get("app_configs")
    if not configs:
        return policy

    enriched = []
    for entry in configs:
        package_name = entry.get("package_name")
        types: dict[str, int] = {}
        package = session.scalar(
            select(AppPackage).where(AppPackage.package_name == package_name)
        )
        if package is not None:
            version = package_service.newest(session, package)
            if version is not None:
                declared = package_service.declared_config(session, version, storage)
                # Only the keys this policy actually sets — the device has no use
                # for the other 228 of Chrome's.
                types = {k: t for k, t in declared.items() if k in entry.get("values", {})}
        enriched.append({**entry, "types": types})

    return {**policy, "APP_CATALOG": {**catalog, "app_configs": enriched}}


def build(
    session: Session, device: Device, storage: ArtifactStorage | None = None
) -> dict[str, Any]:
    """The declarative state this device should converge on. Deterministic."""
    payload = eff.get_effective(session, device)
    policy = payload.get("values", {})
    if storage is not None:
        # ⚠️ Order matters. ATAK_CONFIG resolves into APP_CATALOG.app_configs
        # (D92), so it has to land *before* the types are attached — ATAK declares
        # `enterpriseConfigurationPreferences` itself, and running the enrichment
        # afterwards is what gives the generated document its declared type
        # without a second place that has to know what that type is.
        policy = atak_config.merge_into_policy(session, storage, policy)
        policy = _with_declared_types(session, storage, policy)

    return {
        "schema_version": DESIRED_STATE_SCHEMA_VERSION,
        "device_id": str(device.id),
        "state_version": device.state_version,
        # Values only — no provenance, no conflicts, no policy names.
        "policy": policy,
        # Required apps resolved to concrete artifacts: hashes to verify against and
        # URLs to fetch. The policy says what; this says exactly which bytes.
        "apps": payload.get("apps", []),
        # The ATLAS store: apps the user *may* install, never ones the agent should
        # install itself (W56).
        #
        # ⚠️ A sibling key rather than reshaping `apps` into {required, available}
        # like `files`. The reshape would need a `schema_version` bump, and the
        # whole purpose of that number is to make an older agent **refuse** a
        # document it does not understand — which would strand every device in the
        # field over a purely additive change. An agent that has not learned about
        # the store simply ignores this.
        "store": payload.get("store", []),
        # Split into what the agent must install and what it should offer the user
        # in the marketplace (F4).
        "files": payload.get("files", {"required": [], "available": []}),
        # Both wallpaper slots when both are set: the device chooses by its own
        # screen (D46) and downloads only the one it uses.
        "wallpaper": payload.get("wallpaper", {}),
    }


def build_signed(
    session: Session,
    device: Device,
    signer: BundleSigner,
    storage: ArtifactStorage | None = None,
) -> dict[str, Any]:
    """Desired state plus its detached Ed25519 signature."""
    document = build(session, device, storage)
    return {"desired_state": document, "signature": signer.sign(document)}
