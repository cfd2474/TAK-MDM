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

"""Make Samsung boot and shutdown animations (W465 K2b-5).

Operator, 2026-11-10: the maker lives in Content, the operator names the
animation, says whether it is a bootup or a shutdown sequence, and the files
are named `<name>_boot`, `<name>_bootloop` or `<name>_shutdown`, so the policy
can offer them by a name the operator knows.

Samsung's rules, from its Knox SDK guide "Custom boot and shutdown animations"
(📖, linked from the Content card):

* PNG frames named `bootup01.png…bootup99.png`, `bootloop01.png…bootloop99.png`,
  `shutdown01.png…shutdown30.png`, in time order;
* at most 99 frames for bootup and for bootloop, **30** for shutdown;
* each PNG at most 2 MB, a zip at most 50 MB;
* "All QMG animations play at 12 frames per second" — so every frame is 83 ms
  (operator's choice, 2026-11-10; ✅ the SM-X520 proved the shutdown plays at
  the header's frame time, at 33 ms);
* PNGs "to suit the resolution of the device", so frames are scaled to a size
  the operator picks.

The encoder is `qmgc` (GPLv3, `third_party/qmgc`), run as a separate program.

⚠️ **A zip is read, never extracted.** Each member is checked by name and size
and read into memory; nothing from inside it becomes a path on this server, so
`../` in a member name has nothing to escape from.
"""

from __future__ import annotations

import io
import os
import re
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artifacts.storage import ArtifactStorage
from app.db.models import ManagedFile
from app.services import files as file_service

#: What the operator chooses, and the parts each makes.
BOOTUP = "bootup"
SHUTDOWN = "shutdown"
#: Samsung's frame prefix → the suffix ATLAS adds to the operator's name.
PARTS = {BOOTUP: (("bootup", "_boot"), ("bootloop", "_bootloop")), SHUTDOWN: (("shutdown", "_shutdown"),)}
SUFFIXES = ("_boot", "_bootloop", "_shutdown")
MAX_FRAMES = {"bootup": 99, "bootloop": 99, "shutdown": 30}
MAX_FRAME_BYTES = 2 * 1024 * 1024
MAX_ZIP_BYTES = 50 * 1024 * 1024
FRAME_MS = 83  # 12 frames per second, Samsung's stated rate
#: K2b-5f: how long a shutdown animation lasts, chosen by the operator. The
#: shutdown player plays at the header's frame time (✅ SM-X520); 12 frames at
#: 83 ms was one second, gone before the screen went dark.
SHUTDOWN_SECONDS = (1, 2, 3, 4, 5)
DEFAULT_SHUTDOWN_SECONDS = 3
MEDIA_TYPE = "application/x-samsung-qmg"
REFERENCE = ("https://docs.samsungknox.com/dev/knox-sdk/features/system-integrators/"
             "customization/prokiosk/custom-boot-and-shutdown-animations/")

_PNG = b"\x89PNG\r\n\x1a\n"
_FRAME = re.compile(r"^(bootup|bootloop|shutdown)(\d{2})\.png$", re.IGNORECASE)
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,80}$")


class AnimationError(ValueError):
    """Something the operator can fix; the message says what."""


@dataclass(frozen=True)
class Made:
    """One file made: its library name and id."""

    name: str
    file_id: str


def clean_name(raw: str) -> str:
    """The operator's name, checked. The suffix is ATLAS's, so it is refused."""
    name = (raw or "").strip()
    if not _NAME.match(name):
        raise AnimationError(
            "the name must start with a letter or digit and use only letters, digits, "
            "spaces, dots, dashes and underscores (at most 81 characters)")
    if name.lower().endswith(SUFFIXES):
        raise AnimationError("leave out _boot, _bootloop and _shutdown: ATLAS adds them")
    return name


