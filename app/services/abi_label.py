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

"""A build's CPU type in words: "32-bit", "64-bit" (W498).

Operator: "can we add 32bit or 64bit to the app name list?", after a Chrome
build Google Play served as a 32-bit phone was pinned in a policy and an
arm64-only tablet refused it (`INSTALL_FAILED_NO_MATCHING_ABIS`). The raw ABI
names (`armeabi-v7a`) do not say that at a glance.

⚠️ **Three states, as `AppPackageVersion.abis` has them (W96).** None is "never
scanned" and gets no label: saying "any CPU" there would be a claim nobody
checked. Empty is "scanned, no native code", which installs anywhere.
"""

from __future__ import annotations

#: ABI → (family, bits). An ABI not named here (mips, riscv64) is left out of
#: the label rather than guessed at.
_ABIS = {
    "armeabi": ("arm", 32),
    "armeabi-v7a": ("arm", 32),
    "arm64-v8a": ("arm", 64),
    "x86": ("x86", 32),
    "x86_64": ("x86", 64),
}


def bitness(abis: str | None) -> str:
    """"32-bit", "64-bit", "32 + 64-bit", "any CPU", or "" when unknown.

    A build with only x86 code says so ("x86 64-bit"): it runs on no phone or
    tablet this project manages, and "64-bit" alone would hide that.
    """
    if abis is None:
        return ""
    names = [a.strip() for a in abis.split(",") if a.strip()]
    if not names:
        return "any CPU"
    known = [_ABIS[a] for a in names if a in _ABIS]
    if not known:
        return ""
    bits = sorted({b for _, b in known})
    label = " + ".join(str(b) for b in bits) + "-bit"
    if all(family == "x86" for family, _ in known):
        label = "x86 " + label
    return label
