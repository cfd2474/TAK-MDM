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

"""What a web-filter rule means, and which rule wins (W369).

Three kinds of pattern, exactly as the operator's spec and Headwind's
documentation describe them:

- ``example.com`` — that hostname only.
- ``*.example.com`` — its subdomains, **not** ``example.com`` itself.
- ``*`` — every hostname (in the blocklist: deny whatever is not allowed).

Anything else with a ``*`` in it is refused rather than guessed at: a
``*example.com`` read as a plain suffix would match ``evil-example.com``.

**Which rule wins: the most specific match, and a tie goes to block.**
An exact host beats any wildcard; a longer ``*.`` suffix beats a shorter one;
``*`` is the weakest. So ``tak.gov`` allowed under a ``*`` block is reachable,
``ads.example.com`` blocked under an allowed ``*.example.com`` is not, and the
same pattern on both lists is blocked. A host no rule matches is allowed.

⚠️ **The device must decide exactly as this does.** ``web_filter_vectors.json``
beside this file is the shared truth: the server's tests and the filter app's
both run every case in it.

⚠️ **Hostnames only.** A DNS filter sees names, never paths, so a rule with a
scheme, a path or a port is refused, not silently trimmed to its host.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

STAR = "*"
_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")


class RuleError(ValueError):
    """A pattern that cannot be a rule, said in words an operator can act on."""


def _hostname(text: str) -> str:
    """`text` as a lower-case ASCII hostname, or RuleError."""
    name = text.strip().lower().rstrip(".")
    if not name:
        raise RuleError("an empty name")
    try:
        ipaddress.ip_address(name.strip("[]"))
    except ValueError:
        pass
    else:
        raise RuleError(
            f"{text!r} is an IP address. The filter works on names, so it cannot "
            "match an address; list the site's name instead"
        )
    try:
        labels = [
            label.encode("idna").decode("ascii") if not label.isascii() else label
            for label in name.split(".")
        ]
    except UnicodeError as exc:
        raise RuleError(f"{text!r} is not a valid name") from exc
    ascii_name = ".".join(labels)
    if len(ascii_name) > 253 or not all(_LABEL.match(label) for label in labels):
        raise RuleError(f"{text!r} is not a valid name")
    return ascii_name


def normalize(pattern: str) -> str:
    """One rule in its stored form, or RuleError saying what is wrong with it."""
    text = pattern.strip()
    if text == STAR:
        return STAR
    if re.search(r"://|/|:|\s|@|\?|#", text):
        raise RuleError(
            f"{pattern!r}: enter a name only, such as example.com, without "
            "https://, a path or a port. The filter sees names, not pages"
        )
    if text.startswith("*."):
        suffix = _hostname(text[2:])
        if "." not in suffix:
            raise RuleError(
                f"{pattern!r} would match every .{suffix} site. To block everything, "
                "use * on its own"
            )
        return f"*.{suffix}"
    if "*" in text:
        raise RuleError(
            f"{pattern!r}: * is allowed only on its own, or as *. at the start "
            "(*.example.com). A * anywhere else could match names you did not "
            "mean, such as evil-example.com for *example.com"
        )
    return _hostname(text)


def normalize_all(patterns: list[str]) -> list[str]:
    """Every rule normalised, duplicates dropped, order kept. Raises on the first bad one."""
    seen: dict[str, None] = {}
    for pattern in patterns:
        seen.setdefault(normalize(pattern), None)
    return list(seen)


def host_of(text: str) -> str:
    """The hostname in something typed into the tester: a name, or a whole URL."""
    raw = text.strip()
    if "://" in raw:
        raw = urlsplit(raw).hostname or ""
    else:
        raw = raw.split("/", 1)[0].split(":", 1)[0]
    return _hostname(raw)


def _matches(pattern: str, host: str) -> bool:
    if pattern == STAR:
        return True
    if pattern.startswith("*."):
        return host.endswith(pattern[1:])  # ".suffix": subdomains only
    return host == pattern


def _specificity(pattern: str) -> tuple[int, int]:
    if pattern == STAR:
        return (0, 0)
    if pattern.startswith("*."):
        return (1, pattern.count("."))
    return (2, pattern.count(".") + 1)


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    #: The rule that decided it, or None when no rule matched (allowed by default).
    rule: str | None
    #: "allowlist" or "blocklist", or None with `rule`.
    source: str | None


def evaluate(host: str, allowlist: list[str], blocklist: list[str]) -> Verdict:
    """Whether `host` (already a hostname) may be reached under these rules."""
    candidates = [(p, "allowlist") for p in allowlist if _matches(p, host)]
    candidates += [(p, "blocklist") for p in blocklist if _matches(p, host)]
    if not candidates:
        return Verdict(True, None, None)
    # Most specific first; on a tie the blocklist's entry sorts ahead.
    pattern, source = max(candidates, key=lambda c: (_specificity(c[0]), c[1] == "blocklist"))
    return Verdict(source == "allowlist", pattern, source)