def size_of(raw: str) -> tuple[int, int]:
    """'1440x2304' → (1440, 2304). Multiples of 4, as the format needs."""
    match = re.fullmatch(r"\s*(\d{2,5})\s*[xX×]\s*(\d{2,5})\s*", raw or "")
    if not match:
        raise AnimationError("give the screen size as width x height, e.g. 1440x2304")
    w, h = int(match.group(1)), int(match.group(2))
    if w % 4 or h % 4 or not (64 <= w <= 8192 and 64 <= h <= 8192):
        raise AnimationError("the width and height must be multiples of 4, between 64 and 8192")
    return w, h


def frames_from_zip(data: bytes, kind: str) -> dict[str, list[bytes]]:
    """Samsung-named PNG frames from a zip, per part, in order.

    Every rule refused names the file and the rule, because the zip was made
    by hand and the operator has to find what to change.
    """
    if len(data) > MAX_ZIP_BYTES:
        raise AnimationError("the zip is larger than Samsung's 50 MB limit")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise AnimationError("this is not a zip file") from None
    wanted = [prefix for prefix, _ in PARTS[kind]]
    found: dict[str, dict[int, bytes]] = {prefix: {} for prefix in wanted}
    for info in archive.infolist():
        base = info.filename.rsplit("/", 1)[-1]
        if info.is_dir() or not base or base.startswith(".") or info.filename.startswith("__MACOSX/"):
            continue
        match = _FRAME.match(base)
        if not match or match.group(1).lower() not in wanted:
            names = " and ".join(f"{p}01.png…" for p in wanted)
            raise AnimationError(f"{base}: a {kind} zip holds only frames named {names} (see Samsung's guide)")
        if info.file_size > MAX_FRAME_BYTES:
            raise AnimationError(f"{base}: larger than Samsung's 2 MB limit for a frame")
        prefix, number = match.group(1).lower(), int(match.group(2))
        if number in found[prefix]:
            raise AnimationError(f"{base}: frame {number:02d} appears twice")
        content = archive.read(info)
        if not content.startswith(_PNG):
            raise AnimationError(f"{base}: not a PNG image")
        found[prefix][number] = content
    return {prefix: _in_order(prefix, frames, optional=kind == BOOTUP) for prefix, frames in found.items()}


def frames_from_list(frames: dict[str, list[bytes]], kind: str) -> dict[str, list[bytes]]:
    """Frames the browser sent in order (K2b-5c), checked by the same rules."""
    out = {}
    for prefix, _ in PARTS[kind]:
        listed = frames.get(prefix) or []
        for i, content in enumerate(listed, start=1):
            if len(content) > MAX_FRAME_BYTES:
                raise AnimationError(f"{prefix} frame {i}: larger than Samsung's 2 MB limit")
            if not content.startswith(_PNG):
                raise AnimationError(f"{prefix} frame {i}: not a PNG image")
        out[prefix] = _in_order(prefix, dict(enumerate(listed, start=1)), optional=kind == BOOTUP)
    return out


def _in_order(prefix: str, frames: dict[int, bytes], optional: bool = False) -> list[bytes]:
    """The frames 1..n in order. `optional`: a bootup part may be empty, because
    `complete` fills it from the other part (K2b-5e)."""
    if not frames:
        if optional:
            return []
        raise AnimationError(f"no {prefix} frames: {prefix}01.png is the first")
    if len(frames) > MAX_FRAMES[prefix]:
        raise AnimationError(f"{len(frames)} {prefix} frames: Samsung allows at most {MAX_FRAMES[prefix]}")
    missing = [n for n in range(1, len(frames) + 1) if n not in frames]
    if missing:
        raise AnimationError(f"{prefix}{missing[0]:02d}.png is missing: frames are numbered 01, 02, … with no gap")
    return [frames[n] for n in range(1, len(frames) + 1)]


