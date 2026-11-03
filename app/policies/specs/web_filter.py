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

"""WEB_FILTER policy spec (W369).

Headwind-style lists: an allowlist and a blocklist of hostnames, one pattern
per entry, with ``*`` in the blocklist meaning "deny whatever is not allowed".
What each pattern means, and which wins, lives in
:mod:`app.policies.web_filter_rules`.

⚠️ **One list, several enforcers.** The same rules drive Chrome's own URL
lists (W369 FC, `app/services/chrome_web_filter.py`) and, later, the ATLAS
filter app's DNS filter (F2/F3). The category says which enforce today, so a
Chrome-only filter is never mistaken for a device-wide one.

**Stacked policies combine both lists (union).** Precedence is decided per
host, by the most specific rule, so adding a policy can never make a rule
another policy wrote mean something else: an exact allow still beats a ``*``,
and the same pattern on both lists still blocks.
"""

from __future__ import annotations

import enum
from typing import Annotated, Any

from pydantic import Field, field_validator, model_validator

from app.policies import web_filter_rules as rules
from app.policies.specs.base import PolicySpec
from app.policies.strategies import Merge, MergeStrategy

_GROUP = "Web filtering"
_SAFE = "Safe search"


class YouTubeRestrict(str, enum.Enum):
    """YouTube's restricted mode under Safe search (W379). The values sort
    in strictness order, so a MAX merge keeps the stricter."""

    MODERATE = "moderate"
    STRICT = "strict"


def safe_search_level(spec: dict[str, Any] | None) -> str | None:
    """The YouTube level when Safe search is on ("moderate" by default), else None."""
    spec = spec or {}
    if not spec.get("safe_search"):
        return None
    return str(spec.get("youtube_restrict") or YouTubeRestrict.MODERATE.value)


def in_use(spec: dict[str, Any] | None) -> bool:
    """Whether a resolved WEB_FILTER asks the device for anything: rules, or
    Safe search. One answer for every enforcer (the filter app, Chrome)."""
    spec = spec or {}
    return bool(spec.get("allowlist") or spec.get("blocklist") or safe_search_level(spec))


class WebFilterSpec(PolicySpec):
    allowlist: Annotated[
        list[str] | None,
        Merge(MergeStrategy.UNION, note="Every policy's allowed sites count."),
    ] = Field(
        default=None,
        title="Allowed sites",
        description=(
            "One per line. example.com is the whole site, www.example.com and "
            "every other subdomain included; .example.com (leading dot) is that "
            "name only; *.example.com is its subdomains, not example.com itself. "
            "An allowed site wins over a * block and over any broader block. "
            "Lines starting with # are notes."
        ),
        json_schema_extra={"ui_group": _GROUP, "ui_control": "domain_list"},
    )

    blocklist: Annotated[
        list[str] | None,
        Merge(MergeStrategy.UNION, note="Every policy's blocked sites count."),
    ] = Field(
        default=None,
        title="Blocked sites",
        description=(
            "One per line, the same patterns as Allowed sites. A * on its own "
            "blocks every site not allowed. When a site matches both lists, the "
            "more specific rule wins, and an exact tie is blocked."
        ),
        json_schema_extra={
            "ui_group": _GROUP,
            "ui_control": "domain_list",
            "ui_domain_tester": True,
        },
    )

    # W379: Safe search, built in. The ATLAS filter points the search engines at
    # their own safe-search hosts, and Chrome is told to force SafeSearch and
    # YouTube's restricted mode (platform reference, "SafeSearch is a DNS
    # redirect"). ⚠️ MAX, not MOST_RESTRICTIVE: that one is an AND of "allow"
    # flags, so one policy saying off would switch it off for every other.
    safe_search: Annotated[
        bool | None,
        Merge(MergeStrategy.MAX, note="On in any policy is on."),
    ] = Field(
        default=None,
        title="Safe search",
        description=(
            "Force safe results on Google, Bing and DuckDuckGo, and YouTube's "
            "restricted mode, whatever the user's own setting. Works in every "
            "browser and app on the device."
        ),
        json_schema_extra={"ui_group": _SAFE, "ui_true": "On", "ui_false": "Off"},
    )

    youtube_restrict: Annotated[
        YouTubeRestrict | None,
        Merge(MergeStrategy.MAX, note="The stricter level wins."),
    ] = Field(
        default=None,
        title="YouTube restricted mode",
        description=(
            "Moderate (the default) hides most mature videos; Strict hides more, "
            "and some ordinary videos with them."
        ),
        json_schema_extra={"ui_group": _SAFE},
    )

    @model_validator(mode="after")
    def _youtube_needs_safe_search(self) -> "WebFilterSpec":
        if self.youtube_restrict is not None and not self.safe_search:
            raise ValueError(
                "YouTube restricted mode only applies with Safe search on: turn "
                "Safe search on, or clear it"
            )
        return self

    @field_validator("allowlist", "blocklist")
    @classmethod
    def _rules(cls, value: list[str] | None, info) -> list[str] | None:
        if value is None:
            return None
        try:
            cleaned = rules.normalize_all(value)
        except rules.RuleError as exc:
            raise ValueError(str(exc)) from exc
        if info.field_name == "allowlist" and rules.STAR in cleaned:
            raise ValueError(
                "* in Allowed sites would allow everything, which is already what "
                "happens when nothing is blocked. Leave Allowed sites empty instead"
            )
        return cleaned or None
