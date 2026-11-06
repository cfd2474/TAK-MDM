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

"""Device variables, substituted into one device's configuration (W370).

`config_variables` says what a template means; this supplies one device's
values and applies them where a policy may use them:

- App Management › App configurations (`APP_CATALOG.app_configs`), C2;
- ATAK Config › ATAK core settings (`ATAK_CONFIG.core_prefs`) and plugin
  settings (`ATAK_CONFIG.plugin_prefs`), C5. Substituted as raw text: the
  `.pref` writer (`atak_pref`) escapes for ATAK and refuses control characters,
  so that stays in one place. TAK Server connections are never templated.

⚠️ **Called from `effective_policy.refresh`, not from `desired_state.build`.**
`refresh` decides whether the device gets a new `state_version` by comparing
what it computed with what it stored. Substituted there, a renamed device's new
callsign is a changed payload and the device converges; substituted later, the
value would change under an unchanged version and never be applied.

⚠️ **Which edits must recompute a device:** its name, its custom attribute
values, an attribute deleted, its serial promoted at enrolment. Each of those
paths calls `effective_policy.invalidate`.

**A missing value leaves that one setting out** (operator, 2026-10-10): the
app falls back to its own default, and the device page says which setting and
which variable. Never the literal `${…}`, never an empty string.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artifacts.app_restrictions import TYPE_BUNDLE, TYPE_BUNDLE_ARRAY, TYPE_STRING
from app.artifacts.storage import ArtifactStorage
from app.db.models import AppPackage, Device, DeviceIdentifier, IdentifierKind
from app.policies import config_variables as cv
from app.services import custom_attributes

#: Where the settings left out are recorded in the effective-policy payload.
#: Console only: `desired_state.build` never copies it to a device.
PAYLOAD_KEY = "variable_problems"

#: Where a templated setting lives.
APP_CONFIG = "app_config"
ATAK_CORE = "atak_core"
ATAK_PLUGIN = "atak_plugin"
#: What a core ATAK setting is listed under, where an app's package would be.
ATAK_LABEL = "ATAK"

#: The policy types that can hold device variables.
POLICY_TYPES = frozenset({"APP_CATALOG", "ATAK_CONFIG"})


# --------------------------------------------------------------------------- #
# One device's values
# --------------------------------------------------------------------------- #


def substitute(session: Session, device: Device, policy: dict[str, Any]) -> tuple[dict[str, Any], list[dict]]:
    """[apply] with this device's values, looked up only when a setting names a variable."""
    if not _any_variables(policy):
        return policy, []
    return apply(policy, values_for(session, device))


def values_for(session: Session, device: Device) -> dict[str, str | None]:
    """Every variable's value on this device (None: missing)."""
    return values_for_many(session, [device])[device.id]


def values_for_many(session: Session, devices: list[Device]) -> dict[Any, dict[str, str | None]]:
    """[values_for] for many devices in two queries, not two per device: the
    policy page's coverage reads every device a policy reaches."""
    from app.db.models import DeviceAttributeValue

    ids = [d.id for d in devices]
    attributes = custom_attributes.list_attributes(session)
    stored: dict[Any, dict[Any, str]] = {}
    for row in session.scalars(select(DeviceAttributeValue).where(DeviceAttributeValue.device_id.in_(ids))):
        stored.setdefault(row.device_id, {})[row.attribute_id] = row.value
    serials = set(
        session.execute(
            select(DeviceIdentifier.device_id, DeviceIdentifier.value).where(
                DeviceIdentifier.device_id.in_(ids), DeviceIdentifier.kind == IdentifierKind.SERIAL
            )
        ).all()
    )
    out: dict[Any, dict[str, str | None]] = {}
    for device in devices:
        values: dict[str, str | None] = {
            "device.id": str(device.id),
            "device.name": device.name,
            # ⚠️ Only when a SERIAL identifier proves it. A device whose agent
            # was refused `Build.getSerial()` is recorded under its ANDROID_ID,
            # and a record from before identifiers were kept under a LEGACY copy
            # that may be either: missing, rather than a wrong serial on a map.
            "device.serial": device.serial_number if (device.id, device.serial_number) in serials else None,
            "device.model": device.model,
        }
        for attribute in attributes:
            values[f"{cv.ATTRIBUTE}.{attribute.name}"] = stored.get(device.id, {}).get(attribute.id) or None
        out[device.id] = values
    return out


