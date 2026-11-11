/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "encode_a9ll.h"

#include "bitwriter.h"
#include "predict.h"
#include "qmgc/types.h"
#include "residual.h"
#include "tables.h"
#include "util.h"

#include <cstring>
#include <vector>

namespace qmgc {
namespace detail {

void finalize_anim_block(std::vector<uint8_t>& block, int ordinal, int qversion) {
    while (block.size() % 4 != 0) block.push_back(0);
    if (qversion <= 0x0b) {
        // Legacy layout: offset 12 is a 32-bit byte length for every frame
        // (no /4 scaling for keyframes), so there is no 64 KB frame limit.
        put_u32le_at(block, 12, static_cast<uint32_t>(block.size()));
        return;
    }
    if (ordinal <= 1) {
        uint32_t quarter = static_cast<uint32_t>(block.size() / 4);
        if (quarter > 0xFFFF) throw QmgError("keyframe too large to encode (reclen/4 overflows 16 bits)");
        put_u16le_at(block, 12, static_cast<uint16_t>(quarter));
    } else {
        if (block.size() > 0xFFFF) throw QmgError("delta frame too large to encode (reclen overflows 16 bits)");
        put_u16le_at(block, 12, static_cast<uint16_t>(block.size()));
    }
    block[14] = 0;
    block[15] = 0;
}

static void emit_literal_kf(BitWriter& bw2, std::vector<uint8_t>& gb3, uint16_t actual) {
    bw2.write(7, 3);
    put_u16le(gb3, actual);
}

static void emit_residual_kf(BitWriter& bw1, BitWriter& bw2, std::vector<uint8_t>& gb3,
                             uint16_t pred, uint16_t actual, bool legacy) {
    auto choice = best_residual(pred, actual, legacy);
    if (!choice) {
        emit_literal_kf(bw2, gb3, actual);
    } else {
        bw2.write(choice->first, 3);
        bw1.write(choice->second, choice->first + 1);
    }
}

std::vector<uint8_t> encode_a9ll_keyframe(int width, int height, const std::vector<uint16_t>& pixels,
                                         int total, int ordinal, int delay, int qversion) {
    const bool legacy = qversion <= 0x0b;
    BitWriter bw1, bw2;
    std::vector<uint8_t> gb3;
    std::vector<uint16_t> dst(static_cast<size_t>(width) * height, 0);
    struct Op {
        bool is_edge;
        bool force_literal;
        uint16_t actual, pred;
    };
    std::vector<Op> ops;
    ops.reserve(16);
    for (int y = 0; y < height; y += 4) {
        for (int x = 0; x < width; x += 4) {
            int mode = choose_mode(dst, pixels, width, height, x, y);
            bw1.write(static_cast<uint32_t>(mode), 2);
            if (mode == 3) {
                int bh = std::min(4, height - y), bw = std::min(4, width - x);
                for (int j = 0; j < bh; ++j)
                    for (int i = 0; i < bw; ++i)
                        dst[static_cast<size_t>(y + j) * width + x + i] =
                            dst[static_cast<size_t>(y + j) * width + x - 1];
                continue;
            }
            int dx = DIRS[mode].dx, dy = DIRS[mode].dy;
            uint16_t cbp = 0;
            ops.clear();
            int k = 0;
            for (int j = 0; j < 4; ++j) {
                for (int i = 0; i < 4; ++i) {
                    if (x + i >= width || y + j >= height) continue;
                    uint16_t actual = pixels[static_cast<size_t>(y + j) * width + x + i];
                    int px = x + i + dx, py = y + j + dy;
                    if (pred_linear_oob(width, px, py)) {
                        ops.push_back({true, true, actual, actual});
                    } else {
                        uint16_t pred = gp(dst, width, height, px, py);
                        if (pred == actual) {
                            cbp |= static_cast<uint16_t>(1u << k);
                            ops.push_back({false, false, actual, pred});
                        } else {
                            ops.push_back({true, false, actual, pred});
                        }
                    }
                    dst[static_cast<size_t>(y + j) * width + x + i] = actual;
                    ++k;
                }
            }
            put_u16le(gb3, cbp);
            for (auto& op : ops) {
                if (!op.is_edge) continue;
                if (op.force_literal) emit_literal_kf(bw2, gb3, op.actual);
                else emit_residual_kf(bw1, bw2, gb3, op.pred, op.actual, legacy);
            }
        }
    }

    std::vector<uint8_t> bits1 = bw1.bytes();
    std::vector<uint8_t> bits2 = bw2.bytes();
    pad4(bits1);
    pad4(bits2);

    const size_t header_size = 24;
    uint32_t gb1_start = static_cast<uint32_t>(header_size + 8 + bits1.size());
    uint32_t gb3_start = static_cast<uint32_t>(gb1_start + bits2.size());
    std::vector<uint8_t> block;
    block.insert(block.end(), {'Q', 'M', static_cast<uint8_t>(qversion), 0x00, 0x80, 0x00});
    put_u16le(block, static_cast<uint16_t>(width));
    put_u16le(block, static_cast<uint16_t>(height));
    block.push_back(0);
    block.push_back(legacy ? 0x00 : 0x20); // 0x20 = is_opaque (qversion > 0x0b only)
    put_u32le(block, 0);
    put_u16le(block, static_cast<uint16_t>(total));
    put_u16le(block, static_cast<uint16_t>(ordinal));
    put_u16le(block, static_cast<uint16_t>(delay & 0xFFFF));
    block.push_back(0);
    block.push_back(0);
    put_u32le(block, gb1_start);
    put_u32le(block, gb3_start);
    block.insert(block.end(), bits1.begin(), bits1.end());
    block.insert(block.end(), bits2.begin(), bits2.end());
    block.insert(block.end(), gb3.begin(), gb3.end());
    finalize_anim_block(block, ordinal, qversion);
    return block;
}

static void encode_literal_ani(BitWriter& bw1, std::vector<uint8_t>& lit, uint16_t actual) {
    bw1.write(7, 3);
    put_u16le(lit, actual);
}

static void encode_residual_ani(BitWriter& bw1, std::vector<uint8_t>& lit, uint16_t pred, uint16_t actual,
                                bool legacy) {
    auto choice = best_residual(pred, actual, legacy);
    if (!choice) {
        encode_literal_ani(bw1, lit, actual);
    } else {
        bw1.write(choice->first, 3);
        bw1.write(choice->second, choice->first + 1);
    }
}

static void encode_pixel_ani(BitWriter& bw1, std::vector<uint8_t>& lit, std::vector<uint16_t>& dst,
                             int w, int h, int x, int y, uint16_t actual, int dx, int dy, bool legacy) {
    int px = x + dx, py = y + dy;
    if (pred_linear_oob(w, px, py)) {
        bw1.write(0, 1);
        encode_literal_ani(bw1, lit, actual);
        dst[static_cast<size_t>(y) * w + x] = actual;
        return;
    }
    uint16_t pred = gp(dst, w, h, px, py);
    if (pred == actual) {
        bw1.write(1, 1);
        dst[static_cast<size_t>(y) * w + x] = pred;
    } else {
        bw1.write(0, 1);
        encode_residual_ani(bw1, lit, pred, actual, legacy);
        dst[static_cast<size_t>(y) * w + x] = actual;
    }
}

static void encode_block2_ani(BitWriter& bw1, std::vector<uint8_t>& lit, std::vector<uint16_t>& dst,
                              const std::vector<uint16_t>& pixels, int w, int h, int x, int y, bool legacy) {
    int mode = choose_mode(dst, pixels, w, h, x, y);
    bw1.write(static_cast<uint32_t>(mode), 2);
    if (mode == 3) {
        int bh = std::min(4, h - y), bw = std::min(4, w - x);
        for (int j = 0; j < bh; ++j)
            for (int i = 0; i < bw; ++i)
                dst[static_cast<size_t>(y + j) * w + x + i] = dst[static_cast<size_t>(y + j) * w + x - 1];
        return;
    }
    int dx = DIRS[mode].dx, dy = DIRS[mode].dy;
    for (int j = 0; j < 4; ++j) {
        for (int i = 0; i < 4; ++i) {
            if (x + i < w && y + j < h) {
                encode_pixel_ani(bw1, lit, dst, w, h, x + i, y + j,
                                 pixels[static_cast<size_t>(y + j) * w + x + i], dx, dy, legacy);
            }
        }
    }
}

static bool mb_equal(const std::vector<uint16_t>& a, const std::vector<uint16_t>& b, int w, int h,
                     int x, int y, int bw = 16, int bh = 16) {
    int mj = std::min(bh, h - y), mi = std::min(bw, w - x);
    for (int j = 0; j < mj; ++j) {
        const uint16_t* ra = a.data() + static_cast<size_t>(y + j) * w + x;
        const uint16_t* rb = b.data() + static_cast<size_t>(y + j) * w + x;
        if (std::memcmp(ra, rb, static_cast<size_t>(mi) * sizeof(uint16_t)) != 0) return false;
    }
    return true;
}

std::vector<uint8_t> encode_a9ll_ani(int width, int height, const std::vector<uint16_t>& pixels,
                                     const std::vector<uint16_t>& ref, int total, int ordinal, int delay, int qversion) {
    const bool legacy = qversion <= 0x0b;
    BitWriter bw1;
    std::vector<uint8_t> lit;
    std::vector<uint16_t> dst(static_cast<size_t>(width) * height, 0);
    for (int y = 0; y < height; y += 16) {
        for (int x = 0; x < width; x += 16) {
            bool full = (width - x >= 16) && (height - y >= 16);
            if (full) {
                if (mb_equal(pixels, ref, width, height, x, y)) {
                    bw1.write(1, 1);
                    bw1.write(1, 1);
                    for (int j = 0; j < 16; ++j)
                        for (int i = 0; i < 16; ++i)
                            dst[static_cast<size_t>(y + j) * width + x + i] =
                                ref[static_cast<size_t>(y + j) * width + x + i];
                } else {
                    bw1.write(0, 1);
                    for (int j = 0; j < 16; j += 4)
                        for (int i = 0; i < 16; i += 4)
                            encode_block2_ani(bw1, lit, dst, pixels, width, height, x + i, y + j, legacy);
                }
            } else {
                bw1.write(0, 1);
                for (int yy = y; yy < std::min(y + 16, height); yy += 4) {
                    for (int xx = x; xx < std::min(x + 16, width); xx += 4) {
                        if (xx + 4 <= width && yy + 4 <= height) {
                            encode_block2_ani(bw1, lit, dst, pixels, width, height, xx, yy, legacy);
                        } else {
                            for (int j = 0; j < 4; ++j) {
                                for (int i = 0; i < 4; ++i) {
                                    if (xx + i < width && yy + j < height) {
                                        uint16_t val = pixels[static_cast<size_t>(yy + j) * width + xx + i];
                                        put_u16le(lit, val);
                                        dst[static_cast<size_t>(yy + j) * width + xx + i] = val;
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    std::vector<uint8_t> bits = bw1.bytes();
    pad4(bits);

    const size_t header_size = 24;
    uint32_t gb1_start = static_cast<uint32_t>(header_size + 8 + bits.size());
    std::vector<uint8_t> block;
    block.insert(block.end(), {'Q', 'M', static_cast<uint8_t>(qversion), 0x00, 0x80, 0x00});
    put_u16le(block, static_cast<uint16_t>(width));
    put_u16le(block, static_cast<uint16_t>(height));
    block.push_back(0);
    block.push_back(legacy ? 0x00 : 0x20); // 0x20 = is_opaque (qversion > 0x0b only)
    put_u32le(block, 0);
    put_u16le(block, static_cast<uint16_t>(total));
    put_u16le(block, static_cast<uint16_t>(ordinal));
    put_u16le(block, static_cast<uint16_t>(delay & 0xFFFF));
    block.push_back(0);
    block.push_back(0);
    put_u32le(block, gb1_start);
    put_u32le(block, 0);
    block.insert(block.end(), bits.begin(), bits.end());
    block.insert(block.end(), lit.begin(), lit.end());
    finalize_anim_block(block, ordinal, qversion);
    return block;
}

} // namespace detail
} // namespace qmgc
