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

"""NETWORKS policy spec — Wi-Fi networks and VPN profiles.

⚠️ Wi-Fi and VPN passwords are stored **in the policy spec in cleartext**. The
device genuinely needs them to connect, and a policy config is persistent by
nature (unlike the one-shot enrolment Wi-Fi credential, D75). This widens the
`pki/` + database exposure envelope (R8/R12) but does not change what already had
to be protected.
"""

from __future__ import annotations

import enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.policies.specs.base import PolicySpec
from app.policies.strategies import Merge, MergeStrategy


class WifiSecurity(str, enum.Enum):
    OPEN = "open"
    WEP = "wep"
    WPA_PSK = "wpa_psk"
    WPA3_SAE = "wpa3_sae"


class MacRandomization(str, enum.Enum):
    PERSISTENT = "persistent"
    NON_PERSISTENT = "non_persistent"
    NONE = "none"


class VpnConnectionType(str, enum.Enum):
    PPTP = "pptp"
    L2TP_IPSEC_PSK = "l2tp_ipsec_psk"
    IPSEC_XAUTH_PSK = "ipsec_xauth_psk"


class WifiNetwork(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ssid: str = Field(min_length=1, max_length=32)
    security: WifiSecurity = WifiSecurity.WPA_PSK
    password: str | None = Field(default=None, max_length=64)
    auto_join: bool = True
    hidden: bool = False
    mac_randomization: MacRandomization = MacRandomization.PERSISTENT

    @model_validator(mode="after")
    def _password_present_when_needed(self) -> "WifiNetwork":
        if self.security is not WifiSecurity.OPEN:
            pw = self.password or ""
            if self.security in (WifiSecurity.WPA_PSK, WifiSecurity.WPA3_SAE) and len(pw) < 8:
                raise ValueError("a WPA/WPA3 password must be at least 8 characters")
            if self.security is WifiSecurity.WEP and not pw:
                raise ValueError("a WEP network needs a key")
        return self


class VpnProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    connection_type: VpnConnectionType = VpnConnectionType.L2TP_IPSEC_PSK
    server: str = Field(min_length=1, max_length=255)
    username: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=128)
    mppe: bool = True


class NetworksSpec(PolicySpec):
    wifi_networks: Annotated[
        list[WifiNetwork] | None,
        Merge(
            MergeStrategy.MERGE_BY_KEY,
            key="ssid",
            note="Stacked policies union Wi-Fi networks by SSID; the highest-ranked "
            "entry wins a clash on the same SSID.",
        ),
    ] = Field(
        default=None,
        title="Wi-Fi networks",
        description="Networks pushed to the device.",
        json_schema_extra={"ui_group": "Wi-Fi", "ui_control": "wifi_list"},
    )

    vpn_profiles: Annotated[
        list[VpnProfile] | None,
        Merge(
            MergeStrategy.MERGE_BY_KEY,
            key="name",
            note="Stacked policies union VPN profiles by name; the highest-ranked "
            "entry wins a clash on the same name.",
        ),
    ] = Field(
        default=None,
        title="VPN profiles",
        description="Built-in VPN profiles. A per-app VPN client is configured "
        "through App Management instead.",
        json_schema_extra={"ui_group": "VPN", "ui_control": "vpn_list"},
    )