def complete(frames: dict[str, list[bytes]], kind: str) -> tuple[dict[str, list[bytes]], list[str]]:
    """Fill an empty bootup part from the other one, and say what was done (K2b-5e).

    Samsung's call needs both the boot animation and the loop. Operator,
    2026-11-10, asked to fill the empty one rather than refuse:

    * frames only for the boot animation: the loop **holds its last frame**
      until the device is ready;
    * frames only for the loop: the same frames **also play once** first.
    """
    if kind != BOOTUP:
        return frames, []
    boot, loop = list(frames.get("bootup") or []), list(frames.get("bootloop") or [])
    if not boot and not loop:
        raise AnimationError("no frames: add them to the boot animation, the boot loop, or both")
    notes = []
    if not loop:
        loop = [boot[-1]]
        notes.append("The boot loop holds the boot animation's last frame until the device is ready.")
    if not boot:
        boot = list(loop)
        notes.append("The boot loop's frames also play once as the boot animation.")
    return {"bootup": boot, "bootloop": loop}, notes


def frame_ms(prefix: str, count: int, shutdown_seconds: float) -> int:
    """The frame time for one part (K2b-5f).

    Boot parts keep Samsung's 12 fps: the boot player keeps its own pace (✅ it
    showed at the right speed whatever the header said). A shutdown spreads its
    frames over the length the operator chose, between 33 ms and 1 s a frame.
    """
    if prefix != "shutdown" or count <= 0:
        return FRAME_MS
    return max(33, min(1000, round(shutdown_seconds * 1000 / count)))


def turn_clockwise(frames: list[bytes]) -> list[bytes]:
    """Each PNG turned 90° clockwise (K2b-5f).

    ✅ Measured on the SM-X520 held in landscape: the shutdown player shows the
    panel-sized (portrait) canvas turned 90° counter-clockwise — its top edge at
    the left, its top-left corner at the bottom left, not mirrored. Turning the
    frames clockwise first shows landscape art upright. The boot player fits the
    canvas to the screen, so boot frames are never turned.
    """
    from PIL import Image, UnidentifiedImageError

    out = []
    for i, content in enumerate(frames, start=1):
        try:
            with Image.open(io.BytesIO(content)) as image:
                turned = image.transpose(Image.Transpose.ROTATE_270)  # 270° counter-clockwise = 90° clockwise
                buffer = io.BytesIO()
                turned.save(buffer, format="PNG")
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise AnimationError(f"shutdown frame {i}: could not be read as a PNG ({exc.__class__.__name__})") from None
        out.append(buffer.getvalue())
    return out


def name_taken(session: Session, name: str, kind: str) -> str | None:
    """The first library name this animation would reuse, or None."""
    names = [name + suffix for _, suffix in PARTS[kind]]
    return session.scalar(select(ManagedFile.name).where(ManagedFile.name.in_(names)).limit(1))


def encode(qmgc: str, frames: list[bytes], size: tuple[int, int], ms: int = FRAME_MS) -> bytes:
    """Run qmgc over the frames, in a directory of its own, and return the .qmg."""
    if not os.path.isfile(qmgc):
        raise AnimationError("the animation converter (qmgc) is not installed on this server")
    with tempfile.TemporaryDirectory(prefix="atlas-qmg-") as work:
        paths = []
        for i, content in enumerate(frames, start=1):
            path = Path(work) / f"frame{i:03d}.png"
            path.write_bytes(content)
            paths.append(str(path))
        out = Path(work) / "out.qmg"
        command = [qmgc, "--delay", str(ms), "--force-animation",
                   "--scale", f"{size[0]}x{size[1]}", *paths, str(out)]
        try:
            done = subprocess.run(command, capture_output=True, text=True, timeout=600, check=False)
        except subprocess.TimeoutExpired:
            raise AnimationError("making the animation took longer than 10 minutes") from None
        if done.returncode != 0 or not out.exists():
            detail = (done.stderr or done.stdout or "no message").strip().splitlines()[-1:]
            raise AnimationError(f"the converter could not make the animation: {' '.join(detail)}")
        data = out.read_bytes()
    if not data.startswith(b"QM"):
        raise AnimationError("the converter's output is not a .qmg file")
    return data


