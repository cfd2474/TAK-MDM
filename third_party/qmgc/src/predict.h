/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once

#include "tables.h"

#include <algorithm>
#include <cstdint>
#include <vector>

namespace qmgc {
namespace detail {

// Samsung libQmageDecoder bounds-checks predictors as a linear framebuffer index:
//   if ((int32_t)(y*w + x + dy*w + dx) < 0) → "error pixel position out of image range" → -9.
// Copy and delta both load the predictor; only escape-code 7 (literal) skips the check.
inline bool pred_linear_oob(int w, int x, int y) {
    return static_cast<int64_t>(y) * w + x < 0;
}

inline uint16_t gp(const std::vector<uint16_t>& dst, int w, int h, int x, int y) {
    int64_t lin = static_cast<int64_t>(y) * w + x;
    int64_t max = static_cast<int64_t>(w) * h;
    if (lin < 0 || lin >= max) return 0;
    return dst[static_cast<size_t>(lin)];
}

inline int choose_mode(const std::vector<uint16_t>& dst, const std::vector<uint16_t>& pixels,
                       int w, int h, int x, int y) {
    int bw = std::min(4, w - x);
    int bh = std::min(4, h - y);
    if (x > 0) {
        bool can_edge = true;
        for (int j = 0; j < bh && can_edge; ++j) {
            uint16_t left = pixels[static_cast<size_t>(y + j) * w + (x - 1)];
            for (int i = 0; i < bw; ++i) {
                if (pixels[static_cast<size_t>(y + j) * w + (x + i)] != left) {
                    can_edge = false;
                    break;
                }
            }
        }
        if (can_edge) return 3;
    }
    int best_mode = 0, best_copies = -1;
    for (int mode = 0; mode < 3; ++mode) {
        uint16_t block[4][4];
        bool set[4][4] = {{false}};
        int dx = DIRS[mode].dx, dy = DIRS[mode].dy;
        int copies = 0;
        for (int j = 0; j < bh; ++j) {
            for (int i = 0; i < bw; ++i) {
                uint16_t actual = pixels[static_cast<size_t>(y + j) * w + (x + i)];
                int nx = x + i + dx, ny = y + j + dy;
                uint16_t pred;
                if (nx >= x && nx < x + 4 && ny >= y && ny < y + 4 && set[ny - y][nx - x]) {
                    pred = block[ny - y][nx - x];
                } else if (pred_linear_oob(w, nx, ny)) {
                    block[j][i] = actual;
                    set[j][i] = true;
                    continue;
                } else {
                    pred = gp(dst, w, h, nx, ny);
                }
                if (pred == actual) ++copies;
                block[j][i] = actual;
                set[j][i] = true;
            }
        }
        if (copies > best_copies) {
            best_copies = copies;
            best_mode = mode;
        }
    }
    return best_mode;
}

} // namespace detail
} // namespace qmgc
