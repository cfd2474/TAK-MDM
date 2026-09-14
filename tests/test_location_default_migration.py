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

"""The fleet reaches the location default it was already promised (W161 follow-up).

⚠️ **These run the migration's real `upgrade()`**, with `op.get_bind()` pointed at
the test database, rather than reading the file and re-implementing what it does.
The previous migration was covered by asserting that certain strings appeared in
its source, which cannot fail for a migration whose SQL is wrong — and SQL that is
wrong is the entire risk here, because a migration runs once, unattended, on a
deployment nobody is watching.
"""

from __future__ import annotations

import importlib.util
import pathlib
import uuid
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy import select

from app.db.models import AppSetting, Device, EffectivePolicyCache, EnrollmentState

#: ⚠️ Loaded by path. `alembic/versions/` is not a package, and `import alembic`
#: finds the installed library instead — so the obvious import silently resolves
#: to something else entirely rather than failing in a way that names the cause.
_MIGRATION_PATH = pathlib.Path(
    "alembic/versions/g4i6k8m0o2q4_recompute_for_the_location_default.py"
)


def _migration():
    spec = importlib.util.spec_from_file_location("_w161_migration", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def run_migration(db, monkeypatch):
    """Run the real `upgrade()` against the test database."""

    def _run():
        db.flush()
        monkeypatch.setattr(
            "alembic.op.get_bind", lambda: db.connection(), raising=False
        )
        _migration().upgrade()
        db.expire_all()

    return _run


def _device(db, serial: str) -> Device:
    device = Device(
        id=uuid.uuid4(),
        serial_number=serial,
        enrollment_state=EnrollmentState.ENROLLED,
        state_version=3,
        acked_state_version=3,
    )
    db.add(device)
    db.flush()
    return device


def _cache(db, device: Device, *, stale: bool) -> EffectivePolicyCache:
    row = EffectivePolicyCache(
        device_id=device.id,
        state_version=device.state_version,
        payload={"values": {}, "apps": [], "store": [], "files": {}, "wallpaper": {}},
        stale=stale,
        computed_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    return row


# --------------------------------------------------------------------------- #
# The fleet recomputes
# --------------------------------------------------------------------------- #


def test_every_cached_device_is_marked_for_recompute(db, run_migration):
    """⚠️ The whole point. Without this the 15-minute default reached devices
    enrolled *after* the update and silently skipped the fleet already in the
    field — which works perfectly on whatever device you happen to test with."""
    fresh = _cache(db, _device(db, "MIG-FRESH"), stale=False)
    already = _cache(db, _device(db, "MIG-STALE"), stale=True)

    run_migration()

    assert db.get(EffectivePolicyCache, fresh.device_id).stale is True
    assert db.get(EffectivePolicyCache, already.device_id).stale is True


def test_the_payload_is_kept_rather_than_deleted(db, run_migration):
    """⚠️ Stale is not a delete.

    The stored payload is the baseline `refresh` compares against to decide
    whether `state_version` should move. Dropping the rows would make every
    device look changed and wake the entire fleet over nothing.
    """
    device = _device(db, "MIG-KEEP")
    row = _cache(db, device, stale=False)
    before = dict(row.payload)

    run_migration()

    after = db.get(EffectivePolicyCache, device.id)
    assert after is not None, "the row was deleted"
    assert after.payload == before
    assert after.state_version == 3, "the version is the resolver's to move, not ours"


def test_a_device_with_no_cache_row_is_untouched(db, run_migration):
    """A device that has never been resolved needs nothing: its first read
    computes from scratch and gets the default anyway."""
    device = _device(db, "MIG-NONE")

    run_migration()

    assert db.get(EffectivePolicyCache, device.id) is None


def test_it_runs_on_an_empty_fleet(db, run_migration):
    """A fresh install has no devices at all, and the migration still has to
    complete — it runs on every deployment, not only on upgrades."""
    run_migration()

    assert db.scalars(select(EffectivePolicyCache)).all() == []


# --------------------------------------------------------------------------- #
# Blank settings stop hiding their own defaults
# --------------------------------------------------------------------------- #


def test_a_blank_defaulted_setting_is_cleared(db, run_migration):
    """⚠️ Blank and absent behave identically, but only absent *shows* the default.

    On a box where the Location group had ever been saved, the retention field
    rendered an empty box beside help text promising 30 — the exact ambiguity the
    default was added to remove.
    """
    db.add(AppSetting(key="location.retention_days", value=""))
    db.add(AppSetting(key="location.default_interval_minutes", value="   "))
    db.flush()

    run_migration()

    assert db.get(AppSetting, "location.retention_days") is None
    assert db.get(AppSetting, "location.default_interval_minutes") is None


def test_a_real_value_is_never_touched(db, run_migration):
    """The operator meant 7 days. Nothing here may decide otherwise."""
    db.add(AppSetting(key="location.retention_days", value="7"))
    db.add(AppSetting(key="location.default_interval_minutes", value="0"))
    db.flush()

    run_migration()

    assert db.get(AppSetting, "location.retention_days").value == "7"
    assert db.get(AppSetting, "location.default_interval_minutes").value == "0", (
        "0 is a deliberate answer, not an empty one"
    )


def test_other_blank_settings_survive(db, run_migration):
    """⚠️ Scoped to the two keys that gained a displayed default.

    A blank SMTP host or tile URL means something — it is how those are switched
    off — and deleting them would be a settings change nobody asked for.
    """
    db.add(AppSetting(key="smtp.host", value=""))
    db.add(AppSetting(key="location.tile_url", value=""))
    db.flush()

    run_migration()

    assert db.get(AppSetting, "smtp.host") is not None
    assert db.get(AppSetting, "location.tile_url") is not None


# --------------------------------------------------------------------------- #
# Afterwards
# --------------------------------------------------------------------------- #


def test_the_effect_is_what_the_next_checkin_reads(db, run_migration, client, enrolled):
    """End to end: a device cached before the default existed gets it after.

    This is the claim the migration makes, rather than the SQL it runs to make it.
    """
    from app.services import effective_policy as eff
    from app.services import locations as location_service

    result = enrolled()
    device = db.get(Device, uuid.UUID(result["device_id"]))

    # Rewind this device's cache to what v1.11.0 would have left: resolved, not
    # stale, and with no interval in it. Enrolment has already created the row —
    # which is itself the point, since that is exactly the state of every device
    # that was in the field before the update.
    cached = db.get(EffectivePolicyCache, device.id)
    assert cached is not None, "enrolment no longer caches; this test needs rewriting"
    cached.payload = {
        "values": {}, "apps": [], "store": [], "files": {}, "wallpaper": {},
    }
    cached.stale = False
    db.flush()

    before = eff.get_effective(db, device)
    assert "TRACKING_FENCING" not in before["values"], "the stale cache is being served"

    run_migration()

    after = eff.get_effective(db, device)
    assert after["values"]["TRACKING_FENCING"][location_service.INTERVAL_FIELD] == 15


def test_downgrade_is_a_deliberate_no_op(db, run_migration):
    """A stale flag is a cache instruction, not data. There is nothing to restore,
    and re-inserting the blank settings rows would recreate a display bug on
    purpose."""
    run_migration()

    _migration().downgrade()  # must not raise


def test_the_migration_follows_the_current_head():
    """A revision that does not chain on is a migration that never runs."""
    migration = _migration()

    assert migration.revision == "g4i6k8m0o2q4"
    assert migration.down_revision == "f3h5j7l9n1p3"
