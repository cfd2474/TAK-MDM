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

"""What an ATAK_CONFIG policy's TAK Server connections become on a device (W365).

Two channels, both inside ATAK's own managed configuration:

* **Uploaded certificates** become an ATAK data package (`MANIFEST`, a
  `config.pref` with `cot_streams`, and the `.p12` files) carried base64 in one
  of ATAK's `enterpriseConfigurationDataPackage` slots. ATAK decodes it into its
  watched `tools/datapackage/` directory and imports it: certificates into its
  own store, the connection into its server list. Proven on the emulator by
  dropping the same package into that directory (spike S1); the slot delivery
  itself is the hardware test.
* **Every connection** is listed for the ATLAS plugin in
  `atlas.plugin.tak_servers` (`docs/ATLAS-PLUGIN-CONTRACT.md`): it enrols
  `enroll` connections, and removes a connection whose entry carried the removal
  flag once it leaves the list.

⚠️ **Deterministic bytes, everywhere.** ATAK gates each data-package slot on the
MD5 of its value (`<key>Md5`, `PreferenceControl`) and the preferences document
on its own MD5 (platform reference §10b). Identical policy, identical bytes: no
re-import, no reconnect. So zip entries carry a fixed timestamp and fixed order,
connections are sorted by address, and the package uid is derived from content.

⚠️ **`cot_streams` values are XML-escaped, not `\\uXXXX`-escaped.** ATAK reads
connection entries in `loadConnectionHolder` straight from the XML node's text,
without the `decode()` its ordinary preferences go through. The XML parser undoes
entities; nothing undoes `\\u0026`. So a password containing `&` written the way
`atak_pref.encode_text` writes it would reach ATAK as the literal six characters.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from xml.sax.saxutils import escape, quoteattr

from app.artifacts.storage import ArtifactStorage

#: ATAK's five data-package slots, in the order ATLAS fills them: from the last
#: one down, so the first slots stay free for an operator's own packages set in
#: App Management (`atak_config.merge_into_policy` keeps those).
DATA_PACKAGE_SLOTS = tuple(
    reversed(
        ["enterpriseConfigurationDataPackage"]
        + [f"enterpriseConfigurationDataPackage{n}" for n in range(2, 6)]
    )
)

#: A slot's value is base64 text inside a Binder transaction; ATAK's own
#: description of the slots gives 64 KB as the ceiling (platform reference §10a).
MAX_SLOT_CHARS = 64 * 1024

#: The read-out the plugin keys on (`docs/ATLAS-PLUGIN-CONTRACT.md`).
PLUGIN_KEY = "atlas.plugin.tak_servers"

#: A fixed zip timestamp: the earliest a zip can hold. Any real time would change
#: the bytes, and with them the MD5 ATAK gates the slot on.
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


@dataclass
class Delivery:
    """The managed-configuration values a policy's connections call for."""

    #: slot key -> base64 data package.
    data_packages: dict[str, str] = field(default_factory=dict)
    #: The plugin's list, before per-device credentials are added (S3c).
    plugin_entries: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def plugin_entry(
    connection: Mapping[str, Any], credential: tuple[str, str] | None = None
) -> dict[str, Any]:
    """One connection as the ATLAS plugin reads it.

    ⚠️ **A login only when given one**, and that happens only for a device due
    it (`tak_enrollment`): not yet enrolled, renewing, and no failure with this
    login. Otherwise the entry carries no secret and the plugin reports the
    connection `pending` or leaves its certificate alone.
    """
    entry = {
        "id": connection["address"],
        "kind": connection["auth"],
        "address": connection["address"],
        "description": connection.get("name") or connection["address"],
        "remove_on_removal": bool(connection.get("remove_when_no_longer_required")),
    }
    if credential is not None and connection.get("auth") == "enroll":
        entry["username"], entry["password"] = credential
    return entry


def plugin_value(entries: Sequence[Mapping[str, Any]]) -> str:
    """The preference value: compact JSON, sorted by id, keys sorted. `[]` if none."""
    ordered = sorted(entries, key=lambda e: e["id"])
    return json.dumps(ordered, separators=(",", ":"), sort_keys=True)


def build(
    storage: ArtifactStorage,
    connections: Sequence[Mapping[str, Any]],
    *,
    occupied_slots: Sequence[str] = (),
    credentials: Mapping[str, tuple[str, str]] | None = None,
) -> Delivery:
    """Turn resolved connections into data-package slots and plugin entries.

    :param occupied_slots: slots an operator already filled through App
        Management. They are left alone; ATLAS uses the free ones.
    :param credentials: `{id: (username, password)}` for the enroll
        connections this device is due a login for.
    """
    ordered = sorted(connections, key=lambda c: c["address"])
    credentials = credentials or {}
    delivery = Delivery(
        plugin_entries=[plugin_entry(c, credentials.get(c["address"])) for c in ordered]
    )

    certificate = [c for c in ordered if c.get("auth") == "certificate"]
    if not certificate:
        return delivery

    files: dict[str, bytes] = {}
    usable: list[Mapping[str, Any]] = []
    for connection in certificate:
        blobs = _read_certificates(storage, connection)
        if blobs is None:
            delivery.warnings.append(
                f"TAK Server {connection.get('name')!r}: a certificate file is missing "
                f"from storage, so this connection is not delivered. Upload it again."
            )
            continue
        files.update(blobs)
        usable.append(connection)

    free = [slot for slot in DATA_PACKAGE_SLOTS if slot not in set(occupied_slots)]
    for batch in _pack(usable, files):
        encoded = base64.b64encode(_package(batch, files)).decode("ascii")
        if len(encoded) > MAX_SLOT_CHARS:
            names = ", ".join(repr(c.get("name")) for c in batch)
            delivery.warnings.append(
                f"TAK Server {names}: the certificate files are too large for ATAK's "
                f"configuration slot ({len(encoded):,} of {MAX_SLOT_CHARS:,} characters), "
                f"so this connection is not delivered."
            )
            continue
        if not free:
            names = ", ".join(repr(c.get("name")) for c in batch)
            delivery.warnings.append(
                f"TAK Server {names}: all five of ATAK's data-package slots are in use "
                f"(App Management sets some), so this connection is not delivered."
            )
            continue
        delivery.data_packages[free.pop(0)] = encoded
    return delivery


