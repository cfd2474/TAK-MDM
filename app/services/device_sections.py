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

"""The device page as sections: a few headline stats and the tables behind them (W390).

Operator: "stacked policies become run-on fields ... simple stats for each card,
with a clickable link for a details modal ... export to csv when appropriate ...
a button at the top of the page to export device report".

**One source for four consumers.** The cards show `Section.stats`; each card's
Details modal shows `Section.tables`; every table downloads as its own CSV; and
the device report ZIP is every table of every section. They cannot disagree,
because there is nothing for them to disagree about.

The input is the device page's context (`routes._device_context`), which has
already masked secrets (W365, W370). ⚠️ Nothing here reads a policy value from
anywhere else, so an export can never carry a password the page would hide.

**Values are written for people.** A field's title comes from its spec, booleans
read Yes / No, and a list of records becomes a table of its own with a row per
record, which is the run-on the operator saw: `wifi_networks` and
`required_apps` were dumped into a single cell.

Adding a section is one builder in `_BUILDERS` (OCP, like `reports.py`).
"""

from __future__ import annotations

import csv
import io
import re
import typing
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from app.policies import creator_catalog
from app.policies.registry import registry
from app.services import clock, device_type

#: Policy types shown elsewhere rather than as a category card of their own.
#: App Management is the Apps card (operator: "app catalog is also redundant to
#: apps").
_FOLDED = {"APP_CATALOG"}

#: A cell with nothing to say. One spelling everywhere, so a sort puts them last.
BLANK = ""


@dataclass(frozen=True)
class Stat:
    label: str
    value: str
    #: "good", "warn", "bad" or "" — drawn as the pill colours.
    tone: str = ""


@dataclass(frozen=True)
class Table:
    key: str
    title: str
    columns: list[str]
    rows: list[list[str]]
    note: str = ""
    #: Columns holding a time. A CSV says "(UTC)" in their heading.
    time_columns: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    stats: list[Stat]
    tables: list[Table] = field(default_factory=list)
    #: One line under the stats on the card.
    summary: str = ""
    #: "device", "policy" or "apps": where the card sits on the page.
    group: str = "device"

    def table(self, key: str) -> Table | None:
        return next((t for t in self.tables if t.key == key), None)

    @property
    def has_rows(self) -> bool:
        return any(t.rows for t in self.tables)


# --------------------------------------------------------------------------- #
# Writing values for people
# --------------------------------------------------------------------------- #


def _humanize_key(key: str) -> str:
    text = re.sub(r"[_\.]+", " ", str(key)).strip()
    return text[:1].upper() + text[1:]


def text(value: Any) -> str:
    """One value as a cell: Yes / No, lists joined, records as "key: value"."""
    if value is None or value == "" or value == [] or value == {}:
        return BLANK
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (list, tuple, set)):
        return ", ".join(text(v) for v in value if text(v))
    if isinstance(value, dict):
        return "; ".join(f"{_humanize_key(k)}: {text(v)}" for k, v in value.items() if text(v))
    if hasattr(value, "value") and not isinstance(value, (int, float, str)):
        return str(value.value)
    return str(value)


def _when(moment: datetime | None, tz) -> str:
    return clock.format(moment, tz, "%Y-%m-%d %H:%M") if moment else BLANK


def _at(label: str, tz) -> str:
    """A time's label in a Field / Value table: says UTC when it is."""
    return f"{label} (UTC)" if tz is UTC else label


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


# --------------------------------------------------------------------------- #
# Policy categories
# --------------------------------------------------------------------------- #


def _unwrap(annotation: Any) -> Any:
    """`Annotated[list[X] | None, ...]` → `list[X]`."""
    while True:
        origin = typing.get_origin(annotation)
        if origin is typing.Annotated:
            annotation = typing.get_args(annotation)[0]
            continue
        if origin in (typing.Union, getattr(__import__("types"), "UnionType", None)):
            args = [a for a in typing.get_args(annotation) if a is not type(None)]
            if len(args) == 1:
                annotation = args[0]
                continue
        return annotation


def _item_model(spec_class: type[BaseModel] | None, name: str) -> type[BaseModel] | None:
    """The record type of a list field, when it is a model."""
    if spec_class is None or name not in spec_class.model_fields:
        return None
    annotation = _unwrap(spec_class.model_fields[name].annotation)
    if typing.get_origin(annotation) in (list, tuple):
        args = typing.get_args(annotation)
        item = _unwrap(args[0]) if args else None
        if isinstance(item, type) and issubclass(item, BaseModel):
            return item
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    return None


