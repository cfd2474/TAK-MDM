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

"""Device names and custom attributes, in bulk, as CSV (W370 C8).

One policy with `callsign = ${attribute.Unit}` serves hundreds of trackers
only if each has its Unit, and the console sets those one device at a time.
This is the bulk path: export a spreadsheet, fill it in, import it back.

**The file:** one row per device. `serial` (matches the device, required),
`model` (for reading; never imported), `name`, then one column per custom
attribute, headed with its exact name.

**Import is planned, shown, then applied.** `plan` reads the file and says
exactly what would change, device by device, and what it cannot use; `apply`
re-plans the same text and writes only the changes. Nothing is written by
`plan`.

- A blank cell clears that value; a column left out of the file is not touched.
- A column that is not `serial`, `model`, `name` or an existing attribute is
  refused, not ignored: a mistyped attribute name would otherwise quietly
  change nothing.
- A serial that matches no device, or appears twice, is listed and skipped.

⚠️ **Spreadsheet formulas.** A cell beginning `=`, `+`, `-` or `@` runs as a
formula when the export is opened in Excel, and names and models come partly
from devices. The export prefixes such a cell with `'` (Excel's own "this is
text" mark), and the import takes one leading `'` off again before those
characters, so the round trip is exact.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Device
from app.services import custom_attributes
from app.services import effective_policy as eff

SERIAL = "serial"
MODEL = "model"
NAME = "name"
_FIXED = (SERIAL, MODEL, NAME)

#: Upload bounds: a fleet's worth, not a denial of service.
MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 20000
#: `Device.name` is 128 characters; an attribute value is held to the same.
MAX_VALUE = 128

_FORMULA = ("=", "+", "-", "@")


class InventoryError(ValueError):
    """A file that cannot be imported at all, said in words an operator can act on."""


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #


def export(session: Session) -> str:
    """Every device, its name and its custom attributes, as CSV text (with a
    UTF-8 byte order mark, so Excel reads accented names correctly)."""
    attributes = custom_attributes.list_attributes(session)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow([SERIAL, MODEL, NAME, *(a.name for a in attributes)])
    stored = _stored_values(session)
    for device in session.scalars(select(Device).order_by(Device.serial_number)):
        held = stored.get(device.id, {})
        writer.writerow(
            [_cell(device.serial_number), _cell(device.model), _cell(device.name)]
            + [_cell(held.get(a.name)) for a in attributes]
        )
    return "\ufeff" + out.getvalue()


def _cell(value: str | None) -> str:
    text = value or ""
    return "'" + text if text.startswith(_FORMULA) else text


def _uncell(value: str) -> str:
    text = value.strip()
    return text[1:] if text[:1] == "'" and text[1:2] in _FORMULA else text


# --------------------------------------------------------------------------- #
# Plan
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Change:
    #: "name", or a custom attribute's name.
    field: str
    old: str
    new: str


@dataclass
class DevicePlan:
    device: Device
    changes: list[Change] = field(default_factory=list)


@dataclass
class Plan:
    devices: list[DevicePlan] = field(default_factory=list)
    #: Rows that could not be used, as "line N: why".
    skipped: list[str] = field(default_factory=list)
    #: Columns in the file that are imported (name and attributes).
    columns: list[str] = field(default_factory=list)

    @property
    def change_count(self) -> int:
        return sum(len(d.changes) for d in self.devices)


def decode(data: bytes) -> str:
    """Upload bytes as text: UTF-8, with or without Excel's byte order mark."""
    if len(data) > MAX_BYTES:
        raise InventoryError(f"the file is {len(data)} bytes; the limit is {MAX_BYTES}")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InventoryError(
            "the file is not UTF-8 text. In Excel, save it as \"CSV UTF-8 (Comma delimited)\""
        ) from exc


