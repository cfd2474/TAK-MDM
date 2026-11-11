/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef QMGC_IMAGE_H
#define QMGC_IMAGE_H

#include "qmgc/types.h"
#include <string>

namespace qmgc {

Image load_image(const std::string& path);
Image scale_image(const Image& src, int tw, int th);
std::vector<uint16_t> pixels_to_565(const Image& img);

} // namespace qmgc

#endif
