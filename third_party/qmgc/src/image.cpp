/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "qmgc/image.h"

#include "util.h"

#include <png.h>

#include <csetjmp>
#include <cstring>
#include <vector>

#ifdef QMGC_HAVE_JPEG
extern "C" {
#include <jpeglib.h>
#include <jerror.h>
}
#endif

namespace qmgc {

Image scale_image(const Image& src, int tw, int th) {
    if (tw < 1 || th < 1 || tw > 0xFFFF || th > 0xFFFF) {
        throw QmgError("invalid --scale dimensions " + std::to_string(tw) + "x" + std::to_string(th));
    }
    if (tw == src.width && th == src.height) return src;
    Image out;
    out.width = tw;
    out.height = th;
    out.rgb.resize(static_cast<size_t>(tw) * th * 3);
    for (int y = 0; y < th; ++y) {
        int sy = y * src.height / th;
        if (sy >= src.height) sy = src.height - 1;
        const uint8_t* srow = src.rgb.data() + static_cast<size_t>(sy) * src.width * 3;
        uint8_t* drow = out.rgb.data() + static_cast<size_t>(y) * tw * 3;
        for (int x = 0; x < tw; ++x) {
            int sx = x * src.width / tw;
            if (sx >= src.width) sx = src.width - 1;
            drow[x * 3 + 0] = srow[sx * 3 + 0];
            drow[x * 3 + 1] = srow[sx * 3 + 1];
            drow[x * 3 + 2] = srow[sx * 3 + 2];
        }
    }
    return out;
}

static Image load_png(const std::string& path) {
    FILE* fp = std::fopen(path.c_str(), "rb");
    if (!fp) throw QmgError(path + ": cannot open file");
    uint8_t sig[8];
    if (std::fread(sig, 1, 8, fp) != 8 || png_sig_cmp(sig, 0, 8) != 0) {
        std::fclose(fp);
        throw QmgError(path + ": not a valid PNG file");
    }
    png_structp png = png_create_read_struct(PNG_LIBPNG_VER_STRING, nullptr, nullptr, nullptr);
    if (!png) {
        std::fclose(fp);
        throw QmgError(path + ": png_create_read_struct failed");
    }
    png_infop info = png_create_info_struct(png);
    if (!info) {
        png_destroy_read_struct(&png, nullptr, nullptr);
        std::fclose(fp);
        throw QmgError(path + ": png_create_info_struct failed");
    }
    if (setjmp(png_jmpbuf(png))) {
        png_destroy_read_struct(&png, &info, nullptr);
        std::fclose(fp);
        throw QmgError(path + ": PNG decode error");
    }
    png_init_io(png, fp);
    png_set_sig_bytes(png, 8);
    png_read_info(png, info);
    png_uint_32 w, h;
    int bit_depth, color_type;
    png_get_IHDR(png, info, &w, &h, &bit_depth, &color_type, nullptr, nullptr, nullptr);
    if (color_type == PNG_COLOR_TYPE_PALETTE) png_set_palette_to_rgb(png);
    if (color_type == PNG_COLOR_TYPE_GRAY && bit_depth < 8) png_set_expand_gray_1_2_4_to_8(png);
    if (png_get_valid(png, info, PNG_INFO_tRNS)) png_set_tRNS_to_alpha(png);
    if (bit_depth == 16) png_set_strip_16(png);
    if (color_type == PNG_COLOR_TYPE_GRAY || color_type == PNG_COLOR_TYPE_GRAY_ALPHA) png_set_gray_to_rgb(png);
    png_set_strip_alpha(png);
    png_set_interlace_handling(png);
    png_read_update_info(png, info);
    if (w < 1 || h < 1 || w > 0xFFFF || h > 0xFFFF) {
        png_destroy_read_struct(&png, &info, nullptr);
        std::fclose(fp);
        throw QmgError(path + ": unsupported dimensions " + std::to_string(w) + "x" + std::to_string(h));
    }
    size_t rowbytes = png_get_rowbytes(png, info);
    Image img;
    img.width = static_cast<int>(w);
    img.height = static_cast<int>(h);
    img.rgb.resize(static_cast<size_t>(w) * h * 3);
    std::vector<png_bytep> rows(h);
    std::vector<uint8_t> buf(rowbytes * h);
    for (png_uint_32 y = 0; y < h; ++y) rows[y] = buf.data() + y * rowbytes;
    png_read_image(png, rows.data());
    png_read_end(png, nullptr);
    png_destroy_read_struct(&png, &info, nullptr);
    std::fclose(fp);
    for (png_uint_32 y = 0; y < h; ++y) {
        std::memcpy(img.rgb.data() + static_cast<size_t>(y) * w * 3, rows[y], static_cast<size_t>(w) * 3);
    }
    return img;
}

#ifdef QMGC_HAVE_JPEG
struct JpegErrorMgr {
    struct jpeg_error_mgr pub;
    jmp_buf setjmp_buffer;
};

static void jpeg_error_exit(j_common_ptr cinfo) {
    JpegErrorMgr* err = reinterpret_cast<JpegErrorMgr*>(cinfo->err);
    std::longjmp(err->setjmp_buffer, 1);
}

static Image load_jpeg(const std::string& path) {
    FILE* fp = std::fopen(path.c_str(), "rb");
    if (!fp) throw QmgError(path + ": cannot open file");
    struct jpeg_decompress_struct cinfo;
    JpegErrorMgr jerr;
    cinfo.err = jpeg_std_error(&jerr.pub);
    jerr.pub.error_exit = jpeg_error_exit;
    if (setjmp(jerr.setjmp_buffer)) {
        char msg[JMSG_LENGTH_MAX];
        (*cinfo.err->format_message)(reinterpret_cast<j_common_ptr>(&cinfo), msg);
        jpeg_destroy_decompress(&cinfo);
        std::fclose(fp);
        throw QmgError(path + ": JPEG decode error (" + msg + ")");
    }
    jpeg_create_decompress(&cinfo);
    jpeg_stdio_src(&cinfo, fp);
    jpeg_read_header(&cinfo, TRUE);
    cinfo.out_color_space = JCS_RGB;
    jpeg_start_decompress(&cinfo);
    int width = static_cast<int>(cinfo.output_width);
    int height = static_cast<int>(cinfo.output_height);
    if (width < 1 || height < 1 || width > 0xFFFF || height > 0xFFFF) {
        jpeg_destroy_decompress(&cinfo);
        std::fclose(fp);
        throw QmgError(path + ": unsupported dimensions " + std::to_string(width) + "x" + std::to_string(height));
    }
    int row_stride = width * cinfo.output_components;
    Image img;
    img.width = width;
    img.height = height;
    img.rgb.resize(static_cast<size_t>(width) * height * 3);
    std::vector<uint8_t> rowbuf(row_stride);
    uint8_t* rowptr[1];
    while (cinfo.output_scanline < cinfo.output_height) {
        rowptr[0] = rowbuf.data();
        jpeg_read_scanlines(&cinfo, rowptr, 1);
        std::memcpy(img.rgb.data() + static_cast<size_t>(cinfo.output_scanline - 1) * width * 3, rowbuf.data(),
                    static_cast<size_t>(row_stride));
    }
    jpeg_finish_decompress(&cinfo);
    jpeg_destroy_decompress(&cinfo);
    std::fclose(fp);
    return img;
}
#endif

Image load_image(const std::string& path) {
    FILE* fp = std::fopen(path.c_str(), "rb");
    if (!fp) throw QmgError(path + ": cannot open file");
    uint8_t magic[8] = {0};
    size_t n = std::fread(magic, 1, 8, fp);
    std::fclose(fp);
    (void)n;
    static const uint8_t PNG_SIG[8] = {0x89, 'P', 'N', 'G', 0x0d, 0x0a, 0x1a, 0x0a};
    if (std::memcmp(magic, PNG_SIG, 8) == 0) return load_png(path);
#ifdef QMGC_HAVE_JPEG
    if (magic[0] == 0xFF && magic[1] == 0xD8) return load_jpeg(path);
#endif
    throw QmgError(path + ": not a recognized PNG or JPEG file");
}

std::vector<uint16_t> pixels_to_565(const Image& img) {
    std::vector<uint16_t> out(static_cast<size_t>(img.width) * img.height);
    detail::parallel_for(img.height, [&](int y) {
        const uint8_t* row = img.rgb.data() + static_cast<size_t>(y) * img.width * 3;
        uint16_t* orow = out.data() + static_cast<size_t>(y) * img.width;
        for (int x = 0; x < img.width; ++x) {
            orow[x] = detail::rgb565(row[x * 3 + 0], row[x * 3 + 1], row[x * 3 + 2]);
        }
    });
    return out;
}

} // namespace qmgc