# --------------------------------------------------------------------------- #
# Substitution
# --------------------------------------------------------------------------- #


def apply(policy: dict[str, Any], values: dict[str, str | None]) -> tuple[dict[str, Any], list[dict]]:
    """`policy` (keyed by policy type) with every device variable substituted.

    Returns the new policy (the input is not changed, and is returned as is
    when nothing names a variable) and what was left out, one entry per
    setting: `{"where", "package", "key", "missing" | "error"}`.
    """
    if not _any_variables(policy):
        return policy, []
    problems: list[dict] = []
    out = dict(policy)

    catalog = policy.get("APP_CATALOG") or {}
    if any(_names_variables(e.get("values")) for e in catalog.get("app_configs") or []):
        out["APP_CATALOG"] = {
            **catalog,
            "app_configs": [
                _render_entry(entry, APP_CONFIG, values, problems) for entry in catalog["app_configs"]
            ],
        }

    atak = policy.get("ATAK_CONFIG") or {}
    rendered_atak = dict(atak)
    core = atak.get("core_prefs") or []
    if any(_is_template(e.get("value")) for e in core):
        rendered_atak["core_prefs"] = [
            kept for kept in (_render_core(entry, values, problems) for entry in core) if kept is not None
        ]
    plugins = atak.get("plugin_prefs") or []
    if any(_names_variables(e.get("values")) for e in plugins):
        rendered_atak["plugin_prefs"] = [_render_entry(entry, ATAK_PLUGIN, values, problems) for entry in plugins]
    if rendered_atak != atak:
        out["ATAK_CONFIG"] = rendered_atak
    return out, problems


def _render_entry(entry: dict, where: str, values: dict[str, str | None], problems: list[dict]) -> dict:
    """An `{package_name, values}` entry with its values rendered."""
    if not _names_variables(entry.get("values")):
        return entry
    package = entry.get("package_name")
    rendered: dict[str, Any] = {}
    for key, value in (entry.get("values") or {}).items():
        if not _is_template(value):
            rendered[key] = value
            continue
        result = cv.render(value, values)
        if result.text is not None:
            rendered[key] = result.text
        else:
            problems.append(_problem(where, package, key, result))
    return {**entry, "values": rendered}


def _render_core(entry: dict, values: dict[str, str | None], problems: list[dict]) -> dict | None:
    """A core ATAK `{key, value}`, rendered; None when it must be left out."""
    if not _is_template(entry.get("value")):
        return entry
    result = cv.render(entry["value"], values)
    if result.text is None:
        problems.append(_problem(ATAK_CORE, ATAK_LABEL, entry.get("key"), result))
        return None
    return {**entry, "value": result.text}


def _is_template(value: Any) -> bool:
    return isinstance(value, str) and cv.has_variables(value)


def _names_variables(values: dict | None) -> bool:
    return any(_is_template(v) for v in (values or {}).values())


def _any_variables(policy: dict[str, Any]) -> bool:
    return next(_templated(policy), None) is not None


def _templated(policy: dict[str, Any]) -> Iterator[tuple[str, str, str, str]]:
    """Every `(where, package, key, template)` in `policy` that names a variable."""
    for entry in (policy.get("APP_CATALOG") or {}).get("app_configs") or []:
        for key, value in (entry.get("values") or {}).items():
            if _is_template(value):
                yield APP_CONFIG, entry.get("package_name") or "", key, value
    atak = policy.get("ATAK_CONFIG") or {}
    for entry in atak.get("core_prefs") or []:
        if _is_template(entry.get("value")):
            yield ATAK_CORE, ATAK_LABEL, entry.get("key") or "", entry["value"]
    for entry in atak.get("plugin_prefs") or []:
        for key, value in (entry.get("values") or {}).items():
            if _is_template(value):
                yield ATAK_PLUGIN, entry.get("package_name") or "", key, value


