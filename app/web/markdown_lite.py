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

"""A deliberately small Markdown renderer for the Guides section.

Guide content ships in the repository and is written by us, so this does not need
to be a full CommonMark implementation or a security boundary — but it escapes
all HTML first anyway, so a stray ``<`` in a guide renders as text rather than
markup. Covers headings, fenced and inline code, bold/italic, links, ordered and
unordered lists, blockquotes, horizontal rules and paragraphs. Anything fancier
is not worth a dependency and a Docker rebuild (the AXML and canonical-JSON
precedent).
"""

from __future__ import annotations

import html
import re

_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_CODE = re.compile(r"`([^`]+)`")


#: Schemes a guide may link to. Everything else renders as plain text.
#:
#: ⚠️ An allowlist, not a `javascript:` blocklist. `data:` and `vbscript:` execute
#: too, and a blocklist is a list of the ones somebody thought of. Measured before
#: the fix: `[click](javascript:alert(1))` rendered a live link.
_SAFE_SCHEMES = ("http://", "https://", "mailto:", "/", "#")


def _safe_link(match) -> str:
    """Render a markdown link, or just its words if the target is not a URL."""
    label, target = match.group(1), match.group(2)
    if not target.strip().lower().startswith(_SAFE_SCHEMES):
        # The words survive; only the link is dropped. A guide with a dead link
        # reads oddly; one that silently swallowed a sentence reads like a bug.
        return label
    return '<a href="%s">%s</a>' % (target, label)


def _inline(text: str) -> str:
    # ⚠️ `quote=True`, because a link target is about to be placed inside an
    # attribute. The docstring above claimed this function escaped all HTML; that
    # was true of element context and not of the attribute the link line creates
    # (SEC_AUDIT.md L-3).
    text = html.escape(text, quote=True)
    text = _CODE.sub(r"<code>\1</code>", text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    text = _LINK.sub(_safe_link, text)
    return text


def render(source: str) -> str:
    lines = source.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i = 0
    list_stack: str | None = None  # "ul" | "ol" | None
    para: list[str] = []

    def flush_para() -> None:
        nonlocal para
        if para:
            out.append("<p>" + _inline(" ".join(para).strip()) + "</p>")
            para = []

    def close_list() -> None:
        nonlocal list_stack
        if list_stack:
            out.append(f"</{list_stack}>")
            list_stack = None

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Fenced code block
        if stripped.startswith("```"):
            flush_para()
            close_list()
            i += 1
            code: list[str] = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1  # skip closing fence
            out.append("<pre>" + html.escape("\n".join(code), quote=False) + "</pre>")
            continue

        if not stripped:
            flush_para()
            close_list()
            i += 1
            continue

        heading = re.match(r"(#{1,4})\s+(.*)", stripped)
        if heading:
            flush_para()
            close_list()
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            i += 1
            continue

        if stripped in ("---", "***", "___"):
            flush_para()
            close_list()
            out.append("<hr>")
            i += 1
            continue

        if stripped.startswith("> "):
            flush_para()
            close_list()
            out.append("<blockquote>" + _inline(stripped[2:]) + "</blockquote>")
            i += 1
            continue

        ul = re.match(r"[-*]\s+(.*)", stripped)
        ol = re.match(r"\d+\.\s+(.*)", stripped)
        if ul or ol:
            flush_para()
            want = "ul" if ul else "ol"
            if list_stack != want:
                close_list()
                out.append(f"<{want}>")
                list_stack = want
            out.append("<li>" + _inline((ul or ol).group(1)) + "</li>")
            i += 1
            continue

        para.append(stripped)
        i += 1

    flush_para()
    close_list()
    return "\n".join(out)
