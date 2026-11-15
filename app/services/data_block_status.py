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

"""What the device page says about a device's data blocks (W465).

From the agent's last report: which blocks its NETWORK_DATA_USE policy asks for,
and whether the device carries them out. Only a Knox device can (the firewall);
any other device reports the blocks as wanted and not enforced, and this is the
place that says so, because the policy itself saves on every device.

Pure: the route passes in what is stored.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

_NETWORKS = {"wifi": "Wi-Fi", "mobile": "mobile data", "all": "all data"}
_PERIODS = {"daily": "today", "weekly": "this week", "monthly": "this month"}


@dataclass(frozen=True)
class View:
    #: blocking | not_enforced | none
    state: str
    label: str
    #: One sentence per block, e.g. "Mobile data blocked for com.android.chrome,
    #: past 500 MB this month".
    lines: tuple[str, ...]
    allowed: tuple[str, ...]
    error: str | None
    reported_at: datetime | None


_LABELS = {
    "blocking": "Blocking",
    "not_enforced": "Not enforced",
    "none": "No blocks",
}


def describe(block: dict) -> str:
    """One block as a sentence. Unknown words from a newer agent pass through."""
    network = block.get("network") or "all"
    what = _NETWORKS.get(network, network)
    who = block.get("package") or "every app"
    sentence = f"{what[0].upper()}{what[1:]} blocked for {who}"
    cause = block.get("cause")
    if cause == "limit" and block.get("limit_mb"):
        period = block.get("period") or ""
        sentence += f", past {block['limit_mb']} MB {_PERIODS.get(period, period)}".rstrip()
    elif cause == "always":
        sentence += ", always"
    return sentence


def describe_ip_rule(rule: dict) -> str:
    """W486b: "Blocked: 10.0.0.5, port 443, TCP, on mobile data"."""
    verb = "Allowed" if rule.get("action") == "allow" else "Blocked"
    address = rule.get("address") or "*"
    parts = ["any address" if address == "*" else address]
    port = rule.get("port") or "*"
    if port != "*":
        parts.append(f"port {port}")
    protocol = rule.get("protocol") or "all"
    if protocol != "all":
        parts.append(protocol.upper())
    network = rule.get("network") or "all"
    parts.append(f"on {_NETWORKS.get(network, network)}")
    return f"{verb}: " + ", ".join(parts)


def view(report: dict | None, reported_at: datetime | None) -> View | None:
    """None when the device has never reported (an older agent, or no policy)."""
    if not report:
        return None
    blocks = report.get("blocks") or []
    ip_rules = [r for r in (report.get("ip_rules") or []) if isinstance(r, dict)]
    if not blocks and not ip_rules:
        state = "none"
    elif report.get("enforced"):
        state = "blocking"
    else:
        state = "not_enforced"
    return View(
        state=state,
        label=_LABELS[state],
        lines=tuple(describe(b) for b in blocks) + tuple(describe_ip_rule(r) for r in ip_rules),
        allowed=tuple(report.get("allowed") or ()),
        error=report.get("error") or None,
        reported_at=reported_at,
    )