def _title(model: type[BaseModel] | None, name: str) -> str:
    info = (model.model_fields.get(name) if model else None)
    return (info.title if info and info.title else None) or _humanize_key(name)


def _spec_class(policy_type: str) -> type[BaseModel] | None:
    try:
        return registry.get(policy_type).spec_class
    except Exception:  # noqa: BLE001 — an unknown type still shows its values
        return None


def category_title(policy_type: str) -> str:
    entry = creator_catalog.for_policy_type(policy_type)
    return entry.label if entry else _humanize_key(policy_type.lower())


def _records(value: Any) -> list[dict] | None:
    """A list of records (or one record) as dicts, or None for anything else."""
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
        return value
    return None


def records_table(key: str, title: str, items: list[dict], model: type[BaseModel] | None) -> Table:
    """A list of records as a table: a column per key, in first-seen order."""
    keys: list[str] = []
    for item in items:
        for k in item:
            if k not in keys:
                keys.append(k)
    columns = [_title(model, k) for k in keys]
    rows = [[text(item.get(k)) for k in keys] for item in items]
    return Table(key, title, columns, rows)


def _source(p: dict) -> str:
    if p.get("source"):
        return p["source"].get("policy_name") or BLANK
    if p.get("contributors"):
        return _plural(len(p["contributors"]), "policy combined", "policies combined")
    return BLANK


def _overrode(p: dict) -> str:
    parts = []
    for o in p.get("overridden") or []:
        bit = text(o.get("value"))
        if o.get("source"):
            bit += f" ({o['source'].get('policy_name')})"
        parts.append(bit)
    return "; ".join(parts)


def policy_section(policy_type: str, fields: dict, provenance: dict) -> Section:
    """One policy category: its plain settings, then a table per list of records."""
    spec = _spec_class(policy_type)
    settings_rows: list[list[str]] = []
    record_tables: list[Table] = []
    items = 0
    for name, value in fields.items():
        p = provenance.get(name, {}) or {}
        records = _records(value)
        if records is not None:
            items += len(records)
            label = _title(spec, name)
            record_tables.append(records_table(
                name, label, records, _item_model(spec, name)
            ))
            settings_rows.append([label, _plural(len(records), "entry", "entries"),
                                  _source(p), text(p.get("strategy")), _overrode(p)])
            continue
        if isinstance(value, list):
            items += len(value)
        settings_rows.append([_title(spec, name), text(value), _source(p),
                              text(p.get("strategy")), _overrode(p)])

    conflicts = sum(1 for name in fields if (provenance.get(name) or {}).get("overridden"))
    stats = [Stat("Settings", str(len(fields)))]
    if record_tables:
        stats.append(Stat("Entries", str(sum(len(t.rows) for t in record_tables))))
    if conflicts:
        stats.append(Stat("Overridden", str(conflicts), "warn"))
    summary = "; ".join(
        f"{row[0]}: {row[1]}" for row in settings_rows[:3] if row[1]
    )
    settings = Table(
        "settings", "Settings",
        ["Setting", "Value", "From", "How chosen", "Overrode"], settings_rows,
    )
    return Section(f"policy-{policy_type.lower()}", category_title(policy_type), stats,
                   [settings, *record_tables], summary=summary, group="policy")


# --------------------------------------------------------------------------- #
# The panels
# --------------------------------------------------------------------------- #


def _kv(key: str, title: str, pairs: Iterable[tuple[str, Any]], **kw) -> Table:
    return Table(key, title, ["Field", "Value"], [[k, text(v)] for k, v in pairs], **kw)


