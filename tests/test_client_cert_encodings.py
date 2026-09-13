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

"""However the proxy encodes the client certificate, the device is the same (W143).

Two proxies front this application and a header is all they have in common. The
standalone deployment runs nginx, whose `$ssl_client_escaped_cert` is
URL-encoded PEM. An InfraTAK module runs behind Caddy, whose only single-line
placeholder is base64 DER — `{http.request.tls.client.certificate_pem}` contains
real newlines and a header value cannot.

⚠️ **Encoding only.** None of this decides trust: issuer, signature, validity and
revocation are checked afterwards, and the proxy is still what proves the caller
holds the private key.
"""

from __future__ import annotations

import base64
from urllib.parse import quote

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient

from app.api.deps import _load_client_certificate


def _pem_of(enrolled_device) -> str:
    return enrolled_device["certificate_pem"]


def _der_base64(pem: str) -> str:
    cert = x509.load_pem_x509_certificate(pem.encode())
    return base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode()


# --------------------------------------------------------------------------- #
# The three shapes, at the parser
# --------------------------------------------------------------------------- #


def test_raw_pem_is_accepted(enrolled):
    pem = _pem_of(enrolled())

    assert _load_client_certificate(pem).subject


def test_url_encoded_pem_is_accepted(enrolled):
    """nginx's `$ssl_client_escaped_cert`, which the standalone deployment sends."""
    pem = _pem_of(enrolled())

    assert _load_client_certificate(quote(pem)) == _load_client_certificate(pem)


def test_base64_der_is_accepted(enrolled):
    """⚠️ Caddy's single-line form, and the reason this function exists."""
    pem = _pem_of(enrolled())

    assert _load_client_certificate(_der_base64(pem)) == _load_client_certificate(pem)


def test_a_folded_header_survives(enrolled):
    """A proxy that wraps a long header value is doing something legal, and the
    payload should survive it rather than becoming a 401 nobody can explain."""
    pem = _pem_of(enrolled())
    folded = "\n  ".join(
        _der_base64(pem)[i : i + 64] for i in range(0, len(_der_base64(pem)), 64)
    )

    assert _load_client_certificate(folded) == _load_client_certificate(pem)


@pytest.mark.parametrize("junk", ["", "   ", "not-a-certificate", "!!!!"])
def test_rubbish_is_refused_rather_than_guessed_at(junk):
    with pytest.raises(Exception):
        _load_client_certificate(junk)


# --------------------------------------------------------------------------- #
# ⚠️ End to end, because the parser alone proves nothing about the device
# --------------------------------------------------------------------------- #


def test_a_device_authenticates_with_caddys_encoding(
    client: TestClient, enrolled, settings
):
    """The whole point: the same device, recognised through the other proxy."""
    device = enrolled()
    header = {settings.client_cert_header: _der_base64(device["certificate_pem"])}

    response = client.post("/api/v1/device/checkin", json={"state_version": 0},
                           headers=header)

    assert response.status_code == 200, response.text


def test_an_unrelated_certificate_is_still_refused(client: TestClient, settings):
    """Accepting a new encoding must not accept a new issuer."""
    from tests.apk_fixtures import make_signing_certificate

    stranger = base64.b64encode(make_signing_certificate()).decode()

    response = client.post(
        "/api/v1/device/checkin",
        json={"state_version": 0},
        headers={settings.client_cert_header: stranger},
    )

    assert response.status_code == 401
