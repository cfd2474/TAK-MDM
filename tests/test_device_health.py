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

"""Telling a device that never arrived from one that is merely away (W81)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db.models import Device, EnrollmentState
from app.services import device_health

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def _device(**kwargs) -> Device:
    defaults = {
        "serial_number": "R5CN00TAK01",
        "enrollment_state": EnrollmentState.ENROLLED,
        "created_at": NOW - timedelta(hours=1),
        "last_checkin_at": None,
    }
    return Device(**{**defaults, **kwargs})


def test_a_device_that_enrolled_and_never_arrived_is_flagged():
    assert device_health.enrollment_stalled(_device(), now=NOW) is True


def test_a_device_still_within_its_first_minutes_is_not():
    """A healthy device syncs seconds after provisioning, but a first sync racing
    a flaky network must never be called a failure."""
    fresh = _device(created_at=NOW - timedelta(minutes=1))
    assert device_health.enrollment_stalled(fresh, now=NOW) is False


def test_a_device_that_has_ever_checked_in_is_never_flagged():
    """⚠️ The distinction the whole thing rests on. A device that has reported
    once has a working identity; its silence afterwards is a network or power
    question, and a tablet on a boat for three weeks must not be called broken."""
    away = _device(last_checkin_at=NOW - timedelta(days=21))
    assert device_health.enrollment_stalled(away, now=NOW) is False


def test_a_device_that_never_finished_enrolling_is_not_flagged():
    """Nothing to diagnose: it never got as far as having an identity."""
    pending = _device(enrollment_state=EnrollmentState.PENDING)
    assert device_health.enrollment_stalled(pending, now=NOW) is False


def test_a_naive_created_at_does_not_hide_the_signal():
    """Stored naive on some backends. Letting the subtraction raise would take
    the whole flag out rather than one row."""
    naive = _device(created_at=(NOW - timedelta(hours=1)).replace(tzinfo=None))
    assert device_health.enrollment_stalled(naive, now=NOW) is True


def test_the_reason_names_both_causes_that_have_actually_happened():
    reason = device_health.stalled_reason().lower()
    assert "twice at once" in reason
    assert "reach the server" in reason
    # And says the record survives, so nobody deletes it trying to fix things.
    assert "readopts" in reason


def test_the_console_flags_a_stalled_device(client: TestClient, session_factory):
    """⚠️ Rendered, not asserted on the helper alone: the console said only
    "never", which is equally true of a device enrolled ten seconds ago."""
    with session_factory() as s:
        s.add(
            Device(
                serial_number="R5CX10FCY5D",
                model="SM-G736U1",
                enrollment_state=EnrollmentState.ENROLLED,
                created_at=datetime.now(timezone.utc) - timedelta(hours=2),
            )
        )
        s.add(
            Device(
                serial_number="R5GL40MMHRN",
                model="SM-X520",
                enrollment_state=EnrollmentState.ENROLLED,
                created_at=datetime.now(timezone.utc) - timedelta(hours=2),
                last_checkin_at=datetime.now(timezone.utc),
            )
        )
        s.commit()

    body = client.get("/").text
    import re

    # The pill itself, not the phrase: the same words appear in its tooltip, so a
    # bare substring count says two for a single flagged row.
    pills = re.findall(r'<span class="pill bad"[^>]*>\s*never checked in\s*</span>', body)
    assert len(pills) == 1, f"expected exactly one flagged row, found {len(pills)}"
    # And the healthy device beside it still shows a real timestamp.
    assert "SM-X520" in body
