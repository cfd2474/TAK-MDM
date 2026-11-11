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

"""NETWORKS policy spec — Wi-Fi networks.

VPN was dropped (W14): Android's built-in VPN profile API is private and
unavailable to a Device Owner, and there is no VPN client app in the deployment
to point always-on VPN at. It returns if a concrete VPN client is deployed.

⚠️ Wi-Fi passwords are stored **in the policy spec in cleartext** and travel in
the signed bundle. The device genuinely needs them to connect, and a policy Wi-Fi
config is persistent by nature (unlike the one-shot enrolment credential, D75).
This widens the `pki/` + database exposure envelope (R8/R12) but does not change
what already had to be protected.
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


class WifiNetwork(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # auto_join and mac_randomization were dropped in W18: the per-network
    # auto-join toggle and WifiConfiguration.macRandomizationSetting are both
    # @SystemApi, so a normally-installed Device Owner cannot set either. A
    # configured network auto-joins by default and the platform picks the MAC
    # randomization mode itself.
    ssid: str = Field(min_length=1, max_length=32)
    security: WifiSecurity = WifiSecurity.WPA_PSK
    password: str | None = Field(default=None, max_length=64)
    hidden: bool = False

    @model_validator(mode="after")
    def _password_present_when_needed(self) -> "WifiNetwork":
        if self.security is not WifiSecurity.OPEN:
            pw = self.password or ""
            if self.security in (WifiSecurity.WPA_PSK, WifiSecurity.WPA3_SAE) and len(pw) < 8:
                raise ValueError("a WPA/WPA3 password must be at least 8 characters")
            if self.security is WifiSecurity.WEP and not pw:
                raise ValueError("a WEP network needs a key")
        return self


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
