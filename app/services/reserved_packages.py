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

"""ATLAS's own apps, which no policy, app group or storefront may name (W273).

Two packages reach a device by other means, and choosing them anywhere else is
at best redundant and at worst severs the device from ATLAS:

* **The agent** is installed and made Device Owner by provisioning. It adds
  itself to the lock-task allowlist on the device, so a kiosk never needs it
  named. ⚠️ Nothing on the device protects it from a *block list* or a
  *per-app data cut* -- a policy naming it there would take the device off
  the management channel it would need to undo that.
* **The launcher** is required automatically whenever a multi-app kiosk is
  set (`effective_policy`), with ATLAS choosing the build.
* **The ATLAS ATAK plugin** (W300) is required automatically wherever a
  policy installs ATAK, with ATLAS choosing the build for that ATAK line
  (`atlas_plugin`).

So the rule is enforced twice: pickers never offer these, and
`registry.validate_spec` refuses them from any save path -- the console, the
API, and profile sections alike.
"""

from __future__ import annotations

#: The ATLAS launcher (W68). A separate APK, required only by a multi-app kiosk.
#: Must match `PolicyApplier.LAUNCHER_PACKAGE` in the agent -- the two are one
#: contract expressed in two languages, and a typo here is a kiosk that never
#: locks. `effective_policy.ATLAS_LAUNCHER_PACKAGE` re-exports this.
ATLAS_LAUNCHER_PACKAGE = "com.taksolutions.atlaslauncher"

#: Spec keys whose values are app package names. `data_packages` is absent on
#: purpose: those are ATAK data packages -- files -- not apps.
_SINGLE_KEYS = frozenset({"package_name", "kiosk_package"})
_LIST_KEYS = frozenset(
    {"blocked_packages", "allowed_packages", "background_packages", "auto_load_plugins"}
)


def reserved() -> dict[str, str]:
    """Reserved package name -> why an operator never chooses it.

    The agent's name is a setting, so it is read at call time rather than
    frozen at import.
    """
    from app.config import get_settings
    from app.services import atlas_plugin

    return {
        get_settings().agent_package_name: (
            "ATLAS MDM itself, installed during provisioning"
        ),
        ATLAS_LAUNCHER_PACKAGE: (
            "the ATLAS launcher, applied automatically as the multi-app kiosk"
        ),
        atlas_plugin.PACKAGE: (
            "the ATLAS ATAK plugin, installed automatically with ATAK"
        ),
    }


def is_reserved(package_name: str | None) -> bool:
    return bool(package_name) and package_name in reserved()


def why(package_name: str) -> str:
    """A sentence an operator can act on, for a refused save."""
    return (
        f"{package_name} is {reserved()[package_name]}, so it cannot be "
        "chosen here."
    )


def why_kept(package_name: str) -> str:
    """A sentence for a refused delete (W286)."""
    return (
        f"{package_name} is {reserved()[package_name]}. It ships with ATLAS "
        "and cannot be deleted from the library."
    )


def named_in(spec: object) -> list[str]:
    """Every reserved package a stored spec names in an app field, in order.

    Walks the whole structure, so a package inside a list of tiles or app
    entries is found the same as a top-level field.

    ⚠️ **One exemption, and it is the console tile (W197).** A multi-app kiosk
    carries the ATLAS *console* -- the agent's own package -- as a tile the
    operator can see and reorder but not remove. That is placement on the
    kiosk grid, not choosing an app to deploy, so the agent is allowed as a
    `package_name` inside `multi_app_packages` and nowhere else. The launcher
    gets no such exemption: it *is* the kiosk home screen and has no position
    in its own grid.
    """
    from app.config import get_settings

    found: list[str] = []
    banned = reserved()
    console = get_settings().agent_package_name

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "multi_app_packages" and isinstance(value, list):
                    for tile in value:
                        name = (tile or {}).get("package_name") if isinstance(tile, dict) else None
                        if isinstance(name, str) and name in banned and name != console:
                            found.append(name)
                elif key in _SINGLE_KEYS and isinstance(value, str) and value in banned:
                    found.append(value)
                elif key in _LIST_KEYS and isinstance(value, list):
                    found.extend(v for v in value if isinstance(v, str) and v in banned)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(spec)
    return found