def make(session: Session, storage: ArtifactStorage, *, qmgc: str, name: str, kind: str,
         size: tuple[int, int], frames: dict[str, list[bytes]],
         turn_shutdown: bool = False, shutdown_seconds: float = DEFAULT_SHUTDOWN_SECONDS) -> list[Made]:
    """Encode each part and store it in the library as `<name><suffix>`.

    K2b-5f: a shutdown is turned for a landscape tablet when asked, and spread
    over the chosen length.
    """
    taken = name_taken(session, name, kind)
    if taken:
        raise AnimationError(f"{taken} already exists in Content: choose another name, or delete it first")
    made = []
    for prefix, suffix in PARTS[kind]:
        part = frames[prefix]
        ms = frame_ms(prefix, len(part), shutdown_seconds)
        turned = prefix == "shutdown" and turn_shutdown
        data = encode(qmgc, turn_clockwise(part) if turned else part, size, ms)
        detail = f"{kind} animation, {_frames(len(part))}, {size[0]}x{size[1]}"
        if prefix == "shutdown":
            detail += f", {len(part) * ms / 1000:g} s" + (", turned for a landscape tablet" if turned else "")
        managed = file_service.ingest_file(
            session, storage, data, name=name + suffix, original_filename=name + suffix + ".qmg",
            description=detail, media_type=MEDIA_TYPE, in_library=True)
        made.append(Made(managed.name, str(managed.id)))
    return made


def store_ready(session: Session, storage: ArtifactStorage, *, name: str, kind: str,
                files: dict[str, bytes]) -> list[Made]:
    """Ready-made .qmg files (e.g. Samsung's), named the same way.

    ⚠️ Checked by extension in the route, not by header: the format is
    Samsung's and undocumented, and a guessed check could refuse a real file.
    """
    taken = name_taken(session, name, kind)
    if taken:
        raise AnimationError(f"{taken} already exists in Content: choose another name, or delete it first")
    made = []
    for prefix, suffix in PARTS[kind]:
        data = files.get(prefix) or b""
        if not data:
            raise AnimationError(f"a {kind} needs its {prefix}.qmg")
        managed = file_service.ingest_file(
            session, storage, data, name=name + suffix, original_filename=name + suffix + ".qmg",
            description=f"{kind} animation, uploaded ready-made", media_type=MEDIA_TYPE, in_library=True)
        made.append(Made(managed.name, str(managed.id)))
    return made


def _frames(count: int) -> str:
    return f"{count} frame" if count == 1 else f"{count} frames"


def library(session: Session) -> list[ManagedFile]:
    """Every animation in Content, by name."""
    return list(session.scalars(
        select(ManagedFile).where(ManagedFile.in_library, ManagedFile.media_type == MEDIA_TYPE)
        .order_by(ManagedFile.name)))


def device_sizes(session: Session) -> list[tuple[str, str, bool]]:
    """(label, 'WxH', is_tablet) for each device model ATLAS knows a screen size for.

    `is_tablet`: Android's ScreenLayout size class is large or xlarge (3 or 4),
    which is what defaults "Landscape tablet: turn the shutdown animation" on.
    """
    from app.db.models import PlayDeviceProfile

    sizes = []
    for profile in session.scalars(select(PlayDeviceProfile).order_by(PlayDeviceProfile.model)):
        props = profile.properties or {}
        w, h = props.get("Screen.Width"), props.get("Screen.Height")
        if str(w).isdigit() and str(h).isdigit():
            layout = str(props.get("ScreenLayout", ""))
            tablet = layout.isdigit() and int(layout) & 0x0F >= 3
            sizes.append((f"{profile.model} — {w}x{h}", f"{w}x{h}", tablet))
    return sizes
