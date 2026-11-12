/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef QMGC_ENCODE_H
#define QMGC_ENCODE_H

#include "qmgc/types.h"
#include <cstdint>
#include <functional>
#include <vector>

namespace qmgc {

std::vector<uint8_t> encode_still(const Image& img);
// qversion: 0x0f, 0x0b, or 0 (default) for automatic. Automatic tries 0x0f first
// and falls back to 0x0b when a frame exceeds the 16-bit length field that
// 0x0f headers use (0x0b headers carry a 32-bit length, so no such limit).
std::vector<uint8_t> encode_animation(const std::vector<Image>& frames, int delay, int qversion = 0);

// Streaming animation encoder with bounded memory use.
//
// Instead of taking every frame up front, frames are pulled one at a time from
// `provider(index)` (index in [0, total)), and each encoded block is handed to
// `sink` as soon as it is ready, in order. Only a small window of frames
// (about one per worker thread, plus the previous 565 reference frame) is
// resident at any moment, so peak memory no longer grows with frame count.
//
// `provider` may be called more than once for the same index (the automatic
// 0x0f -> 0x0b fallback restarts the stream) and may be called from multiple
// threads concurrently, so it must be thread-safe. `reset`, if given, is
// invoked before a restart so the sink can discard whatever it already wrote
// (e.g. rewind + truncate a file). Without `reset`, the fallback is disabled
// and an oversized frame is reported as an error.
struct StreamSink {
    std::function<void(const uint8_t*, size_t)> write;
    std::function<void()> reset;
};
void encode_animation_stream(int total, const std::function<Image(int)>& provider, int delay,
                             const StreamSink& sink, int qversion = 0);

} // namespace qmgc

#endif
