/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "residual.h"
#include "tables.h"

#include <array>

namespace qmgc {
namespace detail {

static std::array<ResidualChoice, 65536> RESID_LUT[2];
static bool resid_lut_ready = false;

void init_resid_lut() {
    if (resid_lut_ready) return;
    for (int t = 0; t < 2; ++t) {
        const uint16_t* table = t ? QMAGE_ORI_DELTA_V11 : QMAGE_ORI_DELTA;
        for (int nb_bits = 0; nb_bits < 7; ++nb_bits) {
            int base = (2 << nb_bits) - 2;
            int count = 1 << (nb_bits + 1);
            for (int idx = 0; idx < count; ++idx) {
                int ti = idx + base;
                if (ti >= 256) continue;
                uint16_t v = table[ti];
                if (!RESID_LUT[t][v].found) {
                    RESID_LUT[t][v] = {true, static_cast<uint8_t>(nb_bits), static_cast<uint16_t>(idx)};
                }
            }
        }
    }
    resid_lut_ready = true;
}

std::optional<std::pair<uint8_t, uint16_t>> best_residual(uint16_t pred, uint16_t actual, bool legacy) {
    uint16_t diff = static_cast<uint16_t>(actual - pred);
    const ResidualChoice& c = RESID_LUT[legacy ? 1 : 0][diff];
    if (!c.found) return std::nullopt;
    return std::make_pair(c.nb_bits, c.idx);
}

} // namespace detail
} // namespace qmgc
