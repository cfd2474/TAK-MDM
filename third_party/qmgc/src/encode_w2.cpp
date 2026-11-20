/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "encode_w2.h"

#include "qmgc/image.h"
#include "util.h"

#include <algorithm>
#include <unordered_map>
#include <vector>

namespace qmgc {
namespace detail {

static std::vector<uint32_t> to_pairs(const std::vector<uint16_t>& px) {
    std::vector<uint16_t> vals = px;
    if (vals.size() % 2) vals.push_back(vals.back());
    std::vector<uint32_t> out(vals.size() / 2);
    parallel_for(static_cast<int>(out.size()), [&](int i) {
        out[i] = static_cast<uint32_t>(vals[2 * i]) | (static_cast<uint32_t>(vals[2 * i + 1]) << 16);
    });
    return out;
}

static std::vector<uint8_t> encode_w2_depth1(const std::vector<uint32_t>& pairs, size_t max_table = 256) {
    std::unordered_map<uint32_t, uint32_t> counts;
    std::vector<uint32_t> first_seen_order;
    counts.reserve(pairs.size());
    for (uint32_t p : pairs) {
        auto it = counts.find(p);
        if (it == counts.end()) {
            counts.emplace(p, 1);
            first_seen_order.push_back(p);
        } else {
            ++it->second;
        }
    }
    std::vector<uint32_t> table_vals;
    if (counts.size() == 1) {
        table_vals.push_back(pairs[0]);
    } else {
        std::vector<uint32_t> ordered = first_seen_order;
        std::stable_sort(ordered.begin(), ordered.end(), [&](uint32_t a, uint32_t b) {
            return counts[a] > counts[b];
        });
        for (uint32_t v : ordered) {
            if (counts[v] >= 2) {
                table_vals.push_back(v);
                if (table_vals.size() >= max_table) break;
            }
        }
        if (table_vals.empty()) table_vals.push_back(ordered.front());
    }
    std::unordered_map<uint32_t, uint32_t> index;
    index.reserve(table_vals.size());
    for (size_t i = 0; i < table_vals.size(); ++i) index.emplace(table_vals[i], static_cast<uint32_t>(i));
    std::vector<uint8_t> idx_stream, run_stream, lit_stream;
    uint32_t literal_count = 0;
    size_t i = 0, n = pairs.size();
    while (i < n) {
        uint32_t pair = pairs[i];
        auto it = index.find(pair);
        if (it != index.end()) {
            size_t j = i + 1;
            while (j < n && pairs[j] == pair) ++j;
            encode_value(it->second + 1, idx_stream);
            encode_value(static_cast<uint32_t>(j - i - 1), run_stream);
            i = j;
        } else {
            encode_value(0, idx_stream);
            lit_stream.push_back(static_cast<uint8_t>(pair & 0xFF));
            lit_stream.push_back(static_cast<uint8_t>((pair >> 8) & 0xFF));
            lit_stream.push_back(static_cast<uint8_t>((pair >> 16) & 0xFF));
            lit_stream.push_back(static_cast<uint8_t>((pair >> 24) & 0xFF));
            ++literal_count;
            ++i;
        }
    }
    pad4(idx_stream);
    pad4(run_stream);
    std::vector<uint8_t> table;
    for (uint32_t v : table_vals) put_u32le(table, v);
    std::vector<uint8_t> out;
    put_u32le(out, static_cast<uint32_t>(table_vals.size()));
    put_u32le(out, static_cast<uint32_t>(idx_stream.size()));
    put_u32le(out, static_cast<uint32_t>(run_stream.size()));
    put_u32le(out, literal_count);
    out.insert(out.end(), table.begin(), table.end());
    out.insert(out.end(), idx_stream.begin(), idx_stream.end());
    out.insert(out.end(), run_stream.begin(), run_stream.end());
    out.insert(out.end(), lit_stream.begin(), lit_stream.end());
    return out;
}

std::vector<uint8_t> encode_still_w2(const Image& img) {
    std::vector<uint32_t> pairs = to_pairs(pixels_to_565(img));
    std::vector<uint8_t> body = encode_w2_depth1(pairs);
    std::vector<uint8_t> header = {'Q', 'M', 0x0b, 0x00, 0x00, 0x81};
    put_u16le(header, static_cast<uint16_t>(img.width));
    put_u16le(header, static_cast<uint16_t>(img.height));
    header.push_back(0);
    header.push_back(0);
    header.insert(header.end(), body.begin(), body.end());
    return header;
}

} // namespace detail
} // namespace qmgc
