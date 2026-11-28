"""Finding the icon a website serves for itself (W337).

Copyright 2026 TAK-Solutions LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

Operator: *"an option for the weblink icon to be a 'get from link url' that will
pull the icon served by the linked site itself"*.

⚠️ **This only finds and fetches; it never decodes.** Sites serve ICO, PNG,
JPEG, WebP, GIF and SVG, and the server has no image library. The console's
browser draws whatever this returns into the square PNG the shortcut builder
takes, so the one decoder involved is the browser's.

**Where an icon is looked for**, largest declared size first:

1. the page's `<link rel="apple-touch-icon">` (meant for home screens, so the best
   fit), `<link rel="icon">` and `rel="shortcut icon"`, each by its `sizes`;
2. the icons in the page's web app manifest (`<link rel="manifest">`);
3. `/apple-touch-icon.png` and `/favicon.ico` at the site root, which many sites
   serve without declaring.

⚠️ **Every request goes through `outbound.fetch`** (SEC_AUDIT M-2): never
loopback or link-local, and a redirect may not move from a public address to an
internal one. An internal site is allowed, because a shortcut to an intranet
page is a reasonable thing to want. **The same rule covers links:** a public
page's icon `<link>` or manifest may not name an internal address either.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

from app.security import outbound

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5.0
MAX_PAGE_BYTES = 1024 * 1024
MAX_MANIFEST_BYTES = 256 * 1024
MAX_ICON_BYTES = 1024 * 1024
#: How many candidates are tried before giving up.
MAX_ATTEMPTS = 6

#: What an icon of unknown size is assumed to be, for ordering only.
_ASSUMED = {"apple-touch-icon": 180, "manifest": 96, "icon": 32, "root-touch": 180, "root-ico": 32}


@dataclass(frozen=True)
class SiteIcon:
    data: bytes
    media_type: str
    source_url: str


@dataclass(frozen=True)
class _Candidate:
    url: str
    size: int
    #: Ties go to the more home-screen-like source.
    rank: int


def sniff(data: bytes) -> str | None:
    """The image type by its first bytes, or None for anything else.

    By content, not by the server's Content-Type, which for favicons is wrong
    often enough (`text/plain`, `application/octet-stream`) to be useless.
    """
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:4] == b"\x00\x00\x01\x00":
        return "image/x-icon"
    head = data[:512].lstrip().lower()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in head):
        return "image/svg+xml"
    return None


def _largest(sizes: str | None) -> int | None:
    """The largest WxH in a `sizes` value; `any` (an SVG) counts as large."""
    if not sizes:
        return None
    if "any" in sizes.lower().split():
        return 512
    found = [max(int(w), int(h)) for w, h in re.findall(r"(\d+)\s*[xX]\s*(\d+)", sizes)]
    return max(found) if found else None


class _Links(HTMLParser):
    """`<base>`, icon `<link>`s and the manifest `<link>` from a page's HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.base: str | None = None
        self.icons: list[tuple[str, str, str | None]] = []  # (kind, href, sizes)
        self.manifest: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "base" and a.get("href") and self.base is None:
            self.base = a["href"]
        if tag != "link" or not a.get("href"):
            return
        rels = a.get("rel", "").lower().split()
        if "apple-touch-icon" in rels or "apple-touch-icon-precomposed" in rels:
            self.icons.append(("apple-touch-icon", a["href"], a.get("sizes")))
        elif "icon" in rels:
            self.icons.append(("icon", a["href"], a.get("sizes")))
        elif "manifest" in rels and self.manifest is None:
            self.manifest = a["href"]


