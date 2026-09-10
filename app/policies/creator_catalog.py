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

`subtopics` are display-only — they tell the operator what an *unwired* category
will eventually cover. A wired category's sub-pages come from its spec's
`ui_group` labels instead (W12), so they cannot drift from the form.

`stub_pages` bridges the two (D94): a wired category may still carry a sub-topic
that has no backend yet, rendered as a "coming soon" panel beside its working
ones. Declared here and nowhere else — the editor reads this list, so lighting
one up later means deleting a line rather than editing a template.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StubPage:
    """A sub-topic of a wired category that has no backend yet (D94).

    Rendered before the category's real sub-pages by default — which is how
    "Plugin behavior" sits at the top of ATAK Config while the two configurable
    sub-topics below it work.

    ⚠️ **Set `after` when the operator asked for a different order.** The default
    is a default, not a rule: Tracking and fencing was asked for as *location
    tracking, then geofencing*, and leaving the stub to sort first would have
    silently delivered the reverse. Where a stub belongs is a property of what was
    asked for, so it is declared here rather than inferred from stub-ness (W106).
    """

    slug: str
    label: str
    blurb: str = ""
    #: Slug of the real sub-page this stub should follow. ``None`` puts it first.
    after: str | None = None


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    #: Registry policy type, or None for a placeholder.
    policy_type: str | None = None
    subtopics: tuple[str, ...] = field(default_factory=tuple)
    #: Sub-topics of a *wired* category that are not built yet (D94).
    stub_pages: tuple[StubPage, ...] = field(default_factory=tuple)
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
        "app_management", "App Management", "APP_CATALOG",
        subtopics=(
            "required apps", "blocklist / allowlist", "app catalog",
            "app configurations", "app permissions", "app notifications",
        ),
        blurb="Required apps, blocklist, and allowlist.",
    ),
    Category(
        "kiosk", "Kiosk", "KIOSK",
        subtopics=(
            "single app", "multi app", "background apps", "launcher",
            "permitted features", "peripheral settings", "kiosk exit settings",
            "night mode", "website kiosk settings", "kiosk screensaver",
        ),
        blurb="Lock a device to one app and decide what the user can still reach. "
              "Multi app, launcher, website and screensaver need an ATLAS launcher.",
    ),
    Category(
        "atak_config", "ATAK Config", "ATAK_CONFIG",
        stub_pages=(
            StubPage(
                "plugin-behavior", "Plugin behavior",
                "Which plugins ATAK loads, and how it behaves when one is missing "
                "or built for a different ATAK. Reading a plugin's *settings* "
                "already works — that is the sub-topic below.",
            ),
        ),
        blurb="ATAK's own settings and its plugins', read from the builds in the "
              "app library and delivered through ATAK's enterprise configuration "
              "key — no file push, no Knox.",
    ),
    Category(
        "networks", "Networks", "NETWORKS",
        blurb="Wi-Fi networks. (VPN needs a per-app VPN client — deferred.)",
    ),
    Category(
        "security", "Security", None,
        # ⚠️ Trusted certificates, SCEP and the global HTTP proxy were removed
        # (W113). Not because they were hard: a client certificate reaches no
        # consumer on this fleet without the EAP Wi-Fi support that does not
        # exist here, and Android's own javadoc calls the proxy a
        # *recommendation* that apps may ignore. Shipping either would have
        # looked complete and done nothing. The platform findings are kept in
        # ANDROID_PLATFORM_REFERENCE.md in case this is ever revisited.
        #
        # What is left is unbuilt, so this is an unwired category now and says so
        # the way Accounts and Knox do — `stub_pages` belongs to a *wired*
        # category and would render nothing here (the creator builds panels only
        # for wired categories).
        subtopics=("web content filtering", "os updates"),
        blurb="Update scheduling and content filtering. Both scoped, neither "
              "built yet.",
    ),
    Category("accounts", "Accounts", None, subtopics=("email", "exchange activesync")),
    Category(
        "wallpaper", "Wallpaper", "WALLPAPER",
        subtopics=("tablet", "phone"),
        blurb="Home and lock screen wallpaper, chosen per form factor on the device.",
    ),
    # "wallpaper" has left this placeholder's subtopics — it is a real section now,
    # and listing it in both would offer the operator the same thing twice, once
    # working and once inert.
    Category(
        "configurations", "Configurations", None,
        subtopics=("fonts", "boot/shutdown animation"),
    ),
    Category(
        "customizations", "Customizations", "CUSTOMIZATIONS",
        subtopics=("support message", "lock screen"),
        blurb="Support messages and the lock screen message shown on the device.",
    ),
    Category(
        "network_data_use", "Network data use management", "NETWORK_DATA_USE",
        subtopics=("data usage restrictions", "app-wise restrictions"),
        blurb="Data usage tracking and thresholds. Blocking needs Knox.",
    ),
    Category("app_usage", "App usage management", None),
    Category(
        "file_management", "File management", "FILES",
        blurb="Files placed on the device, ATAK data packages, and terrain data.",
    ),
    Category(
        "tracking_fencing", "Tracking and fencing", "TRACKING_FENCING",
        # Geofencing was a stub here until W106 C4 built it. It is a real sub-page
        # now — one `ui_group` in the spec — and listing it in both places would
        # offer the operator the same thing twice, once working and once inert,
        # which is the mistake the wallpaper note above records.
        blurb="How often a device reports where it is, and the fences it answers to.",
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
