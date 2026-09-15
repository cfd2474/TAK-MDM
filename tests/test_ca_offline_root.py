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

"""Taking the root offline, without stranding a fleet (W172, SEC_AUDIT S-2).

The whole exercise turns *permanent, unrecoverable* compromise into *bounded and
revocable*: steal the box and you get an intermediate that expires and can be
revoked, not a ten-year root that can only be answered by re-enrolling every
tablet by hand.

⚠️ **The dangerous case is not the attack, it is the migration.** A deployment
whose root key has gone offline looks — to code written before this — exactly like
a fresh install. `load_or_create` used to generate a new CA in that state, which
would invalidate every enrolled device at once. Several tests below exist only to
hold that line.
"""

from __future__ import annotations

import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization

from app.security.ca import (
    CertificateAuthority,
    CertificateError,
    RootKeyMissing,
    issue_intermediate,
)
from tests.conftest import ADMIN_HEADERS


def _root(pki):
    return CertificateAuthority.load_or_create(
        pki, common_name="ATLAS Test Root", validity_days=3650
    )


def _utc_now():
    import datetime as _dt

    return _dt.datetime.now(_dt.timezone.utc)


def _enrol(authority: CertificateAuthority):
    """A device certificate from whatever this CA currently signs with."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    device_id = uuid.uuid4()
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, str(device_id))]))
        .sign(key, hashes.SHA256())
    )
    issued = authority.sign_csr(
        csr.public_bytes(serialization.Encoding.PEM).decode(),
        device_id=device_id,
        serial_number="TEST-DEVICE",
        validity_days=825,
    )
    return x509.load_pem_x509_certificate(issued.to_pem().encode())


@pytest.fixture
def cli_pki(tmp_path, monkeypatch):
    """Point the CLI at a scratch PKI, and put the settings cache back afterwards.

    ⚠️ `get_settings` is an `lru_cache`. Clearing it on the way in and not on the
    way out leaves every later test holding a Settings that names a temp directory
    pytest has since deleted — which surfaced as unrelated CSRF failures in the
    full suite while this file passed in isolation. Teardown is the half that
    matters.
    """
    from app.config import get_settings

    pki = tmp_path / "pki"
    _root(pki)
    monkeypatch.setenv("TAKMDM_PKI_DIR", str(pki))
    get_settings.cache_clear()
    try:
        yield pki
    finally:
        get_settings.cache_clear()


# --------------------------------------------------------------------------- #
# The ceremony
# --------------------------------------------------------------------------- #


def test_an_intermediate_is_signed_by_the_root(tmp_path):
    pki = tmp_path / "pki"
    root = _root(pki)

    intermediate = issue_intermediate(
        pki, common_name="ATLAS Issuing CA", validity_days=365
    )

    assert intermediate.issuer == root.certificate.subject
    assert (pki / "issuing.crt").exists()
    assert (pki / "issuing.key").exists()


def test_the_intermediate_may_not_sign_another_ca(tmp_path):
    """⚠️ `path_length=0`, or the bound this buys evaporates.

    Without it a stolen intermediate could mint intermediates of its own, and
    revoking the one you know about would achieve nothing.
    """
    pki = tmp_path / "pki"
    _root(pki)

    intermediate = issue_intermediate(
        pki, common_name="ATLAS Issuing CA", validity_days=365
    )

    constraints = intermediate.extensions.get_extension_for_class(
        x509.BasicConstraints
    ).value
    assert constraints.ca is True
    assert constraints.path_length == 0


def test_the_intermediate_takes_over_signing(tmp_path):
    pki = tmp_path / "pki"
    _root(pki)
    issue_intermediate(pki, common_name="ATLAS Issuing CA", validity_days=365)

    authority = _root(pki)

    assert authority.certificate.subject.rfc4514_string() == "CN=ATLAS Issuing CA"


def test_the_root_key_can_then_be_removed(tmp_path):
    """The state the whole exercise is for."""
    pki = tmp_path / "pki"
    _root(pki)
    issue_intermediate(pki, common_name="ATLAS Issuing CA", validity_days=365)

    (pki / "ca.key").unlink()
    authority = _root(pki)

    assert authority.certificate.subject.rfc4514_string() == "CN=ATLAS Issuing CA"
    assert len(authority.trusted) == 2, "the root is still the anchor"


# --------------------------------------------------------------------------- #
# ⚠️ The line that must never move
# --------------------------------------------------------------------------- #


def test_a_missing_root_key_never_regenerates_the_ca(tmp_path):
    """⚠️ The single most dangerous behaviour in this work.

    Before W172, `load_or_create` generated a new CA whenever the key was absent.
    After the root goes offline that is the *normal* state — so the old code would
    have minted a fresh trust anchor and every enrolled device would have failed
    authentication on its next check-in, with no remedy short of re-enrolling the
    fleet by hand.
    """
    pki = tmp_path / "pki"
    original = _root(pki).certificate.public_bytes(serialization.Encoding.PEM)
    (pki / "ca.key").unlink()

    with pytest.raises(RootKeyMissing):
        _root(pki)

    assert (pki / "ca.crt").read_bytes() == original, "the root certificate was replaced"


def test_the_refusal_says_how_to_recover(tmp_path):
    """A stop with no way forward is an outage. This one names both routes."""
    pki = tmp_path / "pki"
    _root(pki)
    (pki / "ca.key").unlink()

    with pytest.raises(RootKeyMissing) as raised:
        _root(pki)

    message = str(raised.value)
    assert "issuing.key" in message and "restore" in message
    assert "ca-issue-intermediate" in message
    assert "every enrolled device" in message


def test_a_first_install_still_creates_a_root(tmp_path):
    """Nothing above may break the empty-directory case."""
    authority = _root(tmp_path / "pki")

    assert (tmp_path / "pki" / "ca.crt").exists()
    assert authority.trusted == (authority.certificate,)


# --------------------------------------------------------------------------- #
# Rotation, and the fleet that is mid-flight
# --------------------------------------------------------------------------- #


def test_rotating_retires_the_old_intermediate_rather_than_deleting_it(tmp_path):
    pki = tmp_path / "pki"
    _root(pki)
    first = issue_intermediate(pki, common_name="ATLAS Issuing CA", validity_days=365)

    second = issue_intermediate(pki, common_name="ATLAS Issuing CA 2", validity_days=365)

    retired = list((pki / "retired").glob("*.crt"))
    assert len(retired) == 1
    kept = x509.load_pem_x509_certificate(retired[0].read_bytes())
    assert kept.serial_number == first.serial_number
    assert second.serial_number != first.serial_number


def test_devices_from_a_retired_intermediate_still_authenticate(tmp_path):
    """⚠️ The fleet-wide outage this avoids.

    A device holds its certificate for 825 days. Rotating the intermediate every
    year means most of the fleet is chained through one that no longer signs, and
    dropping it from the trust store would lock them all out at once.
    """
    pki = tmp_path / "pki"
    _root(pki)
    issue_intermediate(pki, common_name="ATLAS Issuing CA", validity_days=365)

    device_cert = _enrol(_root(pki))

    issue_intermediate(pki, common_name="ATLAS Issuing CA 2", validity_days=365)
    new_authority = _root(pki)

    new_authority.verify(device_cert)


def test_the_trust_bundle_grows_with_each_rotation(tmp_path):
    pki = tmp_path / "pki"
    _root(pki)
    issue_intermediate(pki, common_name="ATLAS Issuing CA", validity_days=365)
    issue_intermediate(pki, common_name="ATLAS Issuing CA 2", validity_days=365)

    bundle = _root(pki).trust_bundle_pem()

    # Root, the retired intermediate, and the current one.
    assert bundle.count("BEGIN CERTIFICATE") == 3


# --------------------------------------------------------------------------- #
# Issuing an intermediate needs the root, which is the point
# --------------------------------------------------------------------------- #


def test_issuing_without_the_root_key_is_refused(tmp_path):
    pki = tmp_path / "pki"
    _root(pki)
    issue_intermediate(pki, common_name="ATLAS Issuing CA", validity_days=365)
    (pki / "ca.key").unlink()

    with pytest.raises(CertificateError, match="root key"):
        issue_intermediate(pki, common_name="ATLAS Issuing CA 2", validity_days=365)


def test_the_refusal_explains_the_ceremony(tmp_path):
    pki = tmp_path / "pki"
    _root(pki)
    (pki / "ca.key").unlink()

    with pytest.raises(CertificateError) as raised:
        issue_intermediate(pki, common_name="x", validity_days=365)

    assert "bring it back" in str(raised.value)


# --------------------------------------------------------------------------- #
# ⚠️ The intermediate's life caps every certificate it signs
# --------------------------------------------------------------------------- #


def test_the_issuer_always_outlives_what_it_signs(tmp_path):
    """⚠️ This asserted the opposite until W175, and the old version was right
    about the code at the time.

    A 365-day intermediate used to issue 825-day certificates that outlived it —
    which is exactly why a device could be stranded with most of its validity
    unused. Certificates are now capped at the issuer's expiry, so the relationship
    is inverted by construction and the truncation warning in the CLI is about
    *ceremony frequency* rather than about stranding devices.
    """
    pki = tmp_path / "pki"
    _root(pki)
    issue_intermediate(pki, common_name="ATLAS Issuing CA", validity_days=365)
    authority = _root(pki)

    device_cert = _enrol(authority)

    assert device_cert.not_valid_after_utc < authority.certificate.not_valid_after_utc


def test_the_shipped_default_strands_nobody(cli_pki, capsys):
    """The default `--days` must exceed the device certificate validity.

    Run through `main()` rather than by reading the constant, so the number an
    operator actually gets is the one under test.
    """
    from app.cli import main

    assert main(["ca-issue-intermediate"]) == 0
    output = capsys.readouterr().out

    assert "WARNING" not in output, output
    certificate = x509.load_pem_x509_certificate((cli_pki / "issuing.crt").read_bytes())
    device_cert = _enrol(_root(cli_pki))
    assert certificate.not_valid_after_utc > device_cert.not_valid_after_utc


def test_a_truncating_interval_is_called_out(cli_pki, capsys):
    """⚠️ Saying it is the whole mitigation — the command still proceeds.

    Refusing would be wrong: an operator who has accepted the re-enrolment, or who
    has a renewal process this repository does not know about, is entitled to a
    short intermediate. What they are not entitled to is finding out later.
    """
    from app.cli import main
    from app.config import get_settings

    # ⚠️ Derived, not hardcoded. This test asserted "460 days" and "--days 1190",
    # both computed from an 825-day device certificate — so shortening that
    # default to 90 broke the test rather than the code, which is the wrong way
    # round for a guard.
    device_days = get_settings().device_cert_validity_days
    short = max(1, device_days // 2)

    assert main(["ca-issue-intermediate", "--days", str(short)]) == 0
    output = capsys.readouterr().out

    assert "WARNING" in output
    assert f"{device_days - short} days" in output, output
    assert f"--days {device_days + 365}" in output, "it must name the number that works"
    # ⚠️ And it must no longer claim a re-provision. Renewal exists (v1.22.0), so
    # a truncated certificate recovers on the next check-in; the old wording
    # promised a factory reset and was three releases out of date.
    assert "factory reset" not in output, output
    assert "renew themselves" in output, output


# --------------------------------------------------------------------------- #
# ⚠️ A certificate must never outlive the one that signed it (W175)
# --------------------------------------------------------------------------- #


def test_a_device_certificate_never_outlives_its_issuer(tmp_path):
    """⚠️ Without this, automatic renewal does not save the fleet.

    A device renews thirty days before *its own* expiry. One issued a long
    certificate shortly before its issuer expires stops authenticating when the
    issuer does — most of its own validity unused — and does not come back to ask
    for another until long after. Issuing a replacement intermediate rescues
    nobody, because nobody asks.
    """
    from app.security.ca import CertificateAuthority, issue_intermediate

    pki = tmp_path / "pki"
    _root(pki)
    # An intermediate with 40 days left, signing a certificate asked to last 825.
    issue_intermediate(pki, common_name="Short Issuer", validity_days=40)
    authority = _root(pki)

    device_cert = _enrol(authority)

    assert device_cert.not_valid_after_utc < authority.certificate.not_valid_after_utc
    remaining = (device_cert.not_valid_after_utc - _utc_now()).days
    assert 35 <= remaining <= 40, remaining


def test_a_certificate_well_inside_the_issuer_is_not_shortened(tmp_path):
    """The cap must not quietly truncate the ordinary case."""
    from app.security.ca import issue_intermediate

    pki = tmp_path / "pki"
    _root(pki)
    issue_intermediate(pki, common_name="Long Issuer", validity_days=1825)
    authority = _root(pki)

    device_cert = _enrol(authority)

    remaining = (device_cert.not_valid_after_utc - _utc_now()).days
    assert 820 <= remaining <= 825, remaining


def test_an_expired_issuer_refuses_rather_than_issuing_a_useless_certificate(tmp_path):
    """⚠️ A certificate valid for minutes looks like success and strands the device.

    The refusal names the command that fixes it, because this is reached by an
    operator whose intermediate lapsed and whose devices are already failing.
    """
    from app.security.ca import CertificateAuthority, CertificateError

    pki = tmp_path / "pki"
    _root(pki)
    # An issuer that expired yesterday.
    from cryptography import x509 as _x509
    from cryptography.hazmat.primitives import hashes, serialization as _ser
    from cryptography.hazmat.primitives.asymmetric import ec as _ec
    import datetime as _dt

    root_cert = _x509.load_pem_x509_certificate((pki / "ca.crt").read_bytes())
    root_key = _ser.load_pem_private_key((pki / "ca.key").read_bytes(), password=None)
    key = _ec.generate_private_key(_ec.SECP256R1())
    now = _dt.datetime.now(_dt.timezone.utc)
    stale = (
        _x509.CertificateBuilder()
        .subject_name(_x509.Name([_x509.NameAttribute(
            __import__("cryptography.x509.oid", fromlist=["NameOID"]).NameOID.COMMON_NAME,
            "Lapsed Issuer")]))
        .issuer_name(root_cert.subject)
        .public_key(key.public_key())
        .serial_number(_x509.random_serial_number())
        .not_valid_before(now - _dt.timedelta(days=400))
        .not_valid_after(now - _dt.timedelta(days=1))
        .add_extension(_x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(root_key, hashes.SHA256())
    )
    authority = CertificateAuthority(stale, key, trusted=[root_cert, stale])

    with pytest.raises(CertificateError, match="ca-issue-intermediate"):
        _enrol(authority)


# --------------------------------------------------------------------------- #
# The status the module page renders (W176)
# --------------------------------------------------------------------------- #


def test_ca_status_reports_a_legacy_deployment(cli_pki, capsys):
    import json

    from app.cli import main

    assert main(["ca-status"]) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["ok"] is True
    assert report["is_split"] is False
    assert report["root_key_on_server"] is True
    assert report["trust_anchors"] == 1


def test_ca_status_reports_a_split_deployment(cli_pki, capsys):
    """⚠️ `root_key_on_server: false` is the goal state.

    An operator who ran the ceremony but left the key behind has changed nothing
    about their exposure, and this is the field that says so.
    """
    import json

    from app.cli import main

    assert main(["ca-issue-intermediate"]) == 0
    capsys.readouterr()
    (cli_pki / "ca.key").unlink()

    assert main(["ca-status"]) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["is_split"] is True
    assert report["root_key_on_server"] is False
    assert report["trust_anchors"] == 2
    assert report["issuing_days_left"] > 1800


def test_ca_status_does_not_raise_on_a_broken_deployment(cli_pki, capsys):
    """⚠️ The state it is most needed in is the broken one.

    Root key removed, intermediate never issued — a status command that threw
    here would leave an operator with a blank page instead of the sentence
    explaining what to do.
    """
    import json

    from app.cli import main

    (cli_pki / "ca.key").unlink()

    assert main(["ca-status"]) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["ok"] is False
    assert report["root_certificate"] is True
    assert report["root_key_on_server"] is False
    assert "ca-issue-intermediate" in report["error"]


def test_ca_status_warns_months_before_expiry(cli_pki, capsys):
    """⚠️ 180 days, not 30. Reissuing needs the root fetched from wherever it
    went, which is not a same-afternoon task."""
    import json

    from app.cli import main

    assert main(["ca-issue-intermediate", "--days", "100"]) == 0
    capsys.readouterr()

    assert main(["ca-status"]) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["needs_attention"] is True


# --------------------------------------------------------------------------- #
# What the console claims about the root key (W185)
#
# ⚠️ The panel used to decide whether to print "The root is not on this server"
# from `is_split` — whether more than one trust anchor exists. The ceremony has
# two halves, and an operator who issues the intermediate and forgets to delete
# `ca.key` has a split chain and a ten-year root still on an internet-facing box.
# The console told exactly that operator the root was gone.
# --------------------------------------------------------------------------- #


def test_root_key_on_server_reads_the_file(tmp_path):
    from app.security import ca as ca_module

    pki = tmp_path / "pki"
    _root(pki)
    assert ca_module.root_key_on_server(pki) is True

    (pki / "ca.key").unlink()
    assert ca_module.root_key_on_server(pki) is False


def test_it_is_false_for_a_directory_that_does_not_exist(tmp_path):
    """A deployment with no PKI at all has no root key on it, and asking must not
    raise — this is read on every render of the admin page."""
    from app.security import ca as ca_module

    assert ca_module.root_key_on_server(tmp_path / "nothing-here") is False


def test_the_panel_reports_the_key_file_and_not_the_chain_shape(tmp_path):
    """⚠️ The regression. A split chain with the key still present is the one
    state where the two answers differ, and it is the state an interrupted
    ceremony leaves behind."""
    from app.web.routes import _issuing_ca_panel

    pki = tmp_path / "pki"
    _root(pki)
    issue_intermediate(pki, common_name="ATLAS Issuing CA", validity_days=1825)

    panel = _issuing_ca_panel(_root(pki), pki)

    assert panel["is_split"] is True
    assert panel["root_key_on_server"] is True, (
        "a split chain does not mean the root key has gone; the ceremony's "
        "second half is deleting it"
    )


def test_the_panel_says_the_root_is_gone_only_once_it_is(tmp_path):
    from app.web.routes import _issuing_ca_panel

    pki = tmp_path / "pki"
    _root(pki)
    issue_intermediate(pki, common_name="ATLAS Issuing CA", validity_days=1825)
    (pki / "ca.key").unlink()

    panel = _issuing_ca_panel(_root(pki), pki)

    assert panel["is_split"] is True
    assert panel["root_key_on_server"] is False


def test_the_panel_answers_even_with_no_certificate_authority(tmp_path):
    """⚠️ The broken deployment is exactly when somebody opens this page.

    A half-finished ceremony can leave nothing loadable, and the root-key
    question still has an answer worth showing.
    """
    from app.web.routes import _issuing_ca_panel

    pki = tmp_path / "pki"
    _root(pki)

    panel = _issuing_ca_panel(None, pki)

    assert panel["issuing_known"] is False
    assert panel["root_key_on_server"] is True


@pytest.fixture
def console_pki(tmp_path, settings):
    """Point the *console's* view at a scratch PKI.

    ⚠️ Not the real `pki/`. It is a real directory on a developer's machine, so a
    test that read it would pass or fail depending on whether that machine had
    ever run the ceremony.
    """
    pki = tmp_path / "console-pki"
    _root(pki)
    settings.pki_dir = pki
    return pki


def test_the_console_says_so_while_the_root_is_still_here(client, console_pki):
    body = client.get("/admin", headers=ADMIN_HEADERS).text

    assert "The root private key is on this server" in body
    assert "docs/CA-OFFLINE-ROOT.md" in body


def test_the_console_stops_saying_so_once_it_is_gone(client, console_pki):
    (console_pki / "ca.key").unlink()

    body = client.get("/admin", headers=ADMIN_HEADERS).text

    assert "The root private key is on this server" not in body
    assert "The root private key is not on this server" in body


def test_the_console_never_claims_the_key_is_somewhere_it_is_not(
    client, console_pki
):
    """⚠️ The sentence the old panel printed unconditionally.

    "The CA private key lives at pki/ca.key on the server" was in the footer
    whether or not the ceremony had been run, so the page contradicted itself in
    both directions at once.
    """
    (console_pki / "ca.key").unlink()

    body = client.get("/admin", headers=ADMIN_HEADERS).text

    assert "lives at" not in body
