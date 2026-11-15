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

"""The web filter's lists, delivered to the ATLAS filter app (W369 F3).

Through the managed configuration the agent already applies to apps
(`APP_CATALOG.app_configs`), with the keys the filter declares in its own
`app_restrictions.xml`: `allowlist`, `blocklist`, `always_allow` (JSON arrays in
strings) and `config_version`.

**`always_allow`**: names no list can block, so a `*` cannot cut a device off
from its own management or its TAK Server. The ATLAS server's host and every
TAK Server host the policy configures. Exact names only.

**`config_version`**: a short hash of exactly what the filter receives, so the
console can tell which lists a device is running.

The desired state also carries a small `web_filter` marker for the agent,
saying which package to make always-on and which version to expect. Absent when
no rules apply, so every other device's document is byte-identical to before.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import urlsplit

from app.policies.specs import web_filter as web_filter_spec
from app.services.reserved_packages import ATLAS_FILTER_PACKAGE

PAYLOAD_KEY = "web_filter"


def _rules(policy: dict[str, Any]) -> tuple[list[str], list[str]]:
    spec = policy.get("WEB_FILTER") or {}
    return list(spec.get("allowlist") or []), list(spec.get("blocklist") or [])


def always_allow(policy: dict[str, Any], server_url: str) -> list[str]:
    names: set[str] = set()
    host = urlsplit(server_url).hostname
    if host:
        names.add(host.lower().rstrip("."))
    for connection in (policy.get("ATAK_CONFIG") or {}).get("tak_servers") or []:
        tak_host = (connection or {}).get("host")
        if tak_host:
            names.add(str(tak_host).lower().rstrip("."))
    return sorted(names)


def config_values(policy: dict[str, Any], server_url: str) -> dict[str, str] | None:
    """What the filter app receives, or None when the policy asks nothing of it."""
    spec = policy.get("WEB_FILTER") or {}
    if not web_filter_spec.in_use(spec):
        return None
    allow, block = _rules(policy)
    values = {
        "allowlist": json.dumps(allow),
        "blocklist": json.dumps(block),
        "always_allow": json.dumps(always_allow(policy, server_url)),
        # W379: "off", or the YouTube level Safe search runs at. Always sent,
        # so turning it off is a changed value the filter acts on.
        "safe_search": web_filter_spec.safe_search_level(spec) or "off",
    }
    digest = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()[:12]
    return {**values, "config_version": digest}


def merge_into_policy(policy: dict[str, Any], server_url: str) -> dict[str, Any]:
    """The filter's managed configuration added to `APP_CATALOG.app_configs`.

    ⚠️ The filter is a reserved package, so no operator entry for it can exist;
    any found is replaced, never merged.
    """
    values = config_values(policy, server_url)
    if values is None:
        return policy
    catalog = dict(policy.get("APP_CATALOG") or {})
    configs = [c for c in catalog.get("app_configs") or [] if c.get("package_name") != ATLAS_FILTER_PACKAGE]
    configs.append({"package_name": ATLAS_FILTER_PACKAGE, "values": values})
    catalog["app_configs"] = configs
    return {**policy, "APP_CATALOG": catalog}


def marker(policy: dict[str, Any], server_url: str) -> dict[str, str] | None:
    """The agent's cue to enforce: which package, and which lists to expect."""
    values = config_values(policy, server_url)
    if values is None:
        return None
    return {"package": ATLAS_FILTER_PACKAGE, "config_version": values["config_version"]}