def _info(ctx: dict, tz) -> Section:
    d = ctx["device"]
    sims = d.sims or []
    battery = (f"{d.battery_level}%" + (" (charging)" if d.battery_charging else "")
               if d.battery_level is not None else BLANK)
    pairs = [
        ("Name", d.name), ("Serial", d.serial_number),
        ("Category", device_type.label(d.model)),
        ("Manufacturer", device_type.brand(d.model)),
        ("Model", device_type.display_name(d.model) or d.model),
        ("Android", d.os_version), ("Android API level", d.sdk_int),
        ("Agent", d.agent_version), ("Battery", battery),
        ("IMEI 1", d.imei), ("IMEI 2", d.imei2), ("Phone number", d.phone_number),
        ("Carrier", d.carrier), ("Network", d.network_operator),
        ("Roaming", d.network_roaming),
        ("Architectures", d.supported_abis),
        ("ATAK", " ".join(x for x in (d.atak_package, d.atak_version) if x)),
        ("Enrollment state", d.enrollment_state.value),
        ("Compliance", d.compliance_status.value),
        ("Compliance detail", d.compliance_detail),
        ("Worth knowing", d.compliance_warnings),
        ("Policy version on the server", d.state_version),
        ("Policy version applied", d.acked_state_version),
        (_at("Last check-in", tz), _when(d.last_checkin_at, tz)),
        (_at("Enrolled", tz), _when(d.created_at, tz)),
        (_at("Attested", tz), _when(d.attested_at, tz)),
        ("OEM licence", d.oem_license_status),
    ]
    tables = [_kv("device", "Device", pairs)]
    if len(sims) > 1:
        tables.append(records_table("sims", "SIM cards", sims, None))
    stats = [
        Stat("Category", device_type.label(d.model)),
        Stat("Android", d.os_version or "?"),
        Stat("Agent", d.agent_version or "—"),
    ]
    if d.battery_level is not None:
        stats.append(Stat("Battery", f"{d.battery_level}%",
                          "bad" if d.battery_level <= 15 and not d.battery_charging else ""))
    # Operator (W390): the number on the card, where it is the first thing
    # looked for. Only when the device reported one: absence has several
    # reasons, and the Details window says which.
    if d.phone_number:
        stats.append(Stat("Phone", d.phone_number))
    return Section("info", "Device info", stats, tables,
                   summary=" · ".join(x for x in (device_type.display_name(d.model) or d.model,
                                                    d.carrier) if x))


def _location(ctx: dict, tz) -> Section:
    latest = ctx.get("latest_location")
    if latest is None:
        interval = ctx.get("tracking_interval") or 0
        # Two silences, told apart as the panel always did: tracking that is
        # on and has not heard yet, and tracking that is switched off.
        return Section("location", "Location",
                       [Stat("Tracking", f"every {interval} min" if interval else "off",
                             "" if interval else "warn")],
                       [], summary=("Waiting for the first position." if interval
                                    else "Tracking is switched off for this device."))
    accuracy = (f"±{round(latest.accuracy_m)} m" if latest.accuracy_m is not None else BLANK)
    table = Table(
        "latest", "Latest position",
        ["Latitude", "Longitude", "Accuracy", "Taken", "Source"],
        [[f"{latest.latitude:.5f}", f"{latest.longitude:.5f}", accuracy,
          _when(latest.recorded_at, tz), latest.source.value]],
        note="Location history has its own page and export.",
        time_columns=frozenset({"Taken"}),
    )
    stats = [Stat("Fix", ctx.get("location_age") or BLANK, "warn" if ctx.get("location_stale") else ""),
             Stat("Accuracy", accuracy or "—")]
    return Section("location", "Location", stats, [table])


def _groups(ctx: dict, tz) -> Section:
    groups = sorted(ctx["device"].groups, key=lambda g: g.name.casefold())
    table = Table("groups", "Groups", ["Group", "Description"],
                  [[g.name, g.description or BLANK] for g in groups])
    return Section("groups", "Groups", [Stat("Groups", str(len(groups)))], [table],
                   summary=", ".join(g.name for g in groups[:4]))


def _compliance(ctx: dict, tz) -> Section:
    d = ctx["device"]
    results = d.rules_results or []
    outcome = {"pass": "pass", "fail": "fail", "unreported": "not reported"}
    counts = {k: sum(1 for r in results if r.get("outcome") == k) for k in outcome}
    rules = Table("rules", "Rules", ["Rule", "Result", "Device"],
                  [[r.get("label") or r.get("key"), outcome.get(r.get("outcome"), text(r.get("outcome"))),
                    text(r.get("detail"))] for r in results])
    steps = Table("actions", "Actions", ["Action", "From", "State"],
                  [[s.label, _when(s.at, tz), "in force" if s.active else "due"]
                   for s in ctx.get("compliance_timeline") or []],
                  time_columns=frozenset({"From"}))
    stats = [Stat("Passing", str(counts["pass"]), "good" if counts["pass"] else ""),
             Stat("Failing", str(counts["fail"]), "bad" if counts["fail"] else ""),
             Stat("Not reported", str(counts["unreported"]))]
    return Section("compliance", "Compliance rules", stats,
                   [rules] + ([steps] if steps.rows else []),
                   summary="" if results else "No compliance rules apply.")


