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


from app.artifacts.storage import ArtifactStorage
from app.db.models import Device
from app.services import atak_config
from app.services import knox_license
from app.services import tak_enrollment
from app.services import packages as package_service
from app.security.bundle import BundleSigner
from app.services import effective_policy as eff

# Bumped when the document's shape changes, so an old agent can refuse a format it
# does not understand rather than misapply it.
DESIRED_STATE_SCHEMA_VERSION = 1


def _with_declared_types(
    session: Session, storage: ArtifactStorage, policy: dict[str, Any], device: Device
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

    from app.services import app_config_bundles

    capable = app_config_bundles.supported(device.agent_version)
    enriched = []
    for entry in configs:
        package_name = entry.get("package_name")
        values = dict(entry.get("values") or {})
        types: dict[str, int] = {}
        bundle_types: dict[str, dict[str, int]] = {}
        version = app_config_bundles.newest_version(session, package_name or "")
        if version is not None:
            declared = package_service.declared_config(session, version, storage)
            bundles = app_config_bundles.bundle_keys(values, declared)
            if bundles and not capable:
                # ⚠️ W357: an agent before 0.82.5 rejects a bundle as an error,
                # and a DEGRADED device is refused the agent update that would
                # fix it. Left out here; the device page says what is waiting.
                for key in bundles:
                    values.pop(key, None)
            elif bundles:
                # Each bundle's own settings' types, so the agent can build the
                # nested Bundle the app reads with getBundle (W357).
                nested = package_service.declared_bundles(session, version, storage)
                bundle_types = {key: nested.get(key, {}) for key in bundles}
            # Only the keys this policy actually sets — the device has no use
            # for the other 228 of Chrome's.
            types = {k: t for k, t in declared.items() if k in values}
        out = {**entry, "values": values, "types": types}
        if bundle_types:
            # Additive: absent unless a bundle is configured, so every existing
            # desired state is byte-identical to before.
            out["bundle_types"] = bundle_types
        enriched.append(out)

    return {**policy, "APP_CATALOG": {**catalog, "app_configs": enriched}}


def _with_legacy_bluetooth(policy: dict[str, Any]) -> dict[str, Any]:
    """Also say Bluetooth the pre-W364 way, for agents before 0.85.0.

    ⚠️ W364 replaced RESTRICTIONS' `allow_bluetooth` switch with `bluetooth_mode`.
    An agent before 0.85.0 reads only the switch, and without it would leave
    Bluetooth wherever the last policy put it. "Keep on" allows Bluetooth, so
    an older agent at least does not block it. 0.85.0 reads the mode and ignores
    this key.
    """
    restrictions = policy.get("RESTRICTIONS")
    if not isinstance(restrictions, dict) or restrictions.get("bluetooth_mode") is None:
        return policy
    mode = restrictions["bluetooth_mode"]
    mode = getattr(mode, "value", mode)
    return {**policy, "RESTRICTIONS": {**restrictions, "allow_bluetooth": mode != "block"}}


def _without_tak_server_specs(policy: dict[str, Any]) -> dict[str, Any]:
    """Drop ATAK_CONFIG's TAK Server connections from what the agent receives (W365).

    ⚠️ **They hold every password the policy has**: the enrollment login and both
    certificate passwords. The agent never reads ATAK_CONFIG (D92: it is
    delivered through ATAK's managed configuration, which `merge_into_policy`
    has already filled by now), so the raw list would reach every device for no
    reason. The enrollment password reaches a device only through the plugin's
    list, and only while that device still needs it (S3c).
    """
    spec = policy.get("ATAK_CONFIG")
    if not isinstance(spec, dict) or "tak_servers" not in spec:
        return policy
    return {**policy, "ATAK_CONFIG": {k: v for k, v in spec.items() if k != "tak_servers"}}


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
        # W365: an enrollment password only for the connections this device is
        # due one for, by the marker `effective_policy.refresh` keeps.
        credentials = tak_enrollment.credentials(
            policy, payload.get(tak_enrollment.PAYLOAD_KEY) or {}
        )
        policy = atak_config.merge_into_policy(session, storage, policy, credentials=credentials)
        policy = _with_declared_types(session, storage, policy, device)
    policy = _with_legacy_bluetooth(policy)
    policy = _without_tak_server_specs(policy)

    document: dict[str, Any] = {
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

    # The Knox licence key, for the `knox` build of the agent. Absent on a
    # deployment that has not set one, and ignored by the `aosp` build and by any
    # agent too old to know the key — additive, so no `schema_version` bump and
    # no device in the field refusing a document it cannot parse.
    #
    # ⚠️ **Assembled here rather than carried in the payload, and that is the
    # point.** `eff.refresh` caches its payload as plain JSON per device; the key
    # is sealed in `app_setting` so that a database copy does not contain it, and
    # caching it would hand out N plaintext copies of the thing the sealing
    # protects. What the payload carries is a fingerprint — see
    # `effective_policy.apply_knox_license`.
    #
    # ⚠️ **Determinism is preserved**, which the module docstring requires: the
    # key is fixed for a given `state_version`, because that fingerprint is in the
    # comparison that moves `state_version`. Two builds of the same version are
    # still byte-identical, so the signature is still cacheable.
    # W323: suspend/lock for a device failing its compliance rules. Absent when
    # nothing is due, and additive, so an older agent simply ignores it.
    from app.services import compliance_actions

    enforcement = payload.get(compliance_actions.PAYLOAD_KEY)
    if enforcement:
        document[compliance_actions.PAYLOAD_KEY] = enforcement

    oem = knox_license.bundle_block(session)
    if oem is not None:
        document[knox_license.BUNDLE_KEY] = oem

    return document


def build_signed(
    session: Session,
    device: Device,
    signer: BundleSigner,
    storage: ArtifactStorage | None = None,
) -> dict[str, Any]:
    """Desired state plus its detached Ed25519 signature."""
    document = build(session, device, storage)
    return {"desired_state": document, "signature": signer.sign(document)}
