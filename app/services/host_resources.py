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

"""The host ATLAS runs on: CPU, load, memory, uptime, database size (W440).

Operator: "lets look at adding a new dashboard page that would be the
default landing page for an atlas instance", first version "Server
resources + status".

⚠️ **These are the host's figures, not the container's.** `/proc/stat`,
`/proc/meminfo`, `/proc/loadavg` and `/proc/uptime` are not namespaced: read
inside the ATLAS container they describe the whole box, which is what an
operator asking "is the server struggling" means. The page says "host".

⚠️ **Unknown is reported as unknown.** Every figure is `None` when its file is
missing or unreadable (a developer's Windows machine has no `/proc`), and the
page shows a dash, never a zero: a ring at 0 % reads as "idle", which is a
claim.

Disk is not here: `storage_usage.survey` already measures the filesystem that
holds the library, and the dashboard reuses it rather than measuring twice.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

PROC = Path("/proc")

#: A reading older than this is not a fair "recent" average: measure afresh.
STALE_SECONDS = 300.0
#: How long a fresh measurement samples for, when there is nothing to compare.
FRESH_SAMPLE_SECONDS = 0.5


@dataclass(frozen=True)
class CpuSample:
    """Cumulative CPU time since boot, in jiffies: idle (incl. iowait) and total."""

    idle: int
    total: int


@dataclass(frozen=True)
class Memory:
    total: int
    available: int

    @property
    def used(self) -> int:
        return max(0, self.total - self.available)

    @property
    def percent_used(self) -> float:
        return 0.0 if self.total <= 0 else min(100.0, self.used * 100.0 / self.total)


@dataclass(frozen=True)
class Resources:
    cpu_percent: float | None
    cpus: int | None
    #: 1, 5 and 15 minute load averages.
    load: tuple[float, float, float] | None
    memory: Memory | None
    uptime_seconds: float | None
    database_bytes: int | None


def parse_cpu(stat: str | None) -> CpuSample | None:
    """The aggregate `cpu` line of `/proc/stat`."""
    for line in (stat or "").splitlines():
        fields = line.split()
        if fields and fields[0] == "cpu":
            try:
                values = [int(v) for v in fields[1:]]
            except ValueError:
                return None
            if len(values) < 4:
                return None
            # user nice system idle iowait irq softirq steal (guest is inside user).
            idle = values[3] + (values[4] if len(values) > 4 else 0)
            return CpuSample(idle=idle, total=sum(values[:8]))
    return None


def cpu_percent(before: CpuSample, after: CpuSample) -> float | None:
    """Busy share of the time between two samples, 0-100; None if no time passed."""
    total = after.total - before.total
    if total <= 0:
        return None
    busy = total - (after.idle - before.idle)
    return min(100.0, max(0.0, busy * 100.0 / total))


def parse_loadavg(text_: str | None) -> tuple[float, float, float] | None:
    try:
        one, five, fifteen = (float(v) for v in (text_ or "").split()[:3])
    except ValueError:
        return None
    return one, five, fifteen


def parse_meminfo(text_: str | None) -> Memory | None:
    """`MemTotal` and `MemAvailable`, in bytes (the file says kB, meaning KiB)."""
    values: dict[str, int] = {}
    for line in (text_ or "").splitlines():
        name, _, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            values[name.strip()] = int(parts[0]) * 1024
    if "MemTotal" not in values or "MemAvailable" not in values:
        return None
    return Memory(total=values["MemTotal"], available=values["MemAvailable"])


def parse_uptime(text_: str | None) -> float | None:
    try:
        return float((text_ or "").split()[0])
    except (ValueError, IndexError):
        return None


class CpuMeter:
    """CPU use since the last reading: with a 60 s refresh, the last minute.

    One per process, shared by every request, so two consoles open at once
    split the interval between them rather than each sleeping. With no
    reading to compare (the first, or one too old to be "recent"), it samples
    for `FRESH_SAMPLE_SECONDS`.
    """

    def __init__(
        self,
        read: Callable[[], CpuSample | None],
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._read = read
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._last: tuple[float, CpuSample] | None = None

    def percent(self) -> float | None:
        with self._lock:
            now = self._clock()
            if self._last is None or now - self._last[0] > STALE_SECONDS:
                first = self._read()
                if first is None:
                    return None
                self._sleep(FRESH_SAMPLE_SECONDS)
                self._last = (now, first)
                now = self._clock()
            sample = self._read()
            if sample is None:
                return None
            result = cpu_percent(self._last[1], sample)
            # Only move the baseline once time has passed, so a burst of reads
            # still measures against the last real interval.
            if result is not None:
                self._last = (now, sample)
            return result


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="ascii", errors="replace")
    except OSError:
        return None


METER = CpuMeter(lambda: parse_cpu(_read(PROC / "stat")))


def database_bytes(session: Session) -> int | None:
    """The size of ATLAS's own database; None where it cannot be asked (SQLite)."""
    if session.get_bind().dialect.name != "postgresql":
        return None
    try:
        return int(session.scalar(text("select pg_database_size(current_database())")))
    except Exception:
        session.rollback()
        return None


def read(session: Session, *, proc: Path = PROC, meter: CpuMeter | None = None) -> Resources:
    """Everything the dashboard's resource rings show, each figure or None."""
    meter = meter or METER
    return Resources(
        cpu_percent=meter.percent(),
        cpus=os.cpu_count(),
        load=parse_loadavg(_read(proc / "loadavg")),
        memory=parse_meminfo(_read(proc / "meminfo")),
        uptime_seconds=parse_uptime(_read(proc / "uptime")),
        database_bytes=database_bytes(session),
    )
