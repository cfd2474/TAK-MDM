# qmgc in ATLAS

`qmgc` encodes PNG frames into Samsung's Qmage (`.qmg`) animation format. ATLAS
runs it to make boot and shutdown animations (Content > Boot/shutdown
animations), because Samsung offers no tool for it.

- **Upstream:** https://github.com/BroBordd/qmgc, commit
  `553a718af645bf76eebccd0e95edc3a2538bf51e` (2026-10-28).
- **Licence:** GNU GPL version 3 or later — see `LICENSE`. ATLAS itself is
  Apache-2.0; `qmgc` is built as a **separate program** in the server image and
  run as a subprocess, never linked into ATLAS. This directory is its complete
  corresponding source, which ships with every ATLAS release.
- **Upstream's note on provenance:** "Built by reverse-engineering the
  bitstream against Peter Ross's FFmpeg decoder patch"; "Codec tables and
  bitstream logic are derived from FFmpeg's LGPL-2.1-or-later
  qmagedec.c/qmagedata.h".
- **Files kept:** `CMakeLists.txt`, `include/`, `src/`, `tools/`, `LICENSE`,
  `README.md`. Left out: `.gitignore`, `build.sh`.

## ATLAS modifications

One, in `src/encode.cpp` and `src/util.h`, each marked in place: the worker
count is fixed at **1** instead of `std::thread::hardware_concurrency()`. At this
commit, frames are converted in parallel and frame 1 records the expected size
while other threads already compare against it, so a multi-core machine fails
with "frame 3 is 1440x2304, expected 0x0". Found 2026-11-10 while making the
first test animation for the SM-X520; one thread is slower but correct.
