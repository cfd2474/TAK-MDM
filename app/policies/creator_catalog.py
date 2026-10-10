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
    #: A fixed platform notice shown at the top of every page of this category
    #: (W361 C3). Not `warnings`, which are computed from the values entered:
    #: this holds whatever the values are.
    notice: str = ""
    #: Edited somewhere of its own, and never offered in the policy creator.
    #:
    #: ⚠️ **Breach mode is the reason this exists.** A `BREACH` section names
    #: directories to delete. Offered in the ordinary creator, an operator could
    #: put one in a normal profile and empty those directories on every device
    #: that profile reaches — with no breach, no confirmation and no button
    #: pressed. It belongs on one page, which asks for it by key.
    reserved: bool = False

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
    Category(
        "knox", "Knox Configurations", None,
        # ⚠️ W322 (operator, 2026-10-02): fonts and the boot/shutdown animation
        # moved here from the old "Configurations" category, and OS updates from
        # "Security", "as these are part of the knox requirements". Both those
        # categories are gone; so are Accounts and App usage management.
        subtopics=("fonts", "boot/shutdown animation", "os updates"),
        blurb="Samsung Knox policy: fonts, boot and shutdown animations, and OS "
              "update scheduling.",
    ),
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
        # "Plugin behavior" was a stub here until W304 made it a real page: the
        # `auto_load_plugins` field, declared first so it keeps its place.
        blurb="ATAK's own settings and its plugins', read from the builds in the "
              "app library and delivered through ATAK's enterprise configuration "
              "key — no file push, no Knox.",
    ),
    Category(
        "networks", "Networks", "NETWORKS",
        blurb="Wi-Fi networks. (VPN needs a per-app VPN client — deferred.)",
    ),
    # ⚠️ No "Security" category (W322). Trusted certificates, SCEP and the global
    # HTTP proxy were removed in W113: a client certificate reaches no consumer
    # on this fleet without EAP Wi-Fi, and Android calls the proxy a
    # *recommendation* apps may ignore (findings kept in
    # ANDROID_PLATFORM_REFERENCE.md). What was left went in W322: OS updates to
    # Knox, web content filtering dropped by the operator. ⚠️ Web filtering came
    # back as its own category in W369, on the operator's request, built on a
    # local VPN and Chrome's own lists rather than a Knox or proxy route.
    Category(
        "wallpaper", "Wallpaper", "WALLPAPER",
        subtopics=("tablet", "phone"),
        blurb="Home and lock screen wallpaper, chosen per form factor on the device.",
        # ⚠️ On the category, not only the phone field: a policy with a tablet
        # image alone applies it to phones too (W361 C3).
        notice=(
            "Samsung phones (One UI): a wallpaper set by ATLAS, or by any "
            "management app, turns sideways in landscape until someone sets a "
            "wallpaper once through Samsung's own app. The phone shows a "
            "'Finish wallpaper setup' notification for this: tap it, then Next "
            "and Done. Once per phone, whichever image the policy uses. "
            "Landscape crops the top and bottom, so keep badges and text in the "
            "centre band."
        ),
    ),
    Category(
        "web_filter", "Web Filtering", "WEB_FILTER",
        blurb="Allowed and blocked websites, by name.",
        # ⚠️ Said on every page until enforcement ships (W369 FC/F3): a saved
        # list must never be mistaken for one a device is enforcing.
        notice=(
            "Not enforced on devices yet. These lists are saved and delivered, "
            "and the Test box shows what they would do; Chrome's own filtering "
            "and the ATLAS filter app follow in later updates. Filtering is by "
            "site name: it cannot see pages, paths or anything inside HTTPS."
        ),
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
    Category(
        "breach", "Breach mode", "BREACH",
        reserved=True,
        blurb="Directories emptied on a device reported lost or stolen.",
    ),
    Category(
        "compliance", "Compliance", "COMPLIANCE",
        # Was the "Android Enterprise compliance" placeholder; renamed by the
        # operator (W323), because none of it needs Android Enterprise.
        blurb="Rules a device must keep meeting. A device that fails one shows as "
              "non-compliant, with the rule, and the operator is alerted.",
    ),
    # "Troubleshooting" (app logs, remote access management) was a placeholder
    # with nothing behind it, removed at the operator's request (W354). Logs are
    # collected from the device page, not set by policy.
)

_BY_KEY = {c.key: c for c in CATALOG}
_BY_TYPE = {c.policy_type: c for c in CATALOG if c.policy_type}


def get(key: str) -> Category | None:
    return _BY_KEY.get(key)


def for_policy_type(policy_type: str) -> Category | None:
    return _BY_TYPE.get(policy_type)


def wired_categories(include_reserved: bool = False) -> list[Category]:
    """Categories the policy creator offers.

    ⚠️ Reserved ones are excluded by **default**, so a caller that has not
    thought about it cannot put breach mode into an ordinary profile.
    """
    return [c for c in CATALOG if c.wired and (include_reserved or not c.reserved)]
