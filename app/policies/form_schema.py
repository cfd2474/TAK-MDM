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

"""Turn a policy spec into a description of the form controls that edit it (W10).

Everything is derived from the registered spec class — its Pydantic fields, their
``title`` / ``description`` / ``json_schema_extra`` metadata, and the ``Merge``
annotation the resolver already reads. There is no parallel descriptor to keep in
sync (DW8). The form layer never validates: it produces a raw spec dict and hands
it to ``registry.validate_spec`` (see ``form_parse``).
"""

from __future__ import annotations

import enum as _enum
import re
import typing
from dataclasses import dataclass, field

from app.policies.registry import registry
from app.policies.strategies import MergeStrategy


def group_slug(label: str) -> str:
    """Stable URL-safe id for a ui_group label."""
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")

_STRATEGY_HINT = {
    MergeStrategy.MOST_RESTRICTIVE: "When policies stack, any one that blocks this wins.",
    MergeStrategy.MAX: "When policies stack, the strongest value wins.",
    MergeStrategy.MIN: "When policies stack, the strictest (lowest) value wins.",
    MergeStrategy.UNION: "When policies stack, every policy's entries are combined.",
    MergeStrategy.INTERSECT: "When policies stack, only entries present in every policy survive — the result can be empty.",
    MergeStrategy.MERGE_BY_KEY: "When policies stack, entries combine by key; the highest-ranked policy wins a clash on the same one.",
    MergeStrategy.HIGHEST_RANK: "When policies stack, the highest-ranked policy's value wins.",
}


@dataclass(frozen=True)
class EnumChoice:
    value: str
    label: str


@dataclass(frozen=True)
class FormField:
    name: str
    label: str
    help: str
    group: str
    #: bool | int | enum | str | password | package_list | app_list | file_list
    control: str
    merge_hint: str
    minimum: int | None = None
    maximum: int | None = None
    pattern: str | None = None
    unit: str | None = None
    true_label: str = "Yes"
    false_label: str = "No"
    choices: list[EnumChoice] = field(default_factory=list)
    #: A value not to echo in previews or the read-only detail view.
    secret: bool = False
    #: Offer the app-store shortcuts above this control. Blocklist only — the
    #: same tick on an allowlist would mean the opposite of what was asked.
    store_toggles: bool = False
    #: An OEM capability this control needs before it can do anything (e.g.
    #: "Knox"). Set means the platform has no route to it yet: the form renders
    #: the control disabled and says why, and the spec refuses a value for it.
    #: Showing it greyed beats hiding it — an operator looking for a data cap
    #: should find out it needs Knox, not conclude the feature was forgotten.
    requires: str | None = None


def _unwrap(annotation: object) -> object:
    """Strip ``| None`` (and Annotated) down to the underlying type."""
    if typing.get_origin(annotation) is typing.Annotated:
        annotation = typing.get_args(annotation)[0]
    args = [a for a in typing.get_args(annotation) if a is not type(None)]
    if args:
        return args[0]
    return annotation


def _extra(field_info) -> dict:
    extra = field_info.json_schema_extra
    return extra if isinstance(extra, dict) else {}


def _bounds(field_info) -> tuple[int | None, int | None, str | None]:
    """Numeric bounds for an int field; character counts for a string one.

    A string's `min_length` / `max_length` arrive as `annotated_types.MinLen` /
    `MaxLen`, which carry neither `ge` nor `le` — so reading only the numeric
    comparisons dropped them, and every `minlength` / `maxlength` the templates
    render off these was a silent no-op.
    """
    lo = hi = pattern = None
    for meta in field_info.metadata:
        if hasattr(meta, "ge") and meta.ge is not None:
            lo = int(meta.ge)
        if hasattr(meta, "gt") and meta.gt is not None:
            lo = int(meta.gt) + 1
        if hasattr(meta, "le") and meta.le is not None:
            hi = int(meta.le)
        if hasattr(meta, "lt") and meta.lt is not None:
            hi = int(meta.lt) - 1
        if getattr(meta, "min_length", None) is not None:
            lo = int(meta.min_length)
        if getattr(meta, "max_length", None) is not None:
            hi = int(meta.max_length)
        if hasattr(meta, "pattern") and meta.pattern:
            pattern = meta.pattern
    return lo, hi, pattern


