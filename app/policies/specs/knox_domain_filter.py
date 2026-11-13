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

"""Knox Configurations › Domain filter (W486a, coverage item 15).

📖 Samsung `Firewall.addDomainFilterRules` / `DomainFilterRule` /
`enableDomainFilterReport` (see the platform reference, "Knox firewall domain
filter and IP rules"). The filter blocks DNS resolution, so it reaches every app
that uses the device's own DNS — and not one that resolves names itself (a
browser's secure DNS, for instance).

⚠️ **Highest-ranked policy wins, mode and list together** (operator-approved).
Each field is merged on its own, so a policy must set both or neither; otherwise
one policy's mode could meet another's list.
"""

from __future__ import annotations

import enum
from typing import Annotated

from pydantic import Field, model_validator

from app.policies.specs.base import PolicySpec
from app.policies.strategies import Merge, MergeStrategy

KNOX = "Knox"
_GROUP = "Domain filter"
_RANK_WINS = Merge(MergeStrategy.HIGHEST_RANK)

#: 📖 *"The character "*" (wildcard) must be at the beginning and/or at the end of
#: the URL otherwise the URL is invalid."* A bare `*` is refused here: in a block
#: list it blocks everything, which "Allow only listed domains" says plainly.
_DOMAIN = r"^\*?[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?\*?$"


class DomainFilterMode(str, enum.Enum):
    BLOCK = "block"
    ALLOW_ONLY = "allow_only"


class KnoxDomainFilterFields(PolicySpec):
    """W486a. The agent writes one all-apps rule, plus an allow-everything rule
    for itself so a filter can never cut a device off from ATLAS."""

    domain_filter_mode: Annotated[DomainFilterMode | None, _RANK_WINS] = Field(
        default=None,
        title="Domain filter",
        description=(
            "Block listed domains: apps cannot reach the domains below. Allow only "
            "listed domains: apps can reach only those. The ATLAS agent is never "
            "filtered. ⚠️ Samsung filters by blocking name lookups, so an app that "
            "does its own lookups (a browser with secure DNS on) is not filtered, and "
            "a site visited recently can stay reachable for a while. Avoid using it "
            "together with the ATLAS web filter."
        ),
        json_schema_extra={"ui_group": _GROUP, "ui_oem": KNOX, "ui_choice_labels": {
            "BLOCK": "Block listed domains", "ALLOW_ONLY": "Allow only listed domains"}},
    )
    domain_filter_domains: Annotated[
        list[Annotated[str, Field(pattern=_DOMAIN, max_length=253)]] | None, _RANK_WINS,
    ] = Field(
        default=None,
        max_length=500,
        title="Domains",
        description=(
            "One per line. A * may stand at the start and/or the end only: "
            "*example.com is example.com and every name ending in it; www.example* "
            "is every name starting with it. For Allow only listed domains, include "
            "everything the apps need, for example the TAK Server and map tiles."
        ),
        json_schema_extra={"ui_group": _GROUP, "ui_oem": KNOX, "ui_control": "path_list"},
    )
    domain_filter_report: Annotated[bool | None, _RANK_WINS] = Field(
        default=None,
        title="Report blocked domains",
        description=(
            "On: the device page lists the latest domains the filter blocked, with "
            "the app that asked. It shows what users tried to reach."
        ),
        json_schema_extra={"ui_group": _GROUP, "ui_oem": KNOX,
                           "ui_true": "On", "ui_false": "Off"},
    )

    @model_validator(mode="after")
    def _mode_and_list_together(self) -> "KnoxDomainFilterFields":
        has_mode = self.domain_filter_mode is not None
        has_list = bool(self.domain_filter_domains)
        if has_mode != has_list:
            raise ValueError(
                "Domain filter: choose a mode and list at least one domain, or leave both empty"
            )
        return self
