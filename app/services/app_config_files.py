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

"""A file uploaded into an app configuration setting (W392).

Operator: TAK Beacon asks for an optional client certificate as
`client_p12_base64`, "How do we handle uploading that instead of pasting a
hash?" Managed configuration has no file type; an app that wants a file takes
it as base64 text. Pasting a certificate's base64 into a text box is the
problem this solves.

**The pattern is the TAK Server certificate's (W365).** The file is stored as an
artifact and the policy holds only a reference, `atlas-file:<sha256>:<name>`.
The reference becomes the file's base64 **only in the document sent to the
device** (`resolve_policy`, called by `desired_state.build`). Everything a person
sees (the editor, the device page, policy summaries, exports) shows the file's
name instead (`describe_policy`), never its bytes.

Which settings offer an upload is decided by the key, because the schema cannot
say: one ending `_base64`, or naming a `.p12`, that is not itself a password.
Pasting still works on any of them: a value that is not a reference is sent as
typed.
"""

from __future__ import annotations

import base64
import copy
import io
import logging
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.artifacts.storage import ArtifactStorage
from app.db.models import Artifact
from app.services import tak_certs

logger = logging.getLogger(__name__)

PREFIX = "atlas-file:"
#: A managed configuration is held in memory by every app that reads it; this is
#: room for any certificate or small key file, and refuses anything that is not.
MAX_BYTES = 256 * 1024
MEDIA_TYPE = "application/octet-stream"

_REFERENCE = re.compile(r"^atlas-file:([0-9a-f]{64}):(.{1,120})$")
_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._\- ()]+")
_P12_NAMES = ("p12", "pkcs12", "pfx")
_PASSWORD_ENDINGS = ("_password", "_pass", "_passwd", "_pwd", "_passphrase")


class FileError(ValueError):
    """An upload that cannot be used, in words the console can show."""


@dataclass(frozen=True)
class Stored:
    reference: str
    name: str
    description: str


# --------------------------------------------------------------------------- #
# Which settings, and the reference itself
# --------------------------------------------------------------------------- #


def is_file_key(key: str) -> bool:
    """Whether a setting takes an uploaded file: `*_base64`, or one naming a .p12."""
    lowered = (key or "").lower()
    if lowered.endswith(_PASSWORD_ENDINGS):
        return False
    return lowered.endswith("_base64") or any(word in lowered for word in _P12_NAMES)


def password_key(key: str) -> str | None:
    """The sibling setting that holds this file's password, by TAK Beacon's
    naming: `client_p12_base64` → `client_p12_password`."""
    lowered = key or ""
    if lowered.endswith("_base64"):
        return lowered[: -len("_base64")] + "_password"
    return None


def reference(digest: str, name: str) -> str:
    safe = _UNSAFE_NAME.sub("_", (name or "file").strip())[:120] or "file"
    return f"{PREFIX}{digest}:{safe}"


def parse(value: Any) -> tuple[str, str] | None:
    """`(sha256, name)` for a reference, or None for any other value."""
    if not isinstance(value, str):
        return None
    found = _REFERENCE.match(value)
    return (found.group(1), found.group(2)) if found else None


def describe_value(value: Any) -> Any:
    """What a person sees for a value: a file's name, or the value unchanged."""
    ref = parse(value)
    return f"{ref[1]} (uploaded file)" if ref else value


# --------------------------------------------------------------------------- #
# Upload
# --------------------------------------------------------------------------- #


def _looks_like_p12(name: str, key: str) -> bool:
    text = f"{name} {key}".lower()
    return any(word in text for word in _P12_NAMES)


def store(
    session: Session, storage: ArtifactStorage, data: bytes, *, name: str, key: str, password: str = ""
) -> Stored:
    """Check an upload and keep it. A `.p12` is opened with its password when one
    is given, so a wrong password is heard about here and not as an app that
    never connects; without a password it is kept, and the description says it
    was not checked."""
    if not data:
        raise FileError("the file is empty")
    if len(data) > MAX_BYTES:
        raise FileError(f"the file is {len(data) // 1024} KB; settings take files up to {MAX_BYTES // 1024} KB")

    description = f"{name}, {max(1, len(data) // 1024)} KB"
    if _looks_like_p12(name, key):
        if password:
            try:
                info = tak_certs.inspect_any(data, password)
            except tak_certs.CertError as exc:
                raise FileError(str(exc)) from None
            kind = "client certificate" if info.kind == tak_certs.CLIENT else "trust store"
            description = f"{name}: {kind}, {info.describe()}"
        else:
            description += " (not checked: its password setting is empty)"

    digest, size = storage.put(io.BytesIO(data))
    if session.get(Artifact, digest) is None:
        session.add(Artifact(sha256=digest, size_bytes=size, media_type=MEDIA_TYPE))
        session.flush()
    ref = reference(digest, name)
    return Stored(reference=ref, name=parse(ref)[1], description=description)


# --------------------------------------------------------------------------- #
# Delivery and display
# --------------------------------------------------------------------------- #


def _map_configs(policy: dict[str, Any], change) -> dict[str, Any]:
    catalog = (policy or {}).get("APP_CATALOG") or {}
    configs = catalog.get("app_configs") or []
    if not any(parse(v) for c in configs for v in ((c or {}).get("values") or {}).values()):
        return policy
    out = copy.deepcopy(policy)
    for entry in out["APP_CATALOG"]["app_configs"]:
        values = (entry or {}).get("values") or {}
        for key in list(values):
            if parse(values[key]):
                changed = change(entry.get("package_name"), key, values[key])
                if changed is None:
                    del values[key]
                else:
                    values[key] = changed
    return out


def resolve_policy(storage: ArtifactStorage, policy: dict[str, Any]) -> dict[str, Any]:
    """The policy as sent to a device: each reference becomes its file's base64.

    ⚠️ A reference whose file is gone is **left out**, never sent as the
    reference text: an app handed "atlas-file:…" as its certificate would fail in
    a way nobody could trace. It is logged; the setting returns once the file is
    uploaded again.
    """
    def to_base64(package: str, key: str, value: str) -> str | None:
        digest, name = parse(value)
        if not storage.exists(digest):
            logger.warning("app config %s.%s names %s, which is no longer stored; left out", package, key, name)
            return None
        data = b"".join(storage.read_all(digest))
        return base64.b64encode(data).decode("ascii")

    return _map_configs(policy, to_base64)


def describe_policy(policy: dict[str, Any]) -> dict[str, Any]:
    """The policy as a person sees it: each reference shown as its file's name."""
    return _map_configs(policy, lambda package, key, value: describe_value(value))


def describe_spec(policy_type: str, spec: dict[str, Any] | None) -> dict[str, Any] | None:
    """[describe_policy] for one section's spec, as the policy summaries hold it."""
    if policy_type != "APP_CATALOG" or not spec:
        return spec
    return describe_policy({"APP_CATALOG": spec})["APP_CATALOG"]
