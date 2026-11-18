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

"""A device's whole policy configuration as one table, for troubleshooting (W434).

Operator: "export a device's policy configs ... a csv with all the device
policies and values so it can be analyzed for troubleshooting".

**One row per value, long format**, so a spreadsheet can filter and sort it: a
list of records (Wi-Fi networks, app configurations) becomes a row per record
field, each with a machine path (`wifi_networks[1].ssid`) beside the title
people read. A list of plain values stays one cell, as it does on the page.

Every policy type is here, App Management included: the page folds that one
into the Apps card, which is exactly why a per-card CSV can't stand in for this.

⚠️ The input is the device page's context (`routes._device_context`), already
masked, the same rule as `device_sections`: a secret the page shows as •••• is
•••• here too.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.services import device_sections
from app.services.device_sections import BLANK, Table, text

COLUMNS = ["Category", "Policy type", "Setting", "Path", "Value", "From policy",
           "Policy version", "Scope", "Rank", "How chosen", "Overrode"]


def _record_list(value: Any) -> list[dict] | None:
    if isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
        return value
    return None


def _leaves(path: str, title: str, value: Any,
            model: type[BaseModel] | None) -> list[tuple[str, str, str]]:
    """(path, title, value) for every plain value under this one, in order."""
    if isinstance(value, dict) and value:
        out: list[tuple[str, str, str]] = []
        for key, sub in value.items():
            out += _leaves(f"{path}.{key}", f"{title} · {device_sections.field_title(model, key)}",
                           sub, device_sections.item_model(model, key))
        return out
    records = _record_list(value)
    if records is not None:
        out = []
        for i, record in enumerate(records, 1):
            out += _leaves(f"{path}[{i}]", f"{title} #{i}", record, model)
        return out
    return [(path, title, text(value))]


def _origin(p: dict) -> list[str]:
    """From policy, version, scope, rank: the winner's, or every contributor's names."""
    source = p.get("source")
    if source:
        return [source.get("policy_name") or BLANK, text(source.get("policy_version")),
                text(source.get("scope")), text(source.get("rank"))]
    names = [c.get("policy_name") for c in p.get("contributors") or [] if c.get("policy_name")]
    return ["; ".join(names), BLANK, BLANK, BLANK]


def rows(values: dict, provenance: dict) -> list[list[str]]:
    """Every effective value, by policy type then setting, as the device gets them."""
    out: list[list[str]] = []
    for policy_type in sorted(values):
        spec = device_sections.spec_class(policy_type)
        category = device_sections.category_title(policy_type)
        type_provenance = provenance.get(policy_type) or {}
        for name, value in (values.get(policy_type) or {}).items():
            p = type_provenance.get(name) or {}
            tail = [*_origin(p), text(p.get("strategy")), device_sections.overrode(p)]
            # A record's fields are titled by the record's own model, when it has one.
            for path, title, cell in _leaves(name, device_sections.field_title(spec, name), value,
                                             device_sections.item_model(spec, name)):
                out.append([category, policy_type, title, path, cell, *tail])
    return out


def table(ctx: dict) -> Table:
    """The export, from the device page's masked context."""
    return Table("policy-config", "Policy configuration", COLUMNS,
                 rows(ctx.get("values") or {}, ctx.get("provenance") or {}))
