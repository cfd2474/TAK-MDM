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

"""Knox Configurations › IP rules (W486b, the last of coverage item 15).

📖 Samsung `FirewallRule`: an address is `*`, one address, or a range `IP1-IP2`
(no CIDR); a port is `*`, one port, or `P1-P2`; *"Rules applied to IPv4 do not
affect IPv6 data traffic and vice-versa"*; *"allow rules take precedence over
deny rules"*.

The agent writes these together with Data blocking — Samsung's `clearRules`
clears every IP rule at once, so the two must have one owner. Two consequences
the operator sees, both from Samsung's precedence rule:

- an app on Data blocking's **Always allowed apps** also passes an IP block;
- an **Allow** rule lets every app reach that address even while Data blocking
  blocks the network — "block mobile data, but allow the TAK Server" works.

Rows from stacked policies are combined (operator-approved).
"""

from __future__ import annotations

import enum
import ipaddress
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.policies.specs.base import PolicySpec
from app.policies.specs.knox_data_blocking import BlockNetwork
from app.policies.strategies import Merge, MergeStrategy

KNOX = "Knox"
_GROUP = "IP rules"


class IpAction(str, enum.Enum):
    BLOCK = "block"
    ALLOW = "allow"


class IpProtocol(str, enum.Enum):
    ALL = "all"
    TCP = "tcp"
    UDP = "udp"


def _one_address(text: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    try:
        return ipaddress.ip_address(text.strip())
    except ValueError:
        raise ValueError(f"{text!r} is not an IP address") from None


def _one_port(text: str) -> int:
    if not text.strip().isdigit() or not 1 <= int(text) <= 65535:
        raise ValueError(f"{text!r} is not a port (1 to 65535)")
    return int(text)


class IpRule(BaseModel):
    """One Samsung firewall rule for every app (W486b)."""

    model_config = ConfigDict(extra="forbid")

    action: IpAction = IpAction.BLOCK
    #: `*`, an IPv4 or IPv6 address, or a range of one family, low to high.
    address: str = Field(max_length=100)
    #: `*`, a port, or a range, low to high.
    port: str = Field(default="*", max_length=11)
    protocol: IpProtocol = IpProtocol.ALL
    network: BlockNetwork = BlockNetwork.ALL

    @field_validator("address")
    @classmethod
    def _address(cls, value: str) -> str:
        value = value.strip()
        if value == "*":
            return value
        if "-" in value:
            low, _, high = value.partition("-")
            a, b = _one_address(low), _one_address(high)
            if a.version != b.version:
                raise ValueError("a range must be two IPv4 or two IPv6 addresses")
            if a > b:
                raise ValueError("a range goes from the lower address to the higher")
            return f"{a}-{b}"
        if "/" in value:
            raise ValueError("Samsung takes a range (10.0.0.0-10.0.0.255), not a /prefix")
        return str(_one_address(value))

    @field_validator("port")
    @classmethod
    def _port(cls, value: str) -> str:
        value = value.strip() or "*"
        if value == "*":
            return value
        if "-" in value:
            low, _, high = value.partition("-")
            a, b = _one_port(low), _one_port(high)
            if a >= b:
                raise ValueError("a port range goes from the lower port to the higher")
            return f"{a}-{b}"
        return str(_one_port(value))


class KnoxIpRuleFields(PolicySpec):
    """W486b."""

    ip_rules: Annotated[list[IpRule] | None, Merge(MergeStrategy.UNION)] = Field(
        default=None,
        max_length=200,
        title="IP rules",
        description=(
            "Block or allow addresses and ports for every app. The ATLAS agent is "
            "never blocked. ⚠️ Samsung lets an allow rule win over a block: an app on "
            "Data blocking's Always allowed apps also passes an IP block, and an Allow "
            "rule lets every app reach that address even while Data blocking blocks "
            "the network (block mobile data, but allow the TAK Server)."
        ),
        json_schema_extra={"ui_group": _GROUP, "ui_oem": KNOX, "ui_control": "ip_rules"},
    )