def _policies(ctx: dict, tz) -> Section:
    considered = ctx.get("considered") or []
    rows = []
    for i, s in enumerate(considered, 1):
        kind = (f"profile · {_plural(s.get('section_count') or 0, 'section')}"
                if s.get("kind") == "profile" else f"v{s.get('policy_version')}")
        rows.append([str(i), s.get("name") or BLANK, kind, text(s.get("scope")),
                     text(s.get("rank")), s.get("origin") or ("this device" if s.get("removable") or s.get("rank_ref") else BLANK)])
    conflicts = len(ctx.get("conflicts") or [])
    stats = [Stat("Policies", str(len(considered))),
             Stat("Profiles", str(sum(1 for s in considered if s.get("kind") == "profile")))]
    if conflicts:
        stats.append(Stat("Conflicts", str(conflicts), "bad"))
    table = Table("policies", "Policies reaching this device",
                  ["#", "Policy", "Kind", "Scope", "Rank", "Comes from"], rows,
                  note="Highest precedence first. The higher rank wins; scope only breaks ties.")
    return Section("policies", "Policies reaching this device", stats, [table])


def _apps(ctx: dict, tz) -> Section:
    apps = ctx.get("apps") or []
    catalog = (ctx.get("values") or {}).get("APP_CATALOG") or {}
    mismatches = ctx.get("atak_mismatches") or {}
    rows = []
    for a in apps:
        m = mismatches.get(a.get("package_name"))
        rows.append([
            a.get("label") or a.get("package_name"),
            a.get("package_name"),
            # W394: a build chosen because the policy asks for the newest.
            text(a.get("version_name")) + (" (newest)" if a.get("newest") and a.get("available") else ""),
            text(a.get("version_code")),
            "ready" if a.get("available") else "not ready",
            text(len(a.get("files") or [])) if a.get("available") else BLANK,
            # The device's own ATAK is the evidence (W305): an older plugin is a
            # quiet note, a newer one a warning, marked so it reads apart.
            (("⚠ " if m.level == "warning" else "") + m.message if m else BLANK)
            or (BLANK if a.get("available") else (a.get("reason") or "nothing uploaded for it")),
        ])
    ready = sum(1 for a in apps if a.get("available"))
    blocked = list(catalog.get("blocked_packages") or [])
    allowed = list(catalog.get("allowed_packages") or [])
    configs = catalog.get("app_configs") or []
    rules = [[p, "blocked"] for p in blocked] + [[p, "allowed"] for p in allowed]
    config_rows = []
    for c in configs:
        values = (c or {}).get("values") or {}
        custom = (c or {}).get("custom_types") or {}
        for key, value in values.items():
            # W405: a key typed in by hand says so.
            config_rows.append([c.get("package_name"), f"{key} (custom key)" if key in custom else key, text(value)])
        for other, value in (c or {}).items():
            if other not in ("package_name", "values", "custom_types") and text(value):
                config_rows.append([c.get("package_name"), _humanize_key(other), text(value)])
    d = ctx["device"]
    atak = (f"This device reports ATAK {d.atak_version} ({d.atak_package}). Plugins are checked against it."
            if d.atak_version else
            "This device has not reported an ATAK version, so plugin compatibility cannot be checked.")
    tables = [
        Table("apps", "Apps", ["App", "Package", "Version", "Version code", "Status", "Parts", "Note"], rows,
              note=atak),
        Table("rules", "Blocked and allowed", ["Package", "Rule"], rules),
        Table("configurations", "App configurations", ["Package", "Setting", "Value"], config_rows),
    ]
    # W398: what the user added from the ATLAS store, as the device reports it.
    store_added = sorted(d.store_apps or [])
    tables.append(Table("store", "Added from the ATLAS store", ["Package"], [[p] for p in store_added],
                        note="Installed by the device's user from the ATLAS store. In a multi-app "
                             "kiosk that allows the store, each has a tile; the user can remove them."))
    other = {k: v for k, v in catalog.items()
             if k not in ("required_apps", "blocked_packages", "allowed_packages", "app_configs")}
    if other:
        tables.append(policy_section("APP_CATALOG", other,
                                     ((ctx.get("provenance") or {}).get("APP_CATALOG") or {})).tables[0])
    stats = [Stat("Apps", str(len(apps))),
             Stat("Ready", str(ready), "good" if ready == len(apps) and apps else ""),]
    if len(apps) - ready:
        stats.append(Stat("Not ready", str(len(apps) - ready), "bad"))
    if blocked:
        stats.append(Stat("Blocked", str(len(blocked))))
    if allowed:
        stats.append(Stat("Allowed", str(len(allowed))))
    if configs:
        stats.append(Stat("Configured", str(len(configs))))
    if store_added:
        stats.append(Stat("From store", str(len(store_added))))
    warnings = sum(1 for a in apps if getattr(mismatches.get(a.get("package_name")), "level", "") == "warning")
    if warnings:
        stats.append(Stat("Plugin warnings", str(warnings), "warn"))
    return Section("apps", "Apps", stats, tables, group="apps",
                   summary=", ".join((a.get("label") or a.get("package_name")) for a in apps[:4]))


