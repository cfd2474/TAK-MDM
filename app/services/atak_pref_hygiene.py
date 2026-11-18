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

"""Entries an ATAK `.pref` must not carry onto another device (W428).

Operator's defect report: a `.pref` exported from one device and imported on
another makes ATAK **re-enroll** its certificate on the next launch, because it
carries `AtakCertificateDatabase` (Base64-named `QXRha0NlcnRpZmljYXRlRGF0YWJhc2U=`),
the exporting device's certificate-database identity. With a short-lived
enrollment token, that re-enrollment can fail and drop the server connection.

Asked and answered (2026-10-24), strip on import, and say so:
- that identity, always;
- ATAK's own scrub list (`ImportPrefSort.entriesToDelete`, read from ATAK's
  source: it removes these itself after a file import);
- live tokens and API keys;
- TAK Server connection groups (`cot_streams`, `cot_inputs`, `cot_outputs`),
  which are managed in their own section;
- per-device identity: the device UID and callsigns.

⚠️ **Two kinds of rule, by when they apply.** Some are never right in a policy,
so ATLAS also strips them when it **sends** (a key typed in by hand, or a policy
from before W428): the certificate identity, ATAK's scrub list, live tokens.
The rest are only wrong when **copied from another device**: a fleet API key or
a callsign built from `${device.name}` (W370) is exactly what an operator may
mean to set, so those are stripped on import only.
"""

from __future__ import annotations

import base64
import binascii
import re
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    name: str
    #: For the operator: what the entry is, and why it was removed.
    reason: str
    #: Also stripped when ATLAS sends a configuration, not only on import.
    at_send: bool


CERTIFICATE_DATABASE = Rule(
    "certificate database", at_send=True,
    reason="the exporting device's certificate-database identity. Imported, it makes "
           "ATAK re-enroll its certificate on the next launch, which fails if the "
           "enrollment token has expired",
)
ATAK_SCRUBBED = Rule(
    "credential", at_send=True,
    reason="a certificate password or location, or the mesh key. ATAK removes these "
           "itself after importing a preference file",
)
TOKEN = Rule(
    "token", at_send=True,
    reason="a live sign-in token from the exporting device",
)
API_KEY = Rule(
    "API key", at_send=False,
    reason="an API key from the exporting device. Set it in the policy by hand if "
           "the whole fleet should use it",
)
CONNECTION = Rule(
    "TAK Server connection", at_send=False,
    reason="a TAK Server connection from the exporting device. Connections are set in "
           "ATAK Config > TAK Server connections, with enrollment",
)
IDENTITY = Rule(
    "device identity", at_send=False,
    reason="the exporting device's own identity. Imported, every device would share it",
)

#: The names ATAK keeps in its credential store under a Base64-encoded key.
_CERTIFICATE_DATABASE_NAMES = frozenset({"AtakCertificateDatabase"})
#: `ImportPrefSort.entriesToDelete` (ATAK-CIV `main`, read 2026-10-24).
_ATAK_SCRUBBED = frozenset({"clientPassword", "caPassword", "certificateLocation", "caLocation",
                            "networkMeshKey"})
_CONNECTION_GROUPS = frozenset({"cot_streams", "cot_inputs", "cot_outputs"})
_IDENTITY = frozenset({"bestDeviceUID", "locationCallsign"})

_TOKEN = re.compile(r"(?i)(?:^|[._-])(?:access|refresh|auth|id|bearer)?_?token$")
_API_KEY = re.compile(r"(?i)(?:api_?key|authkey)$")
_IDENTITY_PATTERN = re.compile(r"(?i)(?:^|[._])(?:pref_)?callsign$|device_?uid$")
_BASE64_NAME = re.compile(r"^[A-Za-z0-9+/]{8,}={0,2}$")


def decoded_name(key: str) -> str | None:
    """The name behind a Base64-encoded key, as ATAK writes its credential store's."""
    if len(key) % 4 or not _BASE64_NAME.match(key):
        return None
    try:
        name = base64.b64decode(key, validate=True).decode("ascii")
    except (binascii.Error, UnicodeDecodeError):
        return None
    return name if name.isprintable() and name.isidentifier() else None


def problem(group: str, key: str) -> Rule | None:
    """The rule this entry breaks, or None. Decoded names are judged as themselves."""
    if group in _CONNECTION_GROUPS:
        return CONNECTION
    for name in filter(None, (key, decoded_name(key))):
        if name in _CERTIFICATE_DATABASE_NAMES:
            return CERTIFICATE_DATABASE
        if name in _ATAK_SCRUBBED:
            return ATAK_SCRUBBED
        if _TOKEN.search(name):
            return TOKEN
        if _API_KEY.search(name):
            return API_KEY
        if name in _IDENTITY or _IDENTITY_PATTERN.search(name):
            return IDENTITY
    return None


@dataclass(frozen=True)
class Removed:
    key: str
    rule: Rule

    def sentence(self) -> str:
        return f"Removed {self.key} from the ATAK configuration: {self.rule.reason}."


def strip_for_send(group: str, values: Mapping[str, str]) -> tuple[dict[str, str], list[Removed]]:
    """`values` without what may never be sent, and what was removed."""
    kept, removed = {}, []
    for key, value in values.items():
        rule = problem(group, key)
        if rule is not None and rule.at_send:
            removed.append(Removed(key, rule))
        else:
            kept[key] = value
    return kept, removed
