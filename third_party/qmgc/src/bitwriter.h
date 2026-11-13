/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once

#include <cstdint>
#include <vector>

namespace qmgc {
namespace detail {

class BitWriter {
public:
    void write(uint32_t val, int n) {
        for (int i = n - 1; i >= 0; --i) {
            int bit = (val >> i) & 1;
            if (bitpos_ == 0) buf_.push_back(0);
            if (bit) buf_.back() |= static_cast<uint8_t>(1u << (7 - bitpos_));
            bitpos_ = (bitpos_ + 1) & 7;
        }
    }

    const std::vector<uint8_t>& bytes() const { return buf_; }

private:
    std::vector<uint8_t> buf_;
    int bitpos_ = 0;
};

} // namespace detail
} // namespace qmgc
