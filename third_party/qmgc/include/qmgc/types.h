/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef QMGC_TYPES_H
#define QMGC_TYPES_H

#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

namespace qmgc {

struct Image {
    int width = 0;
    int height = 0;
    std::vector<uint8_t> rgb;
};

struct QmgError : std::runtime_error {
    explicit QmgError(const std::string& msg) : std::runtime_error(msg) {}
};

} // namespace qmgc

#endif
