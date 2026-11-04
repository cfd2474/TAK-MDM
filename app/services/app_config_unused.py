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

"""Managed-configuration keys an app's build no longer declares (W444).

Operator, after a newer Chrome went into the library: an error on every
device, and "2 saved keys this build of the app no longer declares are kept
unchanged: AutofillAddressEnabled, AutofillCreditCardEnabled … we need a way
to dump managed configs that are no longer used".

The app does not read a key it does not declare, so sending one does
nothing for the app; and the agent refuses an untyped key as an apply error
(`AppConfigPlan.coerce`), which is the error. So such a key is **not sent**,
and the console lists it with a way to remove it.

⚠️ **Only when the build declares a schema.** `declared_config` returns `{}`
for "declares nothing" and for "could not be read" alike, and a build never
scanned has no declaration at all. In those cases nothing is known about the
key, and it is sent as before: refusing it on the device is the honest
answer there (W49).

⚠️ **A key with a type of its own is never "unused":** one typed in by hand
(W405 `custom_types`), or carried with its type by the entry (W369's Chrome
web-filter keys). Those are deliberate, whatever the build says.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy.orm import Session


def undeclared(declared: Mapping[str, int], values: Mapping[str, Any], typed: Iterable[str] = ()) -> list[str]:
    """The keys in `values` this build does not declare and nothing else types, sorted."""
    if not declared:
        return []
    typed = set(typed)
    return sorted(k for k in values if k not in declared and k not in typed)


def own_types(entry: Mapping[str, Any]) -> set[str]:
    """The keys an entry types itself: W369's `types`, W405's `custom_types`."""
    return set(entry.get("types") or {}) | set(entry.get("custom_types") or {})


def stored_declaration(session: Session, package_name: str) -> dict[str, int]:
    """The library's newest build's declaration, as stored; `{}` when not scanned.

    Never scans: this runs on page renders, and an unscanned build is the
    "nothing is known" case anyway.
    """
    from app.services import app_config_bundles

    version = app_config_bundles.newest_version(session, package_name)
    if version is None or not version.declared_config:
        return {}
    try:
        declared = json.loads(version.declared_config)
    except ValueError:
        return {}
    return declared if isinstance(declared, dict) else {}


def for_entry(session: Session, entry: Mapping[str, Any]) -> list[str]:
    """A saved configuration's keys the library's build no longer declares."""
    declared = stored_declaration(session, entry.get("package_name") or "")
    return undeclared(declared, entry.get("values") or {}, own_types(entry))