def _file_names(connection: Mapping[str, Any]) -> tuple[str, str]:
    """Names inside the package, from the digests: unique and stable."""
    return (
        f"atlas-{connection['truststore_sha256'][:16]}-truststore.p12",
        f"atlas-{connection['client_cert_sha256'][:16]}-client.p12",
    )


def _read_certificates(
    storage: ArtifactStorage, connection: Mapping[str, Any]
) -> dict[str, bytes] | None:
    truststore, client = _file_names(connection)
    out: dict[str, bytes] = {}
    for name, digest in (
        (truststore, connection.get("truststore_sha256")),
        (client, connection.get("client_cert_sha256")),
    ):
        if not digest:
            return None
        try:
            with storage.open(digest) as handle:
                out[name] = handle.read()
        except Exception:  # noqa: BLE001 - a missing blob is a warning, never a failed check-in
            return None
    return out


def _pack(
    connections: Sequence[Mapping[str, Any]], files: Mapping[str, bytes]
) -> list[list[Mapping[str, Any]]]:
    """Group connections into packages that each fit one slot.

    Greedy in address order, which keeps the grouping stable as long as the
    connections are: a package changes only when something in it changed.
    """
    batches: list[list[Mapping[str, Any]]] = []
    current: list[Mapping[str, Any]] = []
    for connection in connections:
        trial = current + [connection]
        size = len(base64.b64encode(_package(trial, files)))
        if current and size > MAX_SLOT_CHARS:
            batches.append(current)
            current = [connection]
        else:
            current = trial
    if current:
        batches.append(current)
    return batches


def _package(connections: Sequence[Mapping[str, Any]], files: Mapping[str, bytes]) -> bytes:
    """One data package, byte-for-byte reproducible from its connections."""
    # ⚠️ Each file once: servers commonly share one truststore (and may share a
    # client certificate), and a zip with the same entry twice is ambiguous.
    names: list[str] = []
    for connection in connections:
        for name in _file_names(connection):
            if name not in names:
                names.append(name)
    pref = _connection_pref(connections).encode("utf-8")
    digest = hashlib.sha256(pref + b"".join(files[n] for n in names)).hexdigest()[:16]
    uid = f"atlas-takservers-{digest}"
    contents = "".join(
        f'    <Content ignore="false" zipEntry={quoteattr(name)}/>\n'
        for name in ["config.pref", *names]
    )
    manifest = (
        '<MissionPackageManifest version="2">\n'
        "  <Configuration>\n"
        f'    <Parameter name="uid" value="{uid}"/>\n'
        '    <Parameter name="name" value="ATLAS TAK Servers"/>\n'
        # The zip holds passwords: ATAK deletes it once imported.
        '    <Parameter name="onReceiveDelete" value="true"/>\n'
        "  </Configuration>\n"
        f"  <Contents>\n{contents}  </Contents>\n"
        "</MissionPackageManifest>\n"
    ).encode("utf-8")

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, data in [("MANIFEST/manifest.xml", manifest), ("config.pref", pref)] + [
            (n, files[n]) for n in names
        ]:
            info = zipfile.ZipInfo(name, date_time=_ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    return out.getvalue()


def package_uid(data: bytes) -> str:
    """The uid inside a package this module built (the agent clean-up keys on it)."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        manifest = archive.read("MANIFEST/manifest.xml").decode("utf-8")
    marker = 'name="uid" value="'
    return manifest[manifest.index(marker) + len(marker):].split('"', 1)[0]


def _connection_pref(connections: Sequence[Mapping[str, Any]]) -> str:
    """The `cot_streams` block. XML-escaped values; see the module note."""

    def entry(key: str, java_class: str, value: str) -> str:
        return (
            f'    <entry key={quoteattr(key)} class="class java.lang.{java_class}">'
            f"{escape(value)}</entry>\n"
        )

    lines = [entry("count", "Integer", str(len(connections)))]
    for j, connection in enumerate(connections):
        truststore, client = _file_names(connection)
        lines += [
            entry(f"description{j}", "String", connection.get("name") or connection["address"]),
            entry(f"enabled{j}", "Boolean", "true"),
            entry(f"connectString{j}", "String", connection["address"]),
            entry(f"caLocation{j}", "String", f"cert/{truststore}"),
            entry(f"caPassword{j}", "String", connection.get("truststore_password") or ""),
            entry(f"certificateLocation{j}", "String", f"cert/{client}"),
            entry(f"clientPassword{j}", "String", connection.get("client_cert_password") or ""),
        ]
    return (
        "<?xml version='1.0' standalone='yes'?>\n<preferences>\n"
        '  <preference version="1" name="cot_streams">\n'
        + "".join(lines)
        + "  </preference>\n</preferences>\n"
    )
