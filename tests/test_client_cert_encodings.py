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


# --------------------------------------------------------------------------- #
# ⚠️ What the QR tells a device to trust (W143)
# --------------------------------------------------------------------------- #


def test_a_fronted_deployment_pins_no_ca(settings, tmp_path):
    """⚠️ The trap behind Caddy, stated rather than left to a missing file.

    `init` always runs `init-pki --dev-server-cert`, so `pki/server.crt` exists
    even on a deployment whose TLS is terminated by a proxy holding a
    *publicly-issued* certificate. Shipping that CA in the QR makes every device
    fail the handshake at provisioning time, with nothing on the tablet to
    explain it.
    """
    from app.services import provisioning

    (tmp_path / "server.crt").write_text("-----BEGIN CERTIFICATE-----\nnot-used\n")
    fronted = settings.model_copy(
        update={"pki_dir": str(tmp_path), "include_server_ca": False}
    )

    extras = provisioning.admin_extras(fronted, "secret")

    assert "server_ca_pem" not in extras


def test_a_standalone_deployment_still_pins_its_own(settings, tmp_path):
    """The self-signed case, unchanged: the agent has no other way to trust it."""
    from app.services import provisioning

    (tmp_path / "server.crt").write_text("-----BEGIN CERTIFICATE-----\nlocal\n")
    standalone = settings.model_copy(update={"pki_dir": str(tmp_path)})

    assert "server_ca_pem" in provisioning.admin_extras(standalone, "secret")


def test_asking_to_pin_nothing_is_refused(settings, tmp_path):
    """⚠️ `include_server_ca: True` with no certificate would provision devices
    with nothing to trust. Louder than shipping a QR that cannot work."""
    from app.services import provisioning

    misconfigured = settings.model_copy(
        update={"pki_dir": str(tmp_path), "include_server_ca": True}
    )

    with pytest.raises(provisioning.ProvisioningError) as raised:
        provisioning.admin_extras(misconfigured, "secret")

    assert "nothing to trust" in str(raised.value)


def test_the_ca_switch_reaches_the_container():
    """⚠️ A setting the container never sees is not a setting.

    `docker-compose.yml` has no `env_file`, so a variable written into `.env`
    reaches the application only where compose names it. The switch was added,
    written to `.env` by the module, and did nothing at all until this appeared
    in the api service's environment.
    """
    import io

    compose = io.open("docker-compose.yml", encoding="utf-8").read()

    assert "TAKMDM_INCLUDE_SERVER_CA: ${TAKMDM_INCLUDE_SERVER_CA:-}" in compose


def test_the_database_password_is_not_a_literal():
    """An InfraTAK module has to generate its own database credential, and a
    hardcoded one is a security-scan finding. The default keeps a laptop
    `docker compose up` working unchanged."""
    import io

    compose = io.open("docker-compose.yml", encoding="utf-8").read()

    assert "POSTGRES_PASSWORD: ${TAKMDM_DB_PASSWORD:-takmdm}" in compose
    assert "postgresql+psycopg://takmdm:${TAKMDM_DB_PASSWORD:-takmdm}@db" in compose


def test_the_admin_group_can_be_explicitly_blank():
    """⚠️ `-`, not `:-`. A deployment whose proxy already restricts the
    application sets this empty to mean "trust the identity provider"; with the
    colon form that empty value became `takmdm-admins`, a group the proxy has
    never heard of, and every administrator was refused."""
    import io

    compose = io.open("docker-compose.yml", encoding="utf-8").read()

    assert "TAKMDM_ADMIN_GROUP: ${TAKMDM_ADMIN_GROUP-takmdm-admins}" in compose


def test_the_image_runs_as_uid_1000():
    """The InfraTAK module chowns the bind mounts to this uid before starting
    anything. If the image ever moved, every deploy would fail writing its own
    device CA — and the compose output would not say the word "permission"."""
    import io

    dockerfile = io.open("Dockerfile", encoding="utf-8").read()

    assert "--uid 1000" in dockerfile


def test_the_writable_host_directories_are_the_three_we_prepare():
    """⚠️ A new writable bind mount is a new root-owned directory the container
    cannot write. Adding one here without telling the module about it breaks
    deployment on the InfraTAK side only, where nothing runs as root."""
    import io

    import yaml

    compose = yaml.safe_load(io.open("docker-compose.yml", encoding="utf-8").read())
    writable = set()
    for name in ("api", "init"):
        for volume in compose["services"][name].get("volumes") or []:
            host = volume.split(":")[0]
            if host.startswith("./") and ":ro" not in volume:
                writable.add(host[2:].rstrip("/"))

    assert writable == {"pki", "artifacts", "cache"}, (
        f"writable bind mounts changed to {sorted(writable)} — teach the InfraTAK "
        f"module's WRITABLE_DIRS about it, or the container cannot write them"
    )
