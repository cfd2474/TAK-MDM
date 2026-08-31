"""PASSWORD policy spec."""

from __future__ import annotations

import enum
from typing import Annotated

from pydantic import Field

from app.policies.specs.base import PolicySpec
from app.policies.strategies import Merge, MergeStrategy


class PasswordQuality(enum.IntEnum):
    """Ordered so that MAX means 'the strictest requirement anyone asked for'."""

    NONE = 0
    SOMETHING = 1
    NUMERIC = 2
    NUMERIC_COMPLEX = 3
    ALPHABETIC = 4
    ALPHANUMERIC = 5
    COMPLEX = 6


class PasswordSpec(PolicySpec):
    quality: Annotated[
        PasswordQuality | None,
        Merge(MergeStrategy.MAX, note="Integer-ordered; MAX selects the strictest."),
    ] = None

    min_length: Annotated[int | None, Merge(MergeStrategy.MAX)] = Field(default=None, ge=0, le=16)
    min_letters: Annotated[int | None, Merge(MergeStrategy.MAX)] = Field(default=None, ge=0, le=16)
    min_digits: Annotated[int | None, Merge(MergeStrategy.MAX)] = Field(default=None, ge=0, le=16)
    min_symbols: Annotated[int | None, Merge(MergeStrategy.MAX)] = Field(default=None, ge=0, le=16)
    history_length: Annotated[int | None, Merge(MergeStrategy.MAX)] = Field(
        default=None, ge=0, le=50
    )

    # Lower is stricter for these three, hence MIN.
    expiration_days: Annotated[int | None, Merge(MergeStrategy.MIN)] = Field(
        default=None, ge=1, le=730
    )
    max_failed_attempts_before_wipe: Annotated[int | None, Merge(MergeStrategy.MIN)] = Field(
        default=None, ge=1, le=100
    )
    lock_timeout_seconds: Annotated[int | None, Merge(MergeStrategy.MIN)] = Field(
        default=None, ge=15, le=86_400
    )
