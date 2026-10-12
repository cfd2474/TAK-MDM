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

"""The web filter's lists, enforced by Chrome itself (W369 FC).

Chrome reads `URLBlocklist` and `URLAllowlist` from its managed configuration,
which ATLAS already pushes. The rules are ours (`web_filter_rules`); this turns
them into Chrome's patterns so Chrome decides every site the way the console's
Test box does.

📖 **What Chrome expects** (Chromium source, read 2026-10-10):
- `generate_policy_source.py` declares every list policy to Android as
  `restrictionType="string"`; `policy_converter.cc` parses that string as a
  JSON array (falling back to comma-separated). So a list travels as
  `'["a","b"]'` in the string-only app configuration.
- `url_util.cc`: a filter `example.com` matches the name **and** its
  subdomains; `.example.com` (leading dot) matches that name only; `*` matches
  everything.
- `url_blocklist_manager.cc` `FilterTakesPrecedence`: a blocklisted `*` is the
  weakest; an exact-name filter beats a subdomain-matching one; a longer host
  beats a shorter one; on a full tie, **allow wins**.

**The translation** (F3c), which keeps every verdict equal to ours by
construction: for every name a rule mentions, Chrome gets **both**
`.name` — our verdict for that exact name — and `name` — our verdict for its
subdomains (asked of a probe subdomain no longer rule can match). Chrome takes
the longest matching name, and for the name itself prefers the exact entry, so
whatever host it is asked about, it lands on one of our own answers. `*` in
the blocklist → `*`. Each Chrome entry is written once, to one list, so
Chrome's allow-wins tie never arises.

⚠️ **Chrome must be told the type.** The agent refuses a managed-configuration
key whose type it does not know (W49), and Chrome is a system app, usually
absent from the library that types come from. These keys are strings to Chrome
on Android (above), so the entry carries `types` for them itself (F3c: Chrome
got nothing until this, and the device was marked DEGRADED).
"""

from __future__ import annotations

import json
from typing import Any

from app.artifacts.app_restrictions import TYPE_STRING
from app.policies import web_filter_rules as rules

CHROME = "com.android.chrome"
BLOCK_KEY = "URLBlocklist"
ALLOW_KEY = "URLAllowlist"
#: 📖 Chromium `DnsOverHttpsMode.yaml`: `supported_on: android:85-`; `off`.
DOH_KEY = "DnsOverHttpsMode"
#: A label no rule can name (not a valid hostname label), so a subdomain built
#: from it matches only rules that cover *every* subdomain of a name.
_PROBE = "-"


def chrome_lists(allowlist: list[str], blocklist: list[str]) -> tuple[list[str], list[str]]:
    """(Chrome blocklist, Chrome allowlist) deciding every site as `evaluate` does."""
    chrome_block: dict[str, None] = {}
    chrome_allow: dict[str, None] = {}
    if rules.STAR in blocklist:
        chrome_block[rules.STAR] = None
    names = dict.fromkeys(rules.name_of(p) for p in [*allowlist, *blocklist] if p != rules.STAR)
    for name in names:
        apex = rules.evaluate(name, allowlist, blocklist).allowed
        subdomains = rules.evaluate(f"{_PROBE}.{name}", allowlist, blocklist).allowed
        (chrome_allow if apex else chrome_block)[f".{name}"] = None
        (chrome_allow if subdomains else chrome_block)[name] = None
    return list(chrome_block), list(chrome_allow)


def _as_list(value: Any) -> list[str]:
    """A Chrome list value as an operator may have typed it: JSON, or comma-separated."""
    if isinstance(value, list):
        return [str(v) for v in value]
    text = str(value or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    if isinstance(parsed, list):
        return [str(v) for v in parsed]
    return [part.strip() for part in text.split(",") if part.strip()]


def merge_into_policy(policy: dict[str, Any]) -> dict[str, Any]:
    """Add the web filter's lists to Chrome's managed configuration.

    ⚠️ **Added to, never replacing, what an operator set by hand.** Chrome's own
    `URLBlocklist` in App configurations keeps every entry; ours are appended.
    Both are Chrome patterns, so the union means what each one meant.

    No WEB_FILTER, or empty lists: the policy is returned untouched, so a fleet
    without web filtering gets byte-identical desired state.
    """
    spec = policy.get("WEB_FILTER") or {}
    allow, block = spec.get("allowlist") or [], spec.get("blocklist") or []
    if not allow and not block:
        return policy
    chrome_block, chrome_allow = chrome_lists(allow, block)

    catalog = dict(policy.get("APP_CATALOG") or {})
    configs = [dict(c) for c in catalog.get("app_configs") or []]
    entry = next((c for c in configs if c.get("package_name") == CHROME), None)
    if entry is None:
        entry = {"package_name": CHROME, "values": {}}
        configs.append(entry)
    values = dict(entry.get("values") or {})
    for key, ours in ((BLOCK_KEY, chrome_block), (ALLOW_KEY, chrome_allow)):
        combined = list(dict.fromkeys([*_as_list(values.get(key)), *ours]))
        if combined:
            values[key] = json.dumps(combined)
    # ⚠️ W369 F0: Chrome's own secure DNS sends lookups straight to its provider,
    # around the ATLAS filter. Off whenever web-filter rules apply, over any
    # value an operator set by hand (the filter depends on it).
    values[DOH_KEY] = "off"
    entry["values"] = values
    entry["types"] = {
        **(entry.get("types") or {}),
        **{key: TYPE_STRING for key in (BLOCK_KEY, ALLOW_KEY, DOH_KEY) if key in values},
    }
    catalog["app_configs"] = configs
    return {**policy, "APP_CATALOG": catalog}
