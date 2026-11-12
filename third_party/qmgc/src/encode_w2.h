/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once

#include "qmgc/types.h"

#include <cstdint>
#include <vector>

namespace qmgc {
namespace detail {

std::vector<uint8_t> encode_still_w2(const Image& img);

} // namespace detail
} // namespace qmgc
