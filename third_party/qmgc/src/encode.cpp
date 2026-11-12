/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "qmgc/encode.h"

#include "encode_a9ll.h"
#include "encode_w2.h"
#include "qmgc/image.h"
#include "residual.h"
#include "util.h"

#include <algorithm>
#include <exception>
#include <mutex>
#include <thread>
#include <vector>

namespace qmgc {

std::vector<uint8_t> encode_still(const Image& img) {
    detail::init_resid_lut();
    return detail::encode_still_w2(img);
}

static std::vector<uint8_t> encode_animation_ver(const std::vector<Image>& frames, int delay, int qversion);

std::vector<uint8_t> encode_animation(const std::vector<Image>& frames, int delay, int qversion) {
    if (qversion == 0) {
        try {
            return encode_animation_ver(frames, delay, 0x0f);
        } catch (const QmgError&) {
            // Most likely a delta/keyframe too large for the 16-bit length field.
            return encode_animation_ver(frames, delay, 0x0b);
        }
    }
    if (qversion != 0x0b && qversion != 0x0f) throw QmgError("unsupported qversion (use 11 or 15)");
    return encode_animation_ver(frames, delay, qversion);
}

static std::vector<uint8_t> encode_animation_ver(const std::vector<Image>& frames, int delay, int qversion) {
    if (frames.empty()) throw QmgError("no frames");
    int width0 = frames[0].width, height0 = frames[0].height;
    for (size_t i = 0; i < frames.size(); ++i) {
        if (frames[i].width != width0 || frames[i].height != height0) {
            throw QmgError("frame " + std::to_string(i + 1) + " is " + std::to_string(frames[i].width) + "x" +
                           std::to_string(frames[i].height) + ", expected " + std::to_string(width0) + "x" +
                           std::to_string(height0));
        }
    }
    detail::init_resid_lut();
    int total = static_cast<int>(frames.size());
    std::vector<std::vector<uint16_t>> frames565(total);
    detail::parallel_for(total, [&](int i) { frames565[i] = pixels_to_565(frames[i]); });
    std::vector<std::vector<uint8_t>> outputs(total);
    outputs[0] = detail::encode_a9ll_keyframe(width0, height0, frames565[0], total, 1, delay, qversion);
    if (total > 1) {
        detail::parallel_for(total - 1, [&](int k) {
            int i = k + 1;
            int ordinal = i + 1;
            outputs[i] = detail::encode_a9ll_ani(width0, height0, frames565[i], frames565[i - 1], total, ordinal, delay, qversion);
        });
    }
    std::vector<uint8_t> out;
    size_t total_size = 0;
    for (auto& o : outputs) total_size += o.size();
    out.reserve(total_size);
    for (auto& o : outputs) out.insert(out.end(), o.begin(), o.end());
    return out;
}

// parallel_for variant that carries the first exception out of the worker
// threads (a throw escaping a std::thread would terminate the process).
template <typename Fn>
static void parallel_for_safe(int n, Fn&& fn) {
    std::exception_ptr first;
    std::mutex m;
    detail::parallel_for(n, [&](int k) {
        try {
            fn(k);
        } catch (...) {
            std::lock_guard<std::mutex> lk(m);
            if (!first) first = std::current_exception();
        }
    });
    if (first) std::rethrow_exception(first);
}

static void encode_stream_ver(int total, const std::function<Image(int)>& provider, int delay,
                             const StreamSink& sink, int qversion) {
    if (total <= 0) throw QmgError("no frames");
    detail::init_resid_lut();

    // ATLAS modification (2026-11-10): one thread. At upstream commit 553a718a
    // frame 1 sets the expected size while other threads already compare
    // against it (still 0x0): "frame 3 is WxH, expected 0x0". See ATLAS.md.
    unsigned hw = 1;
    if (hw == 0) hw = 4;
    // Batch size = number of frames in flight. Each batch holds `batch` decoded
    // images, `batch` 565 buffers and `batch` encoded blocks, then is flushed.
    const int batch = static_cast<int>(std::min<unsigned>(hw, 8u));

    int width0 = 0, height0 = 0;
    std::vector<uint16_t> prev565; // reference for the next delta frame
    std::vector<std::vector<uint16_t>> cur565;
    std::vector<std::vector<uint8_t>> outputs;

    for (int base = 0; base < total; base += batch) {
        int n = std::min(batch, total - base);
        cur565.assign(n, {});
        outputs.assign(n, {});
        parallel_for_safe(n, [&](int k) {
            int i = base + k;
            Image img = provider(i); // freed as soon as it is converted
            if (i == 0) {
                width0 = img.width;
                height0 = img.height;
            } else if (img.width != width0 || img.height != height0) {
                throw QmgError("frame " + std::to_string(i + 1) + " is " + std::to_string(img.width) + "x" +
                               std::to_string(img.height) + ", expected " + std::to_string(width0) + "x" +
                               std::to_string(height0));
            }
            cur565[k] = pixels_to_565(img);
        });
        parallel_for_safe(n, [&](int k) {
            int i = base + k;
            if (i == 0) {
                outputs[k] = detail::encode_a9ll_keyframe(width0, height0, cur565[0], total, 1, delay, qversion);
            } else {
                const std::vector<uint16_t>& ref = (k == 0) ? prev565 : cur565[k - 1];
                outputs[k] = detail::encode_a9ll_ani(width0, height0, cur565[k], ref, total, i + 1, delay, qversion);
            }
        });
        for (int k = 0; k < n; ++k) {
            sink.write(outputs[k].data(), outputs[k].size());
        }
        prev565 = std::move(cur565[n - 1]);
    }
}

void encode_animation_stream(int total, const std::function<Image(int)>& provider, int delay,
                             const StreamSink& sink, int qversion) {
    if (!sink.write) throw QmgError("stream sink has no write callback");
    if (qversion == 0) {
        if (!sink.reset) {
            encode_stream_ver(total, provider, delay, sink, 0x0f);
            return;
        }
        try {
            encode_stream_ver(total, provider, delay, sink, 0x0f);
        } catch (const QmgError& e) {
            // Only retry for the 16-bit length overflow; real errors (bad
            // frames, size mismatch) would fail identically under 0x0b.
            std::string msg = e.what();
            if (msg.find("too large") == std::string::npos) throw;
            sink.reset();
            encode_stream_ver(total, provider, delay, sink, 0x0b);
        }
        return;
    }
    if (qversion != 0x0b && qversion != 0x0f) throw QmgError("unsupported qversion (use 11 or 15)");
    encode_stream_ver(total, provider, delay, sink, qversion);
}

} // namespace qmgc
