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

"""Replaying the QR URL lands somewhere usable (W150).

⚠️ `/enrollment/qr` is the one POST route that renders a page rather than
redirecting, so its URL stays in the address bar and anything that replays it
arrives as a GET. Observed live: an Authentik session lapsed mid-form, the edge
sent the operator through the outpost, and they returned to a POST-only path.
The app answered `{"detail": "Method Not Allowed"}` as JSON — in the middle of
enrolling a device.
"""

from __future__ import annotations

import ast
import io

from fastapi.testclient import TestClient


def test_a_get_lands_on_the_enrollment_page(client: TestClient):
    response = client.get("/enrollment/qr", follow_redirects=False)

    assert response.status_code in (302, 303, 307)
    assert response.headers["location"] == "/enrollment"


def test_it_is_no_longer_a_json_error(client: TestClient):
    """The exact page the operator saw."""
    response = client.get("/enrollment/qr", follow_redirects=True)

    assert "Method Not Allowed" not in response.text
    assert response.status_code == 200


def test_the_post_still_renders_the_page(client: TestClient):
    """⚠️ The fix must not cost the thing the route is for: the POST still
    answers with a page, where the GET now redirects.

    Asserted on the response *shape* rather than on the SSID appearing. Whether
    a QR can be drawn at all depends on a primary token and an uploaded agent
    build, which is a different question with its own tests — and a POST that
    started redirecting would pass a content check by accident.
    """
    response = client.post(
        "/enrollment/qr",
        data={"wifi_ssid": "FieldNet", "wifi_password": "s3cret", "wifi_security": "WPA"},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_a_get_mints_nothing(client: TestClient):
    """⚠️ Minting issues a signed short-lived secret. A GET that minted would
    hand one to a reload, a bookmark, or a browser prefetch."""
    from app.db.models import EnrollmentToken

    before = client.get("/api/v1/enrollment-tokens").json()
    client.get("/enrollment/qr", follow_redirects=True)
    after = client.get("/api/v1/enrollment-tokens").json()

    assert len(after) == len(before)


def test_no_other_post_route_renders_a_page_without_a_get(client: TestClient):
    """⚠️ The class of bug, not the instance. A POST that renders HTML leaves
    its URL in the address bar; without a GET, every replay of it is a JSON 405.
    """
    source = io.open("app/web/routes.py", encoding="utf-8").read()
    tree = ast.parse(source)
    posts_html: set[str] = set()
    gets: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            if not (isinstance(dec, ast.Call) and dec.args):
                continue
            first = dec.args[0]
            if not isinstance(first, ast.Constant):
                continue
            method = getattr(dec.func, "attr", "")
            if method == "get":
                gets.add(first.value)
            elif method == "post" and any(
                k.arg == "response_class" and getattr(k.value, "id", "") == "HTMLResponse"
                for k in dec.keywords
            ):
                posts_html.add(first.value)

    assert not (posts_html - gets), (
        f"POST routes that render a page but answer nothing on GET: "
        f"{sorted(posts_html - gets)}"
    )