def _files(ctx: dict, tz) -> Section:
    files = ctx.get("files") or {}
    required = files.get("required") or []
    optional = files.get("available") or []
    rows = ([[f.get("name") or f.get("file_id"), f.get("dest_path") or BLANK, "required",
              f.get("extract_to") if f.get("extract") else BLANK] for f in required]
            + [[f.get("title") or f.get("name"), f.get("dest_path") or BLANK, "optional",
                f.get("extract_to") if f.get("extract") else BLANK] for f in optional])
    return Section("files", "Files",
                   [Stat("Required", str(len(required))), Stat("Optional", str(len(optional)))],
                   [Table("files", "Files", ["Name", "Destination", "Tier", "Extracted to"], rows)],
                   group="apps")


def _plugin(ctx: dict, tz) -> Section | None:
    status = ctx.get("plugin_status")
    if not (ctx.get("plugin_required") or status):
        return None
    if not status:
        return Section("plugin", "ATLAS plugin", [Stat("State", "not reported")], [],
                       summary="The ATLAS app on this device is older than plugin status reporting.")
    tables = [_kv("status", "Status", [
        ("State", status.state), ("Summary", status.summary),
        ("Plugin", status.plugin_version), ("ATAK", status.atak_version),
        (_at("Last report", tz), _when(status.reported_at, tz)), ("Problem", status.error),
        ("Own updates pre-approved", status.self_update_preapproved_at),
    ])]
    tables.append(Table("plugins", "ATAK plugins", ["Package", "Version", "State", "Error"],
                        [[p.package, text(p.version), p.state.replace("_", " "), text(p.error)]
                         for p in status.plugins]))
    if status.auto_load is not None:
        tables.append(Table("auto-load", "Auto-Load", ["Package", "Result", "When", "Error"],
                            [[a.package, a.result.replace("_", " "), text(a.at), text(a.error)]
                             for a in status.auto_load]))
    tables.append(Table("tak-servers", "TAK servers in ATAK",
                        ["Server", "Description", "Connection", "Server version",
                         "Certificate expires", "Truststore expires"],
                        [[s.connect_string, text(s.description),
                          "disabled" if s.enabled is False else
                          ("connected" if s.connected else ("not connected" if s.connected is False else "unknown")),
                          text(s.server_version), text(s.cert_expires), text(s.truststore_expires)]
                         for s in status.tak_servers]))
    managed = ((ctx.get("values") or {}).get("ATAK_CONFIG") or {}).get("tak_servers") or []
    if managed:
        enroll = {r.id: r for r in (status.tak_server_enroll or [])}
        failures = ctx["device"].tak_enroll_failures or {}
        tables.append(Table("managed", "Managed TAK Server connections",
                            ["Connection", "Address", "Authentication", "On the device"],
                            [[c.get("name"), c.get("address"),
                              f"Enroll as {c.get('username')}" if c.get("auth") == "enroll" else "Uploaded certificates",
                              "enrollment failed" if c.get("address") in failures else
                              (enroll[c.get("address")].result.replace("_", " ") if c.get("address") in enroll else
                               ("waiting for the ATLAS plugin" if c.get("auth") == "enroll" else "delivered in ATAK's configuration"))]
                             for c in managed]))
    loaded = sum(1 for p in status.plugins if p.state == "loaded")
    stats = [Stat("State", status.state, "good" if status.running else ("bad" if status.state == "unreadable" else "")),
             Stat("Plugins loaded", f"{loaded}/{len(status.plugins)}")]
    if status.plugin_version:
        stats.append(Stat("Version", status.plugin_version))
    return Section("plugin", "ATLAS plugin", stats, tables, summary=status.summary)


