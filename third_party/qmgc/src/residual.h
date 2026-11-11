/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once

#include <array>
#include <cstdint>
#include <optional>
#include <utility>

namespace qmgc {
namespace detail {

struct ResidualChoice {
    bool found = false;
    uint8_t nb_bits = 0;
    uint16_t idx = 0;
};

void init_resid_lut();
// legacy == true selects the qversion 0x0b residual table, false the qversion 0x0f one.
std::optional<std::pair<uint8_t, uint16_t>> best_residual(uint16_t pred, uint16_t actual, bool legacy);

} // namespace detail
} // namespace qmgc
