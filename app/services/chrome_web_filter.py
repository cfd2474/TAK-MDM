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

**The translation**, which keeps every verdict equal to ours (tested by
simulating Chrome's precedence over every name the rules mention):
- our exact `example.com` → Chrome `.example.com`;
- our `*.example.com` (subdomains only) → Chrome `example.com`, plus a
  `.example.com` pin in whichever list our own rules put the bare name, since
  Chrome's `example.com` would otherwise decide it too;
- `*` → `*`;
- a pattern on both lists is left out of Chrome's allowlist: we block a tie,
  Chrome would allow it.
"""

from __future__ import annotations

import json
from typing import Any

from app.policies import web_filter_rules as rules

CHROME = "com.android.chrome"
BLOCK_KEY = "URLBlocklist"
ALLOW_KEY = "URLAllowlist"


def chrome_lists(allowlist: list[str], blocklist: list[str]) -> tuple[list[str], list[str]]:
    """(Chrome blocklist, Chrome allowlist) deciding every site as `evaluate` does."""
    exact = {p for p in [*allowlist, *blocklist] if p != rules.STAR and not p.startswith("*.")}

    chrome_block: dict[str, None] = {}
    chrome_allow: dict[str, None] = {}

    def translate(pattern: str, into: dict[str, None]) -> None:
        if pattern == rules.STAR:
            into[rules.STAR] = None
        elif pattern.startswith("*."):
            suffix = pattern[2:]
            into[suffix] = None
            if suffix not in exact:
                pin = chrome_allow if rules.evaluate(suffix, allowlist, blocklist).allowed else chrome_block
                pin[f".{suffix}"] = None
        else:
            into[f".{pattern}"] = None

    for pattern in blocklist:
        translate(pattern, chrome_block)
    for pattern in allowlist:
        translate(pattern, chrome_allow)
    # Anything on both sides is blocked: we block a tie, and Chrome would let
    # the allow win. That covers the same pattern on both lists, and a pin
    # landing on both sides when two wildcards share a suffix.
    for name in list(chrome_allow):
        if name in chrome_block:
            del chrome_allow[name]
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
    entry["values"] = values
    catalog["app_configs"] = configs
    return {**policy, "APP_CATALOG": catalog}
