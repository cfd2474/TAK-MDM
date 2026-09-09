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

"""CERTIFICATES policy spec — what the device itself trusts (W112).

**General device management, not ATAK.** These anchors go into Android's own
trust store, which is what Wi-Fi EAP, the browser, VPN clients and any app asking
the platform for a certificate consult.

⚠️ **ATAK does not read this store**, and an operator who assumes it does gets a
device that looks configured and an ATAK that cannot connect, with nothing
anywhere saying why. ATAK reads `.p12` files from `/sdcard/atak/…` that its own
preferences point at — which FILES and ATAK_CONFIG already deliver. The console
says so beside the field rather than leaving it to be discovered.

⚠️ **Trust is the one setting where "absent" must mean *removed*.** Everywhere
else in this system a policy that stops applying leaves a stale *configuration*
behind, which is untidy. A trust anchor left behind is a device that still trusts
a CA the operator has revoked — so the applier drives this declaratively (R14),
and removes exactly what it installed and nothing else.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from pydantic import Field

from app.policies.specs.base import PolicySpec
from app.policies.strategies import Merge, MergeStrategy

_TRUST = "Trusted certificates"


class CertificatesSpec(PolicySpec):
    trusted_ca_file_ids: Annotated[
        list[uuid.UUID] | None, Merge(MergeStrategy.UNION)
    ] = Field(
        default=None,
        title="Trusted CA certificates",
        description=(
            "Certificate authorities this device should trust, uploaded to the "
            "Content library. They are installed into Android's own trust store, "
            "which is what Wi-Fi EAP, the browser, VPN clients and apps asking the "
            "platform for a certificate use. ⚠️ ATAK does not read this store — its "
            "certificates are files placed by a File management policy and named by "
            "an ATAK Config preference. Removing an authority here removes it from "
            "the device on the next check-in."
        ),
        json_schema_extra={"ui_group": _TRUST, "ui_control": "ca_list"},
    )