def _web_filter(ctx: dict, tz) -> Section | None:
    view = ctx.get("web_filter")
    if not view:
        return None
    table = _kv("status", "Web filter", [
        ("State", view.label), ("Lists expected", view.expected_version),
        ("Lists running", view.running_version), ("Lookups", view.queries),
        ("Blocked", view.blocked), ("Last error", view.last_error),
        (_at("Reported", tz), _when(view.reported_at, tz)),
    ])
    tone = "good" if view.state == "enforcing" else ("" if view.state == "off" else "warn")
    stats = [Stat("State", view.label, tone)]
    if view.queries:
        stats.append(Stat("Blocked", f"{view.blocked or 0} of {view.queries}"))
    return Section("web-filter", "Web filter", stats, [table])


def _identity(ctx: dict, tz) -> Section:
    ids = ctx.get("identifiers") or []
    kinds = [i.kind.value for i in ids]
    table = Table("identifiers", "Identifiers", ["Kind", "Value", "First seen", "Last seen"],
                  [[i.kind.value, i.value, _when(i.first_seen_at, tz), _when(i.last_seen_at, tz)] for i in ids],
                  note="Re-enrolment matches on any of these.",
                  time_columns=frozenset({"First seen", "Last seen"}))
    stats = [Stat("Identifiers", str(len(ids))),
             Stat("Hardware serial", "yes" if "serial" in kinds else "no", "good" if "serial" in kinds else "warn")]
    return Section("identity", "Identity", stats, [table])


def _attributes(ctx: dict, tz) -> Section:
    pairs = ctx.get("attributes") or []
    table = Table("attributes", "Custom attributes", ["Attribute", "Type", "Value"],
                  [[a.name, a.attr_type, text(v)] for a, v in pairs])
    filled = sum(1 for _, v in pairs if text(v))
    return Section("attributes", "Custom attributes",
                   [Stat("Set", f"{filled} of {len(pairs)}")], [table],
                   summary="; ".join(f"{a.name}: {v}" for a, v in pairs if text(v))[:120])


def _diagnostics(ctx: dict, tz) -> Section:
    bundles = ctx.get("log_bundles") or []
    table = Table("logs", "Collected logs", ["Collected", "Size (KB)", "Truncated", "Agent"],
                  [[_when(b.collected_at, tz), f"{b.size_bytes / 1024:.1f}", text(bool(b.truncated)),
                    text(b.agent_version)] for b in bundles],
                  time_columns=frozenset({"Collected"}))
    # W416: ATAK's own session logs, beside the agent's.
    atak = ctx.get("atak_logs") or []
    atak_table = Table("atak_logs", "ATAK session logs",
                       ["Session started", "File", "State", "Size (KB)", "ATAK", "Uploaded"],
                       [[_when(r.started_at, tz), r.file_name, "complete" if r.complete else "still running",
                         f"{r.size_bytes / 1024:.1f}", text(r.atak_version), _when(r.uploaded_at, tz)]
                        for r in atak],
                       time_columns=frozenset({"Session started", "Uploaded"}))
    stats = [Stat("Logs", str(len(bundles))), Stat("ATAK sessions", str(len(atak)))]
    if ctx.get("pending_log_request"):
        stats.append(Stat("Request", "in flight", "warn"))
    return Section("diagnostics", "Diagnostics", stats, [table, atak_table],
                   summary=f"Latest {_when(bundles[0].collected_at, tz)}" if bundles else "")


def _packages(ctx: dict, tz) -> Section:
    from app.services import package_reports

    report = ctx.get("package_report")
    stats = [Stat("Packages", str(report.package_count) if report else "—")]
    if ctx.get("pending_package_report"):
        stats.append(Stat("Request", "waiting", "warn"))
    if not report:
        return Section("packages", "Device package list", stats, [],
                       summary="No package report from this device yet.")
    rows = package_reports.display_rows(report, tz)
    columns = package_reports.COLUMNS
    table = Table("packages", "Installed packages", [h for _, h in columns],
                  [[row[k] for k, _ in columns] for row in rows],
                  time_columns=frozenset(h for k, h in columns if k in package_reports.TIME_COLUMNS))
    return Section("packages", "Device package list", stats, [table],
                   summary=f"Collected {_when(report.collected_at, tz)}")


