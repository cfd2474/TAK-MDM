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

"""A geofence may only demand a lock the operator has actually defined (W106).

⚠️ **The hole this closes.** A fence's password requirement is a *floor* — quality
`SOMETHING`, meaning "any lock at all". With a PASSWORD policy beside it that
floor is the operator's own rule, already chosen and already written down. Without
one it is the only thing in play, so the device prompts whoever is holding it to
invent a PIN, and what they invent is the fleet's password policy. The operator
has enforced a lock and specified nothing about it.

Operator, 2026-09-08: *"can we mandate that it be tied to the password policy if
enabled? as in it requires a password policy be set in the same policy before it
allows the geofence lock?"*

⚠️ **"The same policy" means the same profile, and that is the strict reading on
purpose.** A `PASSWORD` policy assigned separately to the same device would also
reach it — the resolver merges everything assigned — but it can be unassigned
independently, which would leave the fence still demanding a lock with no rules
behind it. That is the very state this exists to prevent, so the two have to
travel together.

The rule is enforced at four points, and the fourth is the one that looks like it
does not need it: creating a profile, updating a section, **removing the password
section**, and creating a standalone policy. Without the third, an operator could
satisfy the rule and then delete the Password tab.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

#: Catalog keys, not policy types — this reasons about the profile's tabs.
TRACKING_KEY = "tracking_fencing"
PASSWORD_KEY = "password"


def _fence_password(fence: Mapping[str, Any]) -> str:
    """This fence's password setting, reading the pre-W111 boolean too."""
    if "password" in fence:
        value = fence.get("password")
        return str(getattr(value, "value", value) or "none").lower()
    return "on" if _truthy(fence.get("password_enforced")) else "none"


def _named(fences: Any, wanted: str) -> list[str]:
    if not isinstance(fences, Iterable):
        return []
    names: list[str] = []
    for index, fence in enumerate(fences):
        if not isinstance(fence, Mapping):
            continue
        if _fence_password(fence) == wanted:
            names.append(str(fence.get("name") or f"fence {index + 1}"))
    return names


def password_fences(tracking_spec: Mapping[str, Any] | None) -> list[str]:
    """Names of fences in this spec that demand a lock."""
    if not tracking_spec:
        return []
    return _named(tracking_spec.get("geofences") or [], "on")


def suspending_fences(tracking_spec: Mapping[str, Any] | None) -> list[str]:
    """Names of fences that suspend the passcode — trusted areas (W111)."""
    if not tracking_spec:
        return []
    return _named(tracking_spec.get("geofences") or [], "off")


def sets_a_passcode(password_spec: Mapping[str, Any] | None) -> bool:
    """Does this PASSWORD policy set the passcode itself?

    ⚠️ **The condition that makes a trusted area safe.** Suspending works by
    clearing the passcode *this system set* and putting it back on the way out.
    Where the user chose their own PIN there is nothing to put back — clearing it
    would lock them out of their own credential permanently.
    """
    if not password_spec:
        return False
    return bool(str(password_spec.get("set_password") or "").strip())


def _truthy(value: Any) -> bool:
    """The form layer may not have coerced yet, so a string counts.

    ⚠️ Called on both validated specs and raw form output. Reading the string
    ``"true"`` as falsey would let a fence through the check and then have it
    coerced to ``True`` a moment later by the model — the check would pass on a
    value different from the one that gets stored.
    """
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def has_password_policy(password_spec: Mapping[str, Any] | None) -> bool:
    """Is there a real password policy here, rather than an empty section?

    An empty spec is not a policy. A section that exists but says nothing would
    satisfy a presence check while defining exactly as little as no section at
    all — which is the thing being guarded against, not a technicality.
    """
    return bool(password_spec)


def violation(
    tracking_spec: Mapping[str, Any] | None,
    password_spec: Mapping[str, Any] | None,
) -> str | None:
    """The message to refuse with, or None if this combination is allowed."""
    suspending = suspending_fences(tracking_spec)
    if suspending and not sets_a_passcode(password_spec):
        listed = ", ".join(repr(name) for name in suspending)
        many = len(suspending) > 1
        return (
            f"the {'geofences' if many else 'geofence'} {listed} "
            f"{'suspend' if many else 'suspends'} the passcode, so this profile's "
            "Password policy has to set one. A trusted area works by clearing the "
            "passcode this policy applied and putting it back on the way out — "
            "with nothing set here there is nothing to restore, and a PIN the user "
            "chose themselves cannot be removed at all."
        )

    demanding = password_fences(tracking_spec)
    if not demanding:
        return None
    if has_password_policy(password_spec):
        return None

    listed = ", ".join(repr(name) for name in demanding)
    many = len(demanding) > 1
    plural = "geofences" if many else "geofence"
    verb = "require" if many else "requires"
    return (
        f"the {plural} {listed} {verb} a password, so this profile needs a "
        "Password policy as well. A geofence lock on its own only tells the "
        "device that some lock is needed — whoever is holding it then chooses "
        "the PIN, and that becomes the rule. Add a Password section, or set "
        "Password enforced to No."
    )


def check_sections(sections: Mapping[str, Mapping[str, Any]]) -> str | None:
    """The rule over a whole set of profile sections, keyed by catalog key."""
    return violation(sections.get(TRACKING_KEY), sections.get(PASSWORD_KEY))


def blocks_password_removal(tracking_spec: Mapping[str, Any] | None) -> str | None:
    """Refusal message when removing the Password section would strand a fence.

    ⚠️ The point of this one is that it is invisible until someone tries it. Every
    other check runs while an operator is editing geofences and thinking about
    them; this one fires from an entirely different tab, minutes later, and the
    thing it protects is not on screen.
    """
    demanding = password_fences(tracking_spec) + suspending_fences(tracking_spec)
    if not demanding:
        return None

    listed = ", ".join(repr(name) for name in demanding)
    many = len(demanding) > 1
    plural = "geofences" if many else "geofence"
    verb = "depend on" if many else "depends on"
    return (
        f"this profile's {plural} {listed} {verb} a password, so its Password "
        "section cannot be removed while they do. Set Password enforced to No on "
        f"the {plural} first."
    )
