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

"""Write-only secrets in the policy editor (W365).

Operator decision, 2026-10-09: a TAK Server password, once saved, is **never
rendered back into the page**. The editor shows an empty password box with
"stored, leave blank to keep", and a save that leaves it blank keeps the stored
value. This module is the "keeps" half: it fills a blank secret in a submitted
spec from the version being replaced.

⚠️ **Matched by server address, not by row position.** Rows can be added,
removed and reordered before a save, so the n-th submitted row is not the n-th
stored one. A row whose address changed is a different connection and gets no
carried secret: a password for one server must never follow the operator onto
another.

⚠️ **Only when the kind of secret still applies.** A connection switched from
"enroll" to "certificate" does not inherit the enrollment password as a
certificate password, because the fields are distinct and each is carried only
into itself.

The NETWORKS Wi-Fi password predates this and is still echoed into the page; it
is not covered here.
"""

from __future__ import annotations

import copy
from typing import Any

from app.policies.specs.atak_config import connection_address

#: policy type -> (list field, the secret fields of each row).
_WRITE_ONLY: dict[str, tuple[str, tuple[str, ...]]] = {
    "ATAK_CONFIG": (
        "tak_servers",
        ("password", "truststore_password", "client_cert_password"),
    ),
}


def write_only_fields(policy_type: str) -> tuple[str, tuple[str, ...]] | None:
    """The list field and its secret fields for a policy type, if it has any."""
    return _WRITE_ONLY.get(policy_type)


def carry_forward(policy_type: str, new_spec: dict[str, Any], old_spec: dict[str, Any] | None) -> dict[str, Any]:
    """`new_spec` with each blank secret filled from `old_spec`, matched by address.

    Returns a new dict; neither argument is modified.
    """
    rule = _WRITE_ONLY.get(policy_type)
    if rule is None or not old_spec:
        return new_spec
    field, secrets = rule
    new_rows = new_spec.get(field)
    old_rows = old_spec.get(field)
    if not isinstance(new_rows, list) or not isinstance(old_rows, list):
        return new_spec

    stored = {
        connection_address(row): row for row in old_rows if isinstance(row, dict)
    }
    result = copy.deepcopy(new_spec)
    for row in result[field]:
        if not isinstance(row, dict):
            continue
        previous = stored.get(connection_address(row))
        if previous is None:
            continue
        for secret in secrets:
            if row.get(secret) or not previous.get(secret):
                continue
            # A certificate's password belongs to that file: a new upload under
            # the same connection must not inherit the old file's password.
            file_field = _FILE_OF.get(secret)
            if file_field and row.get(file_field) != previous.get(file_field):
                continue
            row[secret] = previous[secret]
    return result


#: A certificate password -> the field holding the file it opens.
_FILE_OF = {
    "truststore_password": "truststore_sha256",
    "client_cert_password": "client_cert_sha256",
}


#: What a stored secret looks like wherever a policy is shown rather than edited.
REDACTED = "••••"


def redact_field(policy_type: str, field: str, value: Any) -> Any:
    """`value` with each set secret replaced by :data:`REDACTED`, for display.

    For the effective-policy table, the policy summaries and anything else that
    prints a resolved value: the write-only rule is that a stored password is
    never rendered back, not only that the editor leaves its box empty.
    """
    rule = _WRITE_ONLY.get(policy_type)
    if rule is None or field != rule[0] or not isinstance(value, list):
        return value
    secrets_ = rule[1]
    return [
        {k: (REDACTED if k in secrets_ and v else v) for k, v in row.items()}
        if isinstance(row, dict) else row
        for row in value
    ]


def redact(policy_type: str, spec: Any) -> Any:
    """A whole spec with its secrets redacted for display (a copy)."""
    if not isinstance(spec, dict):
        return spec
    return {field: redact_field(policy_type, field, value) for field, value in spec.items()}


def redact_effective(values: dict, provenance: dict) -> tuple[dict, dict]:
    """The device page's resolved values and provenance, secrets redacted.

    Provenance repeats values too: every value a winner beat is listed under
    "Overrode", so it is redacted the same way.
    """
    shown_values = {ptype: redact(ptype, spec) for ptype, spec in (values or {}).items()}
    shown_provenance: dict = {}
    for ptype, fields in (provenance or {}).items():
        if not isinstance(fields, dict):
            shown_provenance[ptype] = fields
            continue
        shown_fields = {}
        for field, record in fields.items():
            if isinstance(record, dict) and record.get("overridden"):
                record = {
                    **record,
                    "overridden": [
                        {**o, "value": redact_field(ptype, field, o.get("value"))}
                        if isinstance(o, dict) else o
                        for o in record["overridden"]
                    ],
                }
            shown_fields[field] = record
        shown_provenance[ptype] = shown_fields
    return shown_values, shown_provenance