def _delivered(policy: dict[str, Any]) -> dict[tuple[str, str, str], Any]:
    """`(where, package, key)` → value, for every setting `policy` carries."""
    found: dict[tuple[str, str, str], Any] = {}
    for entry in (policy.get("APP_CATALOG") or {}).get("app_configs") or []:
        for key, value in (entry.get("values") or {}).items():
            found[(APP_CONFIG, entry.get("package_name") or "", key)] = value
    atak = policy.get("ATAK_CONFIG") or {}
    for entry in atak.get("core_prefs") or []:
        found[(ATAK_CORE, ATAK_LABEL, entry.get("key") or "")] = entry.get("value")
    for entry in atak.get("plugin_prefs") or []:
        for key, value in (entry.get("values") or {}).items():
            found[(ATAK_PLUGIN, entry.get("package_name") or "", key)] = value
    return found


def _problem(where: str, package: str | None, key: str | None, result: cv.Rendered) -> dict:
    problem: dict[str, Any] = {"where": where, "package": package, "key": key}
    if result.error:
        problem["error"] = result.error
    else:
        problem["missing"] = list(result.missing)
    return problem


# --------------------------------------------------------------------------- #
# At save (W370 C3, C5)
# --------------------------------------------------------------------------- #


def as_policy(policy_type: str, spec: dict[str, Any] | None) -> dict[str, Any]:
    """A single policy's own spec, keyed by its type like a merged policy.

    ⚠️ A policy's spec is `{"app_configs": [...]}`; only the merged effective
    policy is keyed by type.
    """
    return {policy_type: spec or {}} if policy_type in POLICY_TYPES else {}


def uses_variables(policy_type: str, spec: dict[str, Any] | None) -> bool:
    return _any_variables(as_policy(policy_type, spec))


def save_problems(
    session: Session, policy_type: str, spec: dict[str, Any] | None, storage: ArtifactStorage | None = None
) -> list[str]:
    """What a policy about to be saved gets wrong about device variables.

    The checks that need the database; malformed and unknown `device.` names
    are refused by the spec itself. Here: an `attribute.` that does not exist,
    and a variable in a setting declared as something other than text (a
    number or a true/false cannot hold a name). ATAK's types need `storage` to
    read its build; without it they are not checked.

    ⚠️ For ATAK this matters most: a value ATAK cannot parse for its type makes
    the device's whole `.pref` document undeliverable, not just that setting.
    """
    templated = list(_templated(as_policy(policy_type, spec)))
    if not templated:
        return []
    attributes = {a.name for a in custom_attributes.list_attributes(session)}
    types = _Types(session, storage)
    found: list[str] = []
    for where, package, key, template in templated:
        found += [f"{package} › {key}: {p}" for p in cv.problems(template, attributes)]
        if not types.is_text(where, package, key):
            found.append(f"{package} › {key}: this setting is not text, so it cannot hold a device variable")
    return found


def policies_using_attribute(session: Session, attribute_name: str) -> list[str]:
    """Names of the policies (a profile by its own name) whose latest version
    uses `${attribute.<attribute_name>}`, archived ones included: restoring
    one would bring the reference back."""
    from app.db.models import Policy

    wanted = f"{cv.ATTRIBUTE}.{attribute_name}"
    names: dict[str, None] = {}
    for policy in session.scalars(select(Policy).where(Policy.policy_type.in_(POLICY_TYPES))):
        spec = policy.latest_version.spec if policy.latest_version else None
        for _, _, _, template in _templated(as_policy(policy.policy_type, spec)):
            try:
                used = wanted in cv.references(template)
            except cv.TemplateError:
                used = False
            if used:
                names[policy.profile.name if policy.profile is not None else policy.name] = None
                break
    return sorted(names)


def refusal(found: list[str]) -> str:
    return "Device variables: " + "; ".join(found)


#: Declared app-configuration types a variable may stand in: text, and a bundle
#: (its settings travel as one JSON object, rendered with JSON escaping).
_TEXT_TYPES = frozenset({TYPE_STRING, TYPE_BUNDLE, TYPE_BUNDLE_ARRAY})


