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

"""The Guides section: how-to articles, FAQs, and release notes.

Content is Markdown files under ``app/web/guides/``. A file's title is its first
``# `` heading; its slug is the filename without the leading sort number and the
extension (``01-enrolment.md`` -> ``enrolment``). No database, no front-matter
parser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.web import markdown_lite

_ROOT = Path(__file__).resolve().parent.parent / "web" / "guides"
CATEGORIES = ("howto", "faq")


@dataclass(frozen=True)
class GuideMeta:
    category: str
    slug: str
    title: str


def _slug(path: Path) -> str:
    return re.sub(r"^\d+[-_]", "", path.stem)


def _title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        m = re.match(r"#\s+(.*)", line.strip())
        if m:
            return m.group(1).strip()
    return fallback


def _dir(category: str) -> Path:
    if category not in CATEGORIES:
        raise KeyError(category)
    return _ROOT / category


def list_guides(category: str) -> list[GuideMeta]:
    directory = _dir(category)
    if not directory.is_dir():
        return []
    metas = []
    for path in sorted(directory.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        metas.append(GuideMeta(category, _slug(path), _title(text, path.stem)))
    return metas


def get_guide(category: str, slug: str) -> tuple[str, str] | None:
    """Return ``(title, rendered_html)`` for one guide, or None if it does not exist."""
    directory = _dir(category)
    for path in directory.glob("*.md"):
        if _slug(path) == slug:
            text = path.read_text(encoding="utf-8")
            return _title(text, slug), markdown_lite.render(text)
    return None


def release_notes_html() -> str:
    path = _ROOT / "release-notes.md"
    if not path.is_file():
        return "<p>No release notes yet.</p>"
    return markdown_lite.render(path.read_text(encoding="utf-8"))
