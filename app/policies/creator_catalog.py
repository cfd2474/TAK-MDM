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

"""The policy-creator category tree.

One flat list of categories, each either wired to a real policy type from the
registry or flagged a placeholder. The profile creator and editor render this
directly, so adding a category (or lighting one up when its backend lands) is a
one-line change here and nothing else (OCP).

`subtopics` are display-only for now — they tell the operator what a category will
eventually cover. A wired category's whole spec is still edited as one JSON
document (D64), so the subtopics do not yet split into separate forms.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    #: Registry policy type, or None for a placeholder.
    policy_type: str | None = None
    subtopics: tuple[str, ...] = field(default_factory=tuple)
    blurb: str = ""

    @property
    def wired(self) -> bool:
        return self.policy_type is not None


CATALOG: tuple[Category, ...] = (
    Category(
        "password", "Password", "PASSWORD",
        blurb="Passcode strength, expiry, and lockout.",
    ),
    Category(
        "restrictions", "Restrictions", "RESTRICTIONS",
        subtopics=("basic", "advanced"),
        blurb="Device feature restrictions and screen timeout.",
    ),
    Category("knox", "Knox Configurations", None, blurb="Samsung Knox policy. Placeholder."),
    Category(
        "periodic_sync", "Periodic sync", "PERIODIC_SYNC",
        blurb="Foreground or background service for the agent's periodic check-in.",
    ),
    Category(
        "app_management", "App Management", "APP_CATALOG",
        subtopics=(
            "required apps", "blocklist / allowlist", "app catalog",
            "app configurations", "app permissions", "app notifications",
        ),
        blurb="Required apps, blocklist, allowlist, and kiosk app.",
    ),
    Category("networks", "Networks", None, subtopics=("wifi", "vpn")),
    Category(
        "security", "Security", None,
        subtopics=(
            "certificates", "scep", "global http proxy",
            "web content filtering", "os updates",
        ),
    ),
    Category("accounts", "Accounts", None, subtopics=("email", "exchange activesync")),
    Category(
        "configurations", "Configurations", None,
        subtopics=("fonts", "wallpaper", "boot/shutdown animation"),
    ),
    Category("customizations", "Customizations", None, subtopics=("support message", "lock screen")),
    Category("network_data_use", "Network data use management", None),
    Category("app_usage", "App usage management", None),
    Category(
        "file_management", "File management", "FILES",
        blurb="Files placed on the device, required or offered in the marketplace.",
    ),
    Category(
        "tracking_fencing", "Tracking and fencing", None,
        subtopics=("location tracking", "geofencing"),
    ),
    Category("android_enterprise", "Android Enterprise compliance", None, blurb="Placeholder."),
    Category(
        "troubleshooting", "Troubleshooting", None,
        subtopics=("app logs", "remote access management"),
    ),
)

_BY_KEY = {c.key: c for c in CATALOG}
_BY_TYPE = {c.policy_type: c for c in CATALOG if c.policy_type}


def get(key: str) -> Category | None:
    return _BY_KEY.get(key)


def for_policy_type(policy_type: str) -> Category | None:
    return _BY_TYPE.get(policy_type)


def wired_categories() -> list[Category]:
    return [c for c in CATALOG if c.wired]