def _lifecycle(ctx: dict, tz) -> Section:
    d = ctx["device"]
    pending = ctx.get("disenrolling")
    pairs = [
        ("Enrollment state", d.enrollment_state.value), (_at("Enrolled", tz), _when(d.created_at, tz)),
        (_at("Breach engaged", tz), _when(d.breach_engaged_at, tz)), ("Breach engaged by", d.breach_engaged_by),
        (_at("Breach confirmed", tz), _when(d.breach_confirmed_at, tz)),
        (_at("Factory reset queued", tz), _when(pending.created_at, tz) if pending else BLANK),
    ]
    state = d.enrollment_state.value
    tone = "bad" if d.breach_engaged_at or state == "retired" else ("good" if state == "enrolled" else "")
    stats = [Stat("State", state, tone)]
    if d.breach_engaged_at:
        stats.append(Stat("Breach", "applied" if d.breach_confirmed_at else "sent", "bad"))
    if pending:
        stats.append(Stat("Reset", "queued", "warn"))
    return Section("lifecycle", "Lifecycle", stats,
                   [_kv("lifecycle", "Lifecycle", pairs)])


_BUILDERS: tuple[Callable[[dict, Any], Section | None], ...] = (
    _info, _location, _groups, _compliance, _policies, _apps, _files,
    _plugin, _web_filter, _identity, _attributes, _diagnostics, _packages, _lifecycle,
)


def build(ctx: dict, tz) -> list[Section]:
    """Every section of this device, in page order: panels, then policy categories."""
    sections = [s for s in (b(ctx, tz) for b in _BUILDERS) if s is not None]
    values = ctx.get("values") or {}
    provenance = ctx.get("provenance") or {}
    for policy_type, fields in values.items():
        if policy_type in _FOLDED or not fields:
            continue
        sections.append(policy_section(policy_type, fields, provenance.get(policy_type) or {}))
    return sections


def find(sections: list[Section], key: str) -> Section | None:
    return next((s for s in sections if s.key == key), None)


# --------------------------------------------------------------------------- #
# CSV
# --------------------------------------------------------------------------- #


def _cell(value: str) -> str:
    """⚠️ Neutralise a formula: device-reported text is written into a file a
    spreadsheet opens, and one starting `=`, `+`, `-`, `@` would run (OWASP)."""
    value = str(value)
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def to_csv(table: Table) -> str:
    """One table. Times are UTC in an export, and their headings say so."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([f"{c} (UTC)" if c in table.time_columns else c for c in table.columns])
    for row in table.rows:
        writer.writerow([_cell(v) for v in row])
    return out.getvalue()


def file_name(section: Section, table: Table) -> str:
    base = section.key if len(section.tables) == 1 else f"{section.key}-{table.key}"
    return re.sub(r"[^a-z0-9\-]+", "-", base.lower()).strip("-") + ".csv"


def _slug(text_: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text_).lower()).strip("-") or "table"


def report_files(sections: list[Section]) -> list[tuple[str, str]]:
    """The device report's CSV files, in page order (W390 D4).

    One file per table that has rows: `01-summary.csv` is Device info, then
    each section's tables, named by section and, when it has several, table.
    Numbered so a file manager lists them as the page does. Location history
    is not here; it has its own export.
    """
    files: list[tuple[str, str]] = []
    seen: set[str] = set()
    for section in sections:
        for table in section.tables:
            if not table.rows:
                continue
            if section.key == "info" and table.key == "device":
                name = "summary"
            else:
                # A section's first table carries its name; the rest add theirs.
                prefix = _slug(("policy " if section.key.startswith("policy-") else "") + section.title)
                name = prefix if table is section.tables[0] else f"{prefix}-{_slug(table.title)}"
            while name in seen:
                name += "-2"
            seen.add(name)
            files.append((f"{len(files) + 1:02d}-{name}.csv", to_csv(table)))
    return files


#: The zone an export is built in (the package report's rule: a file outlives
#: the console setting that produced it).
UTC = timezone.utc
