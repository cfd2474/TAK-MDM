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

from app.db.models import Device
from app.security.bundle import BundleSigner
from app.services import effective_policy as eff

# Bumped when the document's shape changes, so an old agent can refuse a format it
# does not understand rather than misapply it.
DESIRED_STATE_SCHEMA_VERSION = 1


def build(session: Session, device: Device) -> dict[str, Any]:
    """The declarative state this device should converge on. Deterministic."""
    payload = eff.get_effective(session, device)

    return {
        "schema_version": DESIRED_STATE_SCHEMA_VERSION,
        "device_id": str(device.id),
        "state_version": device.state_version,
        # Values only — no provenance, no conflicts, no policy names.
        "policy": payload.get("values", {}),
    }


def build_signed(session: Session, device: Device, signer: BundleSigner) -> dict[str, Any]:
    """Desired state plus its detached Ed25519 signature."""
    document = build(session, device)
    return {"desired_state": document, "signature": signer.sign(document)}
