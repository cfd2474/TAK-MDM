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

"""Turn a submitted policy form back into a raw spec dict (W10).

Produces only the fields the operator *managed* — leaving a control at "Not
managed" omits it, so a narrow policy still stacks (D3/D18). The result is handed
straight to ``registry.validate_spec``: this module does no validation of its own,
so a bad value fails once, in the place that already reports it well.
"""

from __future__ import annotations

import json

from typing import Any, Protocol

from app.policies.form_schema import form_fields


class _MultiDict(Protocol):
    def get(self, key: str, default: Any = None) -> Any: ...
    def getlist(self, key: str) -> list[str]: ...


def _looks_numeric(raw: str) -> bool:
    return raw.lstrip("-").isdigit()


def _int_or_none(raw: str | None) -> int | None:
    raw = (raw or "").strip()
    if raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def parse_form(policy_type: str, form: _MultiDict) -> dict[str, Any]:
    spec: dict[str, Any] = {}

    for field in form_fields(policy_type):
        name = field.name

        if field.control == "bool":
            raw = (form.get(name) or "").strip()
            if raw == "true":
                spec[name] = True
            elif raw == "false":
                spec[name] = False
            # "" -> not managed

        elif field.control in ("int", "enum"):
            raw = (form.get(name) or "").strip()
            # ⚠️ An enum's values are not always numbers. Every enum reaching this
            # form today is an IntEnum, so coercing to int was harmless — until
            # W68 added string-valued ones, where `_int_or_none` would have
            # returned None and dropped the operator's choice in silence.
            if field.control == "enum" and raw and not _looks_numeric(raw):
                spec[name] = raw
            else:
                value = _int_or_none(raw)
                if value is not None:
                    spec[name] = value

        elif field.control == "image_file":
            # A single managed-file id, or "" for "no image in this slot". Empty is
            # left unset rather than written as null, so the field stays absent and
            # does not contribute to a merge (to_stored uses exclude_unset).
            raw = (form.get(name) or "").strip()
            if raw:
                spec[name] = raw

        elif field.control in ("str", "password", "text", "kiosk_app", "activity_choice"):
            # The strip matters for `text`: a box holding only whitespace means the
            # operator cleared it, so the field goes absent ("stop managing this")
            # rather than being pushed as a blank string — which for the lock screen
            # message is a materially different instruction to the device, holding
            # it blank and keeping the user locked out of it (Android reference W42).
            raw = (form.get(name) or "").strip()
            if raw:
                spec[name] = raw

        elif field.control == "kiosk_apps":
            # ⚠️ Favourites are matched **by package, not by index**. An unchecked
            # checkbox does not submit at all, so a positional pairing would shift
            # every favourite after the first unchecked row onto the wrong app —
            # and the wrong app would look deliberate.
            packages = form.getlist(f"{name}__package_name")
            activities = form.getlist(f"{name}__activity")
            favorites = {v.strip() for v in form.getlist(f"{name}__favorite") if v}
            rows: list[dict[str, Any]] = []
            seen_packages: set[str] = set()
            for i, package in enumerate(packages):
                package = (package or "").strip()
                if not package or package in seen_packages:
                    continue
                seen_packages.add(package)
                row: dict[str, Any] = {"package_name": package}
                activity = (activities[i] if i < len(activities) else "").strip()
                if activity:
                    row["activity"] = activity
                if package in favorites:
                    row["favorite"] = True
                rows.append(row)
            if rows:
                spec[name] = rows

        elif field.control == "package_list":
            items = [v.strip() for v in form.getlist(name) if v and v.strip()]
            # De-dupe, keep order.
            seen: set[str] = set()
            ordered = [x for x in items if not (x in seen or seen.add(x))]
            if ordered:
                spec[name] = ordered

        elif field.control == "app_list":
            packages = form.getlist(f"{name}__package_name")
            # One select carrying all three intents, because they are mutually
            # exclusive and two controls would let an operator express a
            # contradiction the resolver then has to arbitrate silently:
            #   ""          -> latest published
            #   "min:<code>"-> at least that versionCode
            #   "pin:<sha>" -> exactly this build, including an older one
            choices = form.getlist(f"{name}__version_choice")
            rows: list[dict[str, Any]] = []
            for i, package in enumerate(packages):
                package = (package or "").strip()
                if not package:
                    continue
                row: dict[str, Any] = {"package_name": package}
                choice = (choices[i] if i < len(choices) else "") or ""
                if choice.startswith("min:"):
                    floor = _int_or_none(choice[4:])
                    if floor is not None:
                        row["min_version_code"] = floor
                elif choice.startswith("pin:"):
                    sha = choice[4:].strip().lower()
                    if len(sha) == 64:
                        row["artifact_sha256"] = sha
                rows.append(row)
            if rows:
                spec[name] = rows

        elif field.control == "file_list":
            file_ids = form.getlist(f"{name}__file_id")
            dests = form.getlist(f"{name}__dest_path")
            avails = form.getlist(f"{name}__availability")
            persists = form.getlist(f"{name}__persist")
            extracts = form.getlist(f"{name}__extract")
            extract_tos = form.getlist(f"{name}__extract_to")
            overwrites = form.getlist(f"{name}__overwrite")
            rows = []
            for i, file_id in enumerate(file_ids):
                file_id = (file_id or "").strip()
                dest = (dests[i] if i < len(dests) else "").strip()
                if not file_id or not dest:
                    continue
                row = {"file_id": file_id, "dest_path": dest}
                if i < len(avails) and avails[i]:
                    row["availability"] = avails[i]
                persist = persists[i] if i < len(persists) else "inherit"
                if persist in ("yes", "no"):
                    row["persist"] = persist == "yes"
                if i < len(extracts) and extracts[i] == "on":
                    row["extract"] = True
                    et = (extract_tos[i] if i < len(extract_tos) else "").strip()
                    if et:
                        row["extract_to"] = et
                if i < len(overwrites) and overwrites[i]:
                    row["overwrite"] = overwrites[i]
                rows.append(row)
            if rows:
                spec[name] = rows

        elif field.control == "app_configs":
            # values arrives as JSON because the keys belong to the app, not to
            # this form (W49). Parsed here rather than trusted: it reaches us
            # through a hidden input, so it is operator-supplied like anything else.
            packages = form.getlist(f"{name}__package_name")
            raw_values = form.getlist(f"{name}__values")
            rows = []
            for i, package in enumerate(packages):
                package = (package or "").strip()
                if not package:
                    continue
                try:
                    values = json.loads(raw_values[i] if i < len(raw_values) else "{}")
                except (ValueError, IndexError):
                    continue
                if not isinstance(values, dict):
                    continue
                # A configuration with nothing in it would push an empty Bundle,
                # which is a real instruction to an app — "forget your settings" —
                # and never what an operator meant by leaving the form blank.
                if not values:
                    continue
                rows.append(
                    {
                        "package_name": package,
                        "values": {str(k): str(v) for k, v in values.items()},
                    }
                )
            if rows:
                spec[name] = rows

        elif field.control == "data_package_list":
            # ⚠️ No destination, no persist, no overwrite — a data package has
            # none of those by design (see DataPackageEntry). The row carries the
            # managed file and a title, and nothing that could express "put it
            # back", which is the one instruction that must never reach a device.
            file_ids = form.getlist(f"{name}__file_id")
            titles = form.getlist(f"{name}__title")
            rows: list[dict[str, Any]] = []
            seen_ids: set[str] = set()
            for i, file_id in enumerate(file_ids):
                file_id = (file_id or "").strip()
                if not file_id or file_id in seen_ids:
                    continue
                seen_ids.add(file_id)
                row: dict[str, Any] = {"file_id": file_id}
                title = (titles[i] if i < len(titles) else "").strip()
                if title:
                    row["title"] = title
                rows.append(row)
            if rows:
                spec[name] = rows

        elif field.control == "atak_core_prefs":
            # ⚠️ An empty box means "not managed", exactly as it does for every
            # other text control here — never "set this setting to the empty
            # string". ATAK stores what it is given, so a blank submitted as a
            # value would wipe a callsign or a server address rather than leave
            # it alone, and the console would show it as configured.
            keys = form.getlist(f"{name}__key")
            values = form.getlist(f"{name}__value")
            rows: list[dict[str, Any]] = []
            seen_keys: set[str] = set()
            for i, key in enumerate(keys):
                key = (key or "").strip()
                value = (values[i] if i < len(values) else "").strip()
                # ⚠️ The de-dupe is a real safety net, not tidiness. If the
                # table's script fails part way through building, the hidden
                # fallback inputs the server rendered are still in the form
                # alongside the rows it did manage — the same key twice. First
                # one wins, which is the server-rendered value, which is what the
                # policy already held.
                if not key or not value or key in seen_keys:
                    continue
                seen_keys.add(key)
                rows.append({"key": key, "value": value})
            if rows:
                spec[name] = rows

        elif field.control == "plugin_prefs":
            # Same shape as `app_configs`, and for the same reason: the keys
            # belong to the plugin, so they travel as JSON in a hidden input
            # rather than as form field names this server would have to know.
            packages = form.getlist(f"{name}__package_name")
            raw_values = form.getlist(f"{name}__values")
            rows = []
            for i, package in enumerate(packages):
                package = (package or "").strip()
                if not package:
                    continue
                try:
                    values = json.loads(raw_values[i] if i < len(raw_values) else "{}")
                except (ValueError, IndexError):
                    continue
                if not isinstance(values, dict) or not values:
                    # A plugin with nothing selected is dropped rather than sent:
                    # an empty entry still occupies the merge slot for that
                    # package, so it would suppress a lower-ranked policy's real
                    # configuration with nothing on screen to explain it.
                    continue
                rows.append(
                    {
                        "package_name": package,
                        "values": {str(k): str(v) for k, v in values.items()},
                    }
                )
            if rows:
                spec[name] = rows

        elif field.control in ("usage_rules", "app_usage_rules"):
            # A disabled fieldset submits nothing, so a Knox-gated control simply
            # produces no rows here — and the spec refuses one anyway if a request
            # bypasses the form entirely.
            periods = form.getlist(f"{name}__period")
            metrics = form.getlist(f"{name}__metric")
            thresholds = form.getlist(f"{name}__threshold_mb")
            packages = form.getlist(f"{name}__package_name")
            rows = []
            for i, raw_threshold in enumerate(thresholds):
                threshold = _int_or_none(raw_threshold)
                # The threshold is the row: an empty one is a blank template row
                # the operator added and never filled in, not a rule to enforce.
                if threshold is None:
                    continue
                row: dict[str, Any] = {"threshold_mb": threshold}
                period = _int_or_none(periods[i] if i < len(periods) else None)
                if period is not None:
                    row["period"] = period
                metric = _int_or_none(metrics[i] if i < len(metrics) else None)
                if metric is not None:
                    row["metric"] = metric
                if field.control == "app_usage_rules":
                    package = (packages[i] if i < len(packages) else "").strip()
                    if not package:
                        continue  # a per-app rule naming no app restricts nothing
                    row["package_name"] = package
                rows.append(row)
            if rows:
                spec[name] = rows

        elif field.control == "wifi_list":
            ssids = form.getlist(f"{name}__ssid")
            security = form.getlist(f"{name}__security")
            passwords = form.getlist(f"{name}__password")
            hidden = form.getlist(f"{name}__hidden")
            rows = []
            for i, ssid in enumerate(ssids):
                ssid = (ssid or "").strip()
                if not ssid:
                    continue
                row = {"ssid": ssid}
                _put(row, "security", security, i)
                row["hidden"] = _yes(hidden, i, default=False)
                pw = (passwords[i] if i < len(passwords) else "").strip()
                if pw:
                    row["password"] = pw
                rows.append(row)
            if rows:
                spec[name] = rows

    return spec


def _put(row: dict, key: str, values: list[str], i: int) -> None:
    if i < len(values) and values[i]:
        row[key] = values[i]


def _yes(values: list[str], i: int, *, default: bool) -> bool:
    if i < len(values) and values[i] in ("yes", "no"):
        return values[i] == "yes"
    return default
