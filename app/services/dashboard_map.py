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

"""Every enrolled device's last known location, for the dashboard map (W442).

The sample: "Dots group devices within about 1 km per agency, sized by
count, colored by the oldest bucket shown." The grouping is done in the
browser, after the bucket switches and the group filter, so changing either
redraws without a request. This only supplies one point per device.

⚠️ **Compact on purpose.** It is fetched with every refresh, and a fleet of
two thousand devices as objects with named keys is several times the size of
the same thing as short arrays. The shape is documented on `read`.

⚠️ **One query for the latest point**, not `locations.latest` per device: that
is one round trip per device on every refresh of the landing page.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Device, DeviceLocation, EnrollmentState
from app.services import dashboard_fleet, locations

BUCKET_KEYS = [key for key, _ in dashboard_fleet.BUCKETS]


def read(session: Session, now: datetime | None = None) -> dict:
    """`devices`: `[id, label, latitude, longitude, bucket index, [group indexes]]`;
    `groups`: names, indexed by the above ("No group" among them when used);
    `buckets`: keys, indexed by the above; `tiles`: the console's map source.
    """
    now = now or datetime.now(timezone.utc)
    newest = (
        select(DeviceLocation.device_id, func.max(DeviceLocation.recorded_at).label("at"))
        .group_by(DeviceLocation.device_id)
        .subquery()
    )
    rows = session.execute(
        select(Device, DeviceLocation.latitude, DeviceLocation.longitude)
        .join(newest, newest.c.device_id == Device.id)
        .join(DeviceLocation, (DeviceLocation.device_id == newest.c.device_id)
              & (DeviceLocation.recorded_at == newest.c.at))
        .where(Device.enrollment_state == EnrollmentState.ENROLLED)
    ).all()

    group_index: dict[str, int] = {}
    groups: list[str] = []

    def index_of(name: str) -> int:
        if name not in group_index:
            group_index[name] = len(groups)
            groups.append(name)
        return group_index[name]

    devices, seen = [], set()
    for device, latitude, longitude in sorted(rows, key=lambda r: r[0].serial_number):
        if device.id in seen:
            continue  # two points with the same newest time: one dot, not two
        seen.add(device.id)
        names = sorted((g.name for g in device.groups), key=str.casefold) or [dashboard_fleet.NO_GROUP]
        devices.append([
            str(device.id),
            device.name or device.serial_number,
            round(latitude, 6),
            round(longitude, 6),
            BUCKET_KEYS.index(dashboard_fleet.bucket(device.last_checkin_at, now)),
            [index_of(n) for n in names],
        ])
    return {
        "devices": devices,
        "groups": groups,
        "buckets": BUCKET_KEYS,
        "tiles": locations.tile_config(session),
    }