def _control(annotation: object, extra: dict) -> tuple[str, list[EnumChoice]]:
    override = extra.get("ui_control")
    if override:
        return override, []
    base = _unwrap(annotation)
    if base is bool:
        return "bool", []
    if isinstance(base, type) and issubclass(base, _enum.Enum):
        choices = [
            EnumChoice(str(member.value), member.name.replace("_", " ").title())
            for member in base
        ]
        return "enum", choices
    if base is int:
        return "int", []
    return "str", []


def form_fields(policy_type: str) -> list[FormField]:
    definition = registry.get(policy_type)
    spec_class = definition.spec_class
    merge_rules = definition.merge_rules

    fields: list[FormField] = []
    for name, info in spec_class.model_fields.items():
        extra = _extra(info)
        control, choices = _control(info.annotation, extra)
        lo, hi, pattern = _bounds(info)
        rule = merge_rules.get(name)
        hint = _STRATEGY_HINT.get(rule.strategy, "") if rule else ""
        if rule and rule.note:
            hint = f"{hint} {rule.note}".strip()

        fields.append(
            FormField(
                name=name,
                label=info.title or name.replace("_", " ").capitalize(),
                help=info.description or "",
                group=extra.get("ui_group", "General"),
                control=control,
                merge_hint=hint,
                minimum=lo,
                maximum=hi,
                pattern=pattern,
                unit=extra.get("ui_unit"),
                true_label=extra.get("ui_true", "Yes"),
                false_label=extra.get("ui_false", "No"),
                choices=choices,
                secret=bool(extra.get("ui_secret", False)),
                requires=extra.get("ui_requires"),
                store_toggles=bool(extra.get("ui_store_toggles", False)),
            )
        )
    return fields


def grouped_fields(policy_type: str) -> list[tuple[str, list[FormField]]]:
    """Fields bucketed by ``ui_group``, groups in first-seen order."""
    order: list[str] = []
    buckets: dict[str, list[FormField]] = {}
    for f in form_fields(policy_type):
        if f.group not in buckets:
            buckets[f.group] = []
            order.append(f.group)
        buckets[f.group].append(f)
    return [(g, buckets[g]) for g in order]


@dataclass(frozen=True)
class SubPage:
    slug: str
    label: str
    fields: list[FormField]


def sub_pages(policy_type: str) -> list[SubPage]:
    """A wired category's sub-pages — one per ``ui_group`` (W12)."""
    return [
        SubPage(group_slug(label), label, fields)
        for label, fields in grouped_fields(policy_type)
    ]


def _is_set(value: object) -> bool:
    """Whether a spec value is something an operator actually chose (W135).

    ⚠️ **Key presence is not configuration.** `to_stored` uses
    `exclude_unset=True`, but that keeps a key passed explicitly as null — so a
    spec could carry `core_prefs: None` and describe a page nobody had filled
    in, which is what put a tick beside ATAK Core Pref Config.

    ⚠️ **Falsiness is not emptiness.** `allow_camera: False` and a timeout of 0
    are deliberate settings; `if not value` would hide every page an operator
    had configured to turn something *off*.
    """
    if value is None:
        return False
    if isinstance(value, (str, list, dict, tuple, set)):
        return len(value) > 0
    return True


def managed_group_slugs(policy_type: str, spec: dict) -> set[str]:
    """Slugs of the sub-pages that have at least one field set in ``spec``."""
    return {
        page.slug
        for page in sub_pages(policy_type)
        if any(f.name in spec and _is_set(spec[f.name]) for f in page.fields)
    }
