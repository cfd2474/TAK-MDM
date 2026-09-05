"""Short-lived, stateless QR secrets derived from the primary enrollment token.

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
"""

from __future__ import annotations

import uuid

import pytest

from app.security import enrollment_qr as qr

PRIMARY = uuid.uuid4()


def guard(ttl_seconds: int = 900) -> qr.EnrollmentQrGuard:
    return qr.EnrollmentQrGuard(b"k" * 32, ttl_seconds=ttl_seconds)


def test_a_freshly_issued_secret_verifies():
    g = guard()
    secret = g.issue(PRIMARY, now=1000)

    assert g.verify(secret, now=1000) == PRIMARY


def test_it_still_verifies_moments_before_expiry():
    g = guard(ttl_seconds=900)
    secret = g.issue(PRIMARY, now=1000)

    assert g.verify(secret, now=1000 + 899) == PRIMARY


def test_it_is_refused_the_moment_it_expires():
    g = guard(ttl_seconds=900)
    secret = g.issue(PRIMARY, now=1000)

    with pytest.raises(qr.EnrollmentQrError, match="expired"):
        g.verify(secret, now=1000 + 901)


def test_a_secret_from_the_future_is_refused():
    g = guard()
    secret = g.issue(PRIMARY, now=10_000)

    with pytest.raises(qr.EnrollmentQrError):
        g.verify(secret, now=1_000)


def test_a_tampered_signature_is_refused():
    g = guard()
    secret = g.issue(PRIMARY, now=1000)
    forged = secret[:-4] + "AAAA"

    with pytest.raises(qr.EnrollmentQrError, match="signature"):
        g.verify(forged, now=1000)


def test_a_secret_signed_by_a_different_key_is_refused():
    # The scenario a key rotation produces: every QR in someone's camera roll
    # stops verifying, which is the point of rotating.
    secret = guard().issue(PRIMARY, now=1000)

    with pytest.raises(qr.EnrollmentQrError):
        qr.EnrollmentQrGuard(b"different-key-32-bytes-long!!!!", ttl_seconds=900).verify(
            secret, now=1000
        )


def test_the_primary_id_cannot_be_substituted():
    """Changing which primary a secret resolves to invalidates its signature.

    The id is inside the signed payload, not alongside it — an attacker who
    could edit it without invalidating the signature could point a captured QR
    at a primary of their choosing.
    """
    g = guard()
    secret = g.issue(PRIMARY, now=1000)
    other = str(uuid.uuid4())
    tampered = other + secret[len(str(PRIMARY)):]

    with pytest.raises(qr.EnrollmentQrError):
        g.verify(tampered, now=1000)


@pytest.mark.parametrize(
    "secret",
    [
        "",
        "not-a-qr-secret",
        "secrets.token_urlsafe-shaped-string-with-no-dots",
        f"{PRIMARY}.only.two.dots.here.too-many",
        "not-a-uuid.nonce.1000.sig",
        f"{PRIMARY}.nonce.not-a-number.sig",
    ],
)
def test_malformed_input_is_refused_not_crashed(secret):
    with pytest.raises(qr.EnrollmentQrError):
        guard().verify(secret, now=1000)


def test_an_ordinary_token_secret_never_verifies():
    """The shape check that lets resolve_token fall through safely.

    secrets.token_urlsafe never produces a '.', so a legacy 32-byte urlsafe
    secret can never accidentally parse as this four-part format.
    """
    import secrets as pysecrets

    ordinary = pysecrets.token_urlsafe(32)
    assert "." not in ordinary

    with pytest.raises(qr.EnrollmentQrError):
        guard().verify(ordinary, now=1000)


def test_two_issues_for_the_same_primary_in_the_same_second_differ():
    # Cosmetic, not a security property (see the module docstring's note on the
    # nonce) — but two QRs generated back to back should not look identical.
    g = guard()
    assert g.issue(PRIMARY, now=1000) != g.issue(PRIMARY, now=1000)


def test_load_or_create_persists_the_key(tmp_path):
    first = qr.EnrollmentQrGuard.load_or_create(tmp_path, ttl_seconds=900)
    secret = first.issue(PRIMARY, now=1000)

    second = qr.EnrollmentQrGuard.load_or_create(tmp_path, ttl_seconds=900)

    # A guard rebuilt from the same directory must verify a secret the first
    # instance issued, or every process restart would invalidate every live QR.
    assert second.verify(secret, now=1000) == PRIMARY
    assert (tmp_path / "enrollment_qr.key").exists()
