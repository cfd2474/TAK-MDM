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
import typing
from dataclasses import dataclass, field

from app.policies.registry import registry
from app.policies.strategies import MergeStrategy

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
    #: bool | int | enum | str | package_list | app_list | file_list
    control: str
    merge_hint: str
    minimum: int | None = None
    maximum: int | None = None
    pattern: str | None = None
    unit: str | None = None
    true_label: str = "Yes"
    false_label: str = "No"
    choices: list[EnumChoice] = field(default_factory=list)
    #: for control == "enum": whether the member values are integers
    enum_is_int: bool = False


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
        if hasattr(meta, "pattern") and meta.pattern:
            pattern = meta.pattern
    return lo, hi, pattern


def _control(annotation: object, extra: dict) -> tuple[str, list[EnumChoice], bool]:
    override = extra.get("ui_control")
    if override:
        return override, [], False
    base = _unwrap(annotation)
    if base is bool:
        return "bool", [], False
    if isinstance(base, type) and issubclass(base, _enum.Enum):
        labels = extra.get("ui_choices", {})
        choices = [
            EnumChoice(
                str(member.value),
                labels.get(str(member.value), member.name.replace("_", " ").title()),
            )
            for member in base
        ]
        return "enum", choices, issubclass(base, int)
    if base is int:
        return "int", [], False
    return "str", [], False


def form_fields(policy_type: str) -> list[FormField]:
    definition = registry.get(policy_type)
    spec_class = definition.spec_class
    merge_rules = definition.merge_rules

    fields: list[FormField] = []
    for name, info in spec_class.model_fields.items():
        extra = _extra(info)
        control, choices, enum_is_int = _control(info.annotation, extra)
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
                enum_is_int=enum_is_int,
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