def candidates(page_url: str, html: str, manifest: dict | None, manifest_url: str | None) -> list[_Candidate]:
    """Every icon the page declares or the site may serve, best first."""
    parser = _Links()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001 - a broken page still has a root favicon
        pass
    base = urljoin(page_url, parser.base) if parser.base else page_url
    found: list[_Candidate] = []
    for kind, href, sizes in parser.icons:
        url = urljoin(base, href.strip())
        size = _largest(sizes) or _ASSUMED[kind]
        found.append(_Candidate(url, size, 0 if kind == "apple-touch-icon" else 2))
    if manifest and manifest_url:
        for icon in (manifest.get("icons") or [])[:20]:
            if isinstance(icon, dict) and isinstance(icon.get("src"), str):
                size = _largest(icon.get("sizes") if isinstance(icon.get("sizes"), str) else None)
                found.append(_Candidate(urljoin(manifest_url, icon["src"]), size or _ASSUMED["manifest"], 1))
    root = "{0.scheme}://{0.netloc}".format(urlsplit(page_url))
    found.append(_Candidate(root + "/apple-touch-icon.png", _ASSUMED["root-touch"], 3))
    found.append(_Candidate(root + "/favicon.ico", _ASSUMED["root-ico"], 4))
    unique: dict[str, _Candidate] = {}
    for c in found:
        if urlsplit(c.url).scheme in ("http", "https") and c.url not in unique:
            unique[c.url] = c
    return sorted(unique.values(), key=lambda c: (-c.size, c.rank))


def find(page_url: str, *, client: httpx.Client | None = None) -> SiteIcon | None:
    """The site's best icon, or None if it serves none we can use."""
    owned = client is None
    client = client or httpx.Client(
        timeout=TIMEOUT_SECONDS, headers={"User-Agent": "ATLAS-MDM"},
        event_hooks={"response": [_refuse_declared_oversize]},
    )
    try:
        html = _text(client, page_url, MAX_PAGE_BYTES) or ""
        manifest, manifest_url = None, None
        link = _Links()
        try:
            link.feed(html)
        except Exception:  # noqa: BLE001
            pass
        public_page = _is_public(page_url)
        if link.manifest:
            base = urljoin(page_url, link.base) if link.base else page_url
            manifest_url = urljoin(base, link.manifest)
        if manifest_url and public_page and not _is_public(manifest_url):
            log.warning("site icon: %s named an internal manifest, refused", page_url)
            manifest_url = None
        if manifest_url:
            try:
                manifest = json.loads(_text(client, manifest_url, MAX_MANIFEST_BYTES) or "null")
            except ValueError:
                manifest = None
            if not isinstance(manifest, dict):
                manifest = None
        for candidate in candidates(page_url, html, manifest, manifest_url)[:MAX_ATTEMPTS]:
            if public_page and not _is_public(candidate.url):
                # ⚠️ The redirect rule, applied to links: a page on the public
                # internet naming an icon inside this network is the same
                # steering `outbound` refuses for a redirect, and whoever runs
                # that site chose the link, not the administrator.
                log.warning("site icon: %s named an internal address, refused", page_url)
                continue
            data = _bytes(client, candidate.url, MAX_ICON_BYTES)
            kind = sniff(data) if data else None
            if kind:
                return SiteIcon(data, kind, candidate.url)
        return None
    finally:
        if owned:
            client.close()


def _is_public(url: str) -> bool:
    """True when every address the URL's host answers with is public."""
    try:
        return not outbound.inspect(url).is_internal
    except outbound.UnsafeUrl:
        return False


def _refuse_declared_oversize(response: httpx.Response) -> None:
    """Refuse a body that says it is too big, before it is downloaded.

    Runs on the headers, ahead of the body. A body sent without a length is
    still bounded by the timeout and refused by size afterwards.
    """
    declared = response.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_PAGE_BYTES:
        raise httpx.DecodingError(f"{declared} bytes is larger than a site icon or page should be")


def _bytes(client: httpx.Client, url: str, limit: int) -> bytes | None:
    """A body no larger than `limit`, or None for any failure.

    Every failure is the same answer here: this icon is not usable, try the next.
    """
    try:
        response = outbound.fetch(client, url)
    except (outbound.UnsafeUrl, httpx.HTTPError) as exc:
        log.info("site icon: %s not fetched: %s", url, exc)
        return None
    if response.status_code != 200 or len(response.content) > limit:
        return None
    return response.content


def _text(client: httpx.Client, url: str, limit: int) -> str | None:
    data = _bytes(client, url, limit)
    return data.decode("utf-8", errors="replace") if data else None