class _Types:
    """Declared types, read once per save. A key nothing declares counts as
    text: it is delivered as a string."""

    def __init__(self, session: Session, storage: ArtifactStorage | None) -> None:
        self._session = session
        self._storage = storage
        self._cache: dict[tuple[str, str], dict] = {}

    def is_text(self, where: str, package: str, key: str) -> bool:
        if where == APP_CONFIG:
            declared = self._memo(where, package, lambda: _declared_types(self._session, package))
            return declared.get(key) is None or declared[key] in _TEXT_TYPES
        from app.services import atak_pref

        if where == ATAK_CORE:
            classes = self._memo(where, "", self._atak_core_classes)
        else:
            classes = self._memo(where, package, lambda: self._pref_classes(package))
        return classes.get(key, atak_pref.CLASS_STRING) == atak_pref.CLASS_STRING

    def _memo(self, where: str, package: str, read) -> dict:
        if (where, package) not in self._cache:
            self._cache[(where, package)] = read()
        return self._cache[(where, package)]

    def _atak_core_classes(self) -> dict[str, str]:
        """A key any ATAK build in the library declares as other than text wins:
        which ATAK a device runs is only known from its whole policy."""
        from app.services import atak_config, atak_pref

        if self._storage is None:
            return {}
        classes: dict[str, str] = {}
        for package in atak_config.atak_packages(self._session):
            schema = atak_config.schema_for(self._session, self._storage, package)
            for key, java_class in (schema.types() if schema else {}).items():
                if classes.get(key, atak_pref.CLASS_STRING) == atak_pref.CLASS_STRING:
                    classes[key] = java_class
        return classes

    def _pref_classes(self, package_name: str) -> dict[str, str]:
        from app.services import atak_config

        if self._storage is None:
            return {}
        package = self._session.scalar(select(AppPackage).where(AppPackage.package_name == package_name))
        schema = atak_config.schema_for(self._session, self._storage, package) if package else None
        return schema.types() if schema else {}


def _declared_types(session: Session, package: str) -> dict[str, int]:
    """The newest build's declared types, when the library has already read them."""
    from app.services import app_config_bundles

    version = app_config_bundles.newest_version(session, package)
    if version is None or version.declared_config is None:
        return {}
    try:
        declared = json.loads(version.declared_config)
    except ValueError:
        return {}
    return declared if isinstance(declared, dict) else {}


def catalogue(session: Session) -> list[dict[str, str]]:
    """Every variable an operator may insert, for the editor's picker."""
    entries = [
        {"name": v.name, "label": v.label, "description": v.description, "example": v.example}
        for v in cv.DEVICE_VARIABLES
    ]
    for attribute in custom_attributes.list_attributes(session):
        entries.append(
            {
                "name": f"{cv.ATTRIBUTE}.{attribute.name}",
                "label": attribute.name,
                "description": attribute.description or "Custom attribute, set on each device's page.",
                "example": "",
            }
        )
    return entries


# --------------------------------------------------------------------------- #
# Preview and masking (W370 C4)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PreviewRow:
    #: The app or plugin's package, or "ATAK" for a core ATAK setting.
    package: str
    key: str
    #: As written in the policy (masked when the key looks secret).
    template: str
    #: What the device receives (masked likewise), or None when left out.
    value: str | None
    #: Why it is left out: the variables with no value, or the template's error.
    missing: tuple[str, ...] = ()
    error: str | None = None


def preview(session: Session, device: Device, policy_type: str, spec: dict[str, Any] | None) -> list[PreviewRow]:
    """Every setting in a policy's own `spec` that names a variable, as
    `device` would receive it.

    ⚠️ Built from [apply], the function delivery uses, never a second
    rendering, so the preview cannot disagree with what is sent.
    """
    policy = as_policy(policy_type, spec)
    templated = list(_templated(policy))
    if not templated:
        return []
    rendered, problems = apply(policy, values_for(session, device))
    left_out = {(p["where"], p["package"], p["key"]): p for p in problems}
    delivered = _delivered(rendered)
    rows: list[PreviewRow] = []
    for where, package, key, template in templated:
        problem = left_out.get((where, package, key))
        rows.append(
            PreviewRow(
                package=package,
                key=key,
                template=mask(key, template),
                value=None if problem else mask(key, delivered[(where, package, key)]),
                missing=tuple((problem or {}).get("missing") or ()),
                error=(problem or {}).get("error"),
            )
        )
    return rows


#: Parts of a setting's name that mark its value as secret. Lower-cased,
#: matched anywhere in the name, so `serverPassword` and `api_key` both count.
_SECRET_NAMES = ("password", "passwd", "passphrase", "secret", "token", "credential", "apikey", "api_key",
                 "privatekey", "private_key")
MASK = "••••••"


def is_secret(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in _SECRET_NAMES)


