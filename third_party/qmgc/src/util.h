/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <string>
#include <thread>
#include <vector>

namespace qmgc {
namespace detail {

inline uint16_t rgb565(uint8_t r, uint8_t g, uint8_t b) {
    return static_cast<uint16_t>(((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3));
}

inline void encode_value(uint32_t n, std::vector<uint8_t>& out) {
    while (n >= 0xFF) {
        out.push_back(0xFF);
        n -= 0xFF;
    }
    out.push_back(static_cast<uint8_t>(n & 0xFF));
}

inline void pad4(std::vector<uint8_t>& data) {
    size_t rem = (4 - (data.size() % 4)) % 4;
    data.resize(data.size() + rem, 0);
}

inline void put_u16le(std::vector<uint8_t>& out, uint16_t v) {
    out.push_back(static_cast<uint8_t>(v & 0xFF));
    out.push_back(static_cast<uint8_t>((v >> 8) & 0xFF));
}

inline void put_u32le(std::vector<uint8_t>& out, uint32_t v) {
    out.push_back(static_cast<uint8_t>(v & 0xFF));
    out.push_back(static_cast<uint8_t>((v >> 8) & 0xFF));
    out.push_back(static_cast<uint8_t>((v >> 16) & 0xFF));
    out.push_back(static_cast<uint8_t>((v >> 24) & 0xFF));
}

inline void put_u16le_at(std::vector<uint8_t>& out, size_t off, uint16_t v) {
    out[off] = static_cast<uint8_t>(v & 0xFF);
    out[off + 1] = static_cast<uint8_t>((v >> 8) & 0xFF);
}

inline void put_u32le_at(std::vector<uint8_t>& out, size_t off, uint32_t v) {
    for (int i = 0; i < 4; ++i) out[off + i] = static_cast<uint8_t>((v >> (8 * i)) & 0xFF);
}

template <typename Fn>
inline void parallel_for(int n, Fn&& fn) {
    if (n <= 0) return;
    // ATLAS modification (2026-11-10): one thread. At upstream commit 553a718a
    // frame 1 sets the expected size while other threads already compare
    // against it (still 0x0): "frame 3 is WxH, expected 0x0". See ATLAS.md.
    unsigned hw = 1;
    if (hw == 0) hw = 4;
    int workers = static_cast<int>(std::min<unsigned>(hw, static_cast<unsigned>(n)));
    if (workers <= 1) {
        for (int i = 0; i < n; ++i) fn(i);
        return;
    }
    std::atomic<int> next{0};
    std::vector<std::thread> pool;
    for (int t = 0; t < workers; ++t) {
        pool.emplace_back([&]() {
            for (;;) {
                int i = next.fetch_add(1);
                if (i >= n) break;
                fn(i);
            }
        });
    }
    for (auto& th : pool) th.join();
}

inline bool write_file(const std::string& path, const std::vector<uint8_t>& data) {
    FILE* f = std::fopen(path.c_str(), "wb");
    if (!f) return false;
    size_t written = std::fwrite(data.data(), 1, data.size(), f);
    std::fclose(f);
    return written == data.size();
}

} // namespace detail
} // namespace qmgc
