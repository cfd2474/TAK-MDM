# qmgc

Encoder for Samsung's Qmage (`.qmg`) boot-animation and still-image format.
Built by reverse-engineering the bitstream against Peter Ross's FFmpeg
decoder patch and validated against real on-device samples.

## Building

With CMake (preferred):

```sh
cmake -B build
cmake --build build
./build/qmgc frame0.png frame1.png out.qmg
```

Without CMake:

```sh
sh build.sh
./qmgc frame0.png frame1.png out.qmg
```

Requires **libpng-dev**. JPEG input needs **libjpeg-dev** (optional; PNG-only
builds work without it).

## Usage

```sh
qmgc [--delay N] [--force-animation] [--scale WxH] input... output.qmg
```

- One PNG/JPEG input → still image (W2_PASS, qversion 0x0b)
- Multiple inputs, or `--force-animation` → A9LL animation (qversion 0x0f)
- `--delay N` — per-frame delay field in the animation header (centiseconds)
- `--scale WxH` — resize all inputs before encoding

## Repo layout

```
include/qmgc/     public headers (encode.h, image.h, types.h)
src/              library implementation
  tables.h        residual delta table, prediction direction vectors
  bitwriter.h     MSB-first bit packing (matches decoder)
  predict.h       mode selection + Samsung hardware OOB predictor rules
  residual.*      O(1) residual lookup table
  encode_w2.*     still-image W2_PASS encoder
  encode_a9ll.*   animation A9LL keyframe + delta encoder
  encode.cpp      top-level encode_still / encode_animation
  image.cpp       PNG/JPEG loading, RGB565 conversion
tools/            qmgc CLI
```

## License

GPLv3 (or later) — see [`LICENSE`](LICENSE). Codec tables and bitstream
logic are derived from FFmpeg's LGPL-2.1-or-later `qmagedec.c`/`qmagedata.h`.