def mask(key: str, value: str) -> str:
    """`value` fit to show: masked whole when `key` looks secret, and secrets
    inside a JSON value (AndroidTAKTracker's `serversJson`) masked in place."""
    if is_secret(key):
        return MASK
    if not value.lstrip().startswith(("{", "[")):
        return value
    try:
        document = json.loads(value)
    except ValueError:
        return value
    masked, changed = _mask_json(document)
    return json.dumps(masked, ensure_ascii=False) if changed else value


def _mask_json(node: Any) -> tuple[Any, bool]:
    if isinstance(node, dict):
        out, changed = {}, False
        for k, v in node.items():
            if isinstance(k, str) and is_secret(k) and not isinstance(v, (dict, list)):
                out[k], changed = MASK, True
            else:
                out[k], inner = _mask_json(v)
                changed = changed or inner
        return out, changed
    if isinstance(node, list):
        items = [_mask_json(v) for v in node]
        return [v for v, _ in items], any(c for _, c in items)
    return node, False


def mask_policy(policy: dict[str, Any]) -> dict[str, Any]:
    """A merged policy (keyed by type) with every app and ATAK setting passed
    through [mask], for display. Delivery is never masked."""
    out = dict(policy)
    for policy_type in POLICY_TYPES:
        if isinstance(policy.get(policy_type), dict):
            out[policy_type] = mask_spec(policy_type, policy[policy_type])
    return out


def mask_spec(policy_type: str, spec: dict[str, Any] | None) -> dict[str, Any] | None:
    """A policy's own spec with its app and ATAK settings passed through [mask],
    for summaries such as the policy page's Versions table."""
    if not spec or policy_type not in POLICY_TYPES:
        return spec
    masked = dict(spec)

    def entries(field: str) -> None:
        if spec.get(field):
            masked[field] = [
                {**e, "values": {k: mask(k, v) if isinstance(v, str) else v for k, v in (e.get("values") or {}).items()}}
                for e in spec[field]
            ]

    entries("app_configs")
    entries("plugin_prefs")
    if spec.get("core_prefs"):
        masked["core_prefs"] = [
            {**e, "value": mask(e.get("key") or "", e["value"])} if isinstance(e.get("value"), str) else e
            for e in spec["core_prefs"]
        ]
    return masked


# --------------------------------------------------------------------------- #
# Fleet coverage (W370 C7)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CoverageRow:
    package: str
    key: str
    #: As written (masked when the key looks secret).
    template: str
    #: Devices this setting reaches with a value, and those it is left out on.
    covered: int
    left_out: tuple[Device, ...]
    #: Values more than one device would receive, each with those devices.
    #: Never for a secret-looking key: its values are not shown.
    shared: tuple[tuple[str, tuple[Device, ...]], ...]


def coverage(session: Session, policy_type: str, spec: dict[str, Any] | None, devices: list[Device]) -> list[CoverageRow]:
    """Every templated setting in a policy's own `spec`, across `devices`.

    ⚠️ From [apply], as delivery and the single-device preview are, so the
    counts cannot disagree with what devices receive from this policy.
    """
    policy = as_policy(policy_type, spec)
    templated = list(_templated(policy))
    if not templated or not devices:
        return []
    values = values_for_many(session, devices)
    received: dict[tuple[str, str, str], dict[Any, str | None]] = {t[:3]: {} for t in templated}
    for device in devices:
        rendered, _ = apply(policy, values[device.id])
        # A setting left out is absent from what was rendered, so it reads None.
        delivered = _delivered(rendered)
        for setting in received:
            received[setting][device.id] = delivered.get(setting)
    by_id = {d.id: d for d in devices}
    rows: list[CoverageRow] = []
    for where, package, key, template in templated:
        got = received[(where, package, key)]
        groups: dict[str, list[Device]] = {}
        for device_id, value in got.items():
            if value is not None:
                groups.setdefault(value, []).append(by_id[device_id])
        shared = () if is_secret(key) else tuple(
            (value, tuple(group)) for value, group in sorted(groups.items()) if len(group) > 1
        )
        rows.append(
            CoverageRow(
                package=package,
                key=key,
                template=mask(key, template),
                covered=sum(1 for v in got.values() if v is not None),
                left_out=tuple(by_id[i] for i, v in got.items() if v is None),
                shared=shared,
            )
        )
    return rows

