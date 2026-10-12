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

"""The app stores an operator usually wants shut, as blocklist entries (W153).

A tablet that can reach a store can install anything, which is most of the point
of managing it. Naming those packages from memory is the part that goes wrong:
they are not guessable, and **a blocklist entry that names a package the device
does not have blocks nothing and reports nothing** — the policy looks applied
and the store still opens.

⚠️ **These groups expand into the blocklist itself, not into a hidden rule.**
Ticking one writes the package names into the visible list, where an operator can
read them, add a store we missed, or drop one that is wrong. The alternative —
storing a flag and expanding it at apply time — hides the very thing most likely
to be incomplete, and "which packages did that actually block" stops being a
question the page can answer.

Each entry carries the store's name so the list stays readable once expanded.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StoreGroup:
    """One checkbox: a label, why it exists, and what it writes."""

    key: str
    label: str
    help: str
    #: `(package, store name)`, in the order they are written.
    packages: tuple[tuple[str, str], ...]

    @property
    def package_names(self) -> tuple[str, ...]:
        return tuple(package for package, _ in self.packages)


#: ⚠️ The Play *store*, not Play *services*. `com.google.android.gms` is not here
#: and must not be: it backs location, push and SafetyNet, and hiding it breaks
#: far more than app installation — including things ATAK relies on.
PLAY = StoreGroup(
    key="play",
    label="Disable Play Store",
    help="Hides the Google Play app. Play services are untouched, so location, "
    "push and anything else depending on them keep working.",
    packages=(("com.android.vending", "Google Play Store"),),
)

GALAXY = StoreGroup(
    key="galaxy",
    label="Disable Galaxy Store",
    help="Samsung's own store, preinstalled on every Galaxy device. Hidden "
    "rather than removed — a preinstalled app cannot be uninstalled.",
    packages=(
        ("com.sec.android.app.samsungapps", "Samsung Galaxy Store"),
        # Ships beside the store on newer Galaxy builds and can install on its own.
        ("com.samsung.android.app.appsedge", "Samsung Apps Edge"),
    ),
)

#: ⚠️ Not a complete list, and it cannot be: anyone can publish a store. This
#: covers the ones a tablet is likely to arrive with or a user is likely to
#: fetch. The names land in the blocklist where they can be added to.
THIRD_PARTY = StoreGroup(
    key="third_party",
    label="Disable 3rd party stores",
    help="F-Droid, APKPure, Aptoide, Amazon and the OEM stores. Not exhaustive — "
    "anyone can publish a store, so treat this as a starting list and add any "
    "others your fleet has.",
    packages=(
        ("org.fdroid.fdroid", "F-Droid"),
        ("org.fdroid.basic", "F-Droid Basic"),
        ("com.apkpure.aegon", "APKPure"),
        ("com.apkmirror.helper.prod", "APKMirror Installer"),
        ("cm.aptoide.pt", "Aptoide"),
        ("com.amazon.venezia", "Amazon Appstore"),
        ("com.huawei.appmarket", "Huawei AppGallery"),
        ("com.xiaomi.market", "Xiaomi GetApps"),
        ("com.heytap.market", "OPPO / realme App Market"),
        ("com.bbk.appstore", "vivo V-Appstore"),
    ),
)

STORE_GROUPS: tuple[StoreGroup, ...] = (PLAY, GALAXY, THIRD_PARTY)


def group(key: str) -> StoreGroup | None:
    return next((g for g in STORE_GROUPS if g.key == key), None)


def all_packages() -> tuple[str, ...]:
    """Every package any group writes, in group order and without duplicates."""
    seen: list[str] = []
    for store in STORE_GROUPS:
        for package in store.package_names:
            if package not in seen:
                seen.append(package)
    return tuple(seen)