def plan(session: Session, text: str) -> Plan:
    """What importing `text` would change. Writes nothing."""
    text = text.lstrip("\ufeff")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or not any(cell.strip() for cell in rows[0]):
        raise InventoryError("the file is empty")
    if len(rows) - 1 > MAX_ROWS:
        raise InventoryError(f"the file has {len(rows) - 1} rows; the limit is {MAX_ROWS}")

    header = [cell.strip() for cell in rows[0]]
    attributes = {a.name: a for a in custom_attributes.list_attributes(session)}
    _check_header(header, attributes)
    imported = [h for h in header if h not in (SERIAL, MODEL)]

    lines = [
        (line, {h: _uncell(row[i]) if i < len(row) else "" for i, h in enumerate(header)})
        for line, row in enumerate(rows[1:], start=2)
        if any(cell.strip() for cell in row)
    ]
    on_lines: dict[str, list[int]] = {}
    for line, cells in lines:
        on_lines.setdefault(cells[SERIAL], []).append(line)

    devices = {d.serial_number: d for d in session.scalars(select(Device))}
    stored = _stored_values(session)
    result = Plan(columns=imported)
    for line, cells in lines:
        serial = cells[SERIAL]
        if not serial:
            result.skipped.append(f"line {line}: no serial")
            continue
        if len(on_lines[serial]) > 1:
            others = ", ".join(str(n) for n in on_lines[serial] if n != line)
            result.skipped.append(f"line {line}: {serial} is also on line {others}; none of them is used")
            continue
        device = devices.get(serial)
        if device is None:
            result.skipped.append(f"line {line}: no device has the serial {serial}")
            continue
        too_long = [h for h in imported if len(cells[h]) > MAX_VALUE]
        if too_long:
            result.skipped.append(
                f"line {line}: {serial}: {', '.join(too_long)} longer than {MAX_VALUE} characters"
            )
            continue
        held = stored.get(device.id, {})
        changes = []
        for column in imported:
            old = (device.name or "") if column == NAME else held.get(column, "")
            new = cells[column]
            if new != old:
                changes.append(Change(column, old, new))
        if changes:
            result.devices.append(DevicePlan(device, changes))
    return result


def _stored_values(session: Session) -> dict:
    """device id → {attribute name → value}, in one query."""
    from app.db.models import DeviceAttributeValue

    held: dict = {}
    for row in session.scalars(select(DeviceAttributeValue)):
        held.setdefault(row.device_id, {})[row.attribute.name] = row.value
    return held


def _check_header(header: list[str], attributes: dict) -> None:
    if SERIAL not in header:
        raise InventoryError(f"the first row needs a \"{SERIAL}\" column to match devices by")
    repeated = sorted({h for h in header if header.count(h) > 1})
    if repeated:
        raise InventoryError(f"these columns appear more than once: {', '.join(repeated)}")
    unknown = [h for h in header if h not in _FIXED and h not in attributes]
    if unknown:
        raise InventoryError(
            f"no custom attribute is called {', '.join(repr(h) for h in unknown)}. Columns are "
            f"{SERIAL}, {MODEL}, {NAME} and your attributes' exact names; create an attribute "
            f"in Admin before importing it"
        )


# --------------------------------------------------------------------------- #
# Apply
# --------------------------------------------------------------------------- #


def apply(session: Session, text: str) -> Plan:
    """Import `text`: re-planned here, so what is written is what `plan` says
    now, and only devices with a change are written and recomputed."""
    result = plan(session, text)
    attributes = {a.name: a for a in custom_attributes.list_attributes(session)}
    renamed = []
    for device_plan in result.devices:
        device = device_plan.device
        for change in device_plan.changes:
            if change.field == NAME:
                device.name = change.new or None
                renamed.append(device.id)
            else:
                # Recomputes the device itself (W370 C2).
                custom_attributes.set_value(session, device.id, attributes[change.field].id, change.new)
    # `${device.name}` in a configuration changes with it.
    eff.invalidate(session, renamed)
    session.flush()
    return result
