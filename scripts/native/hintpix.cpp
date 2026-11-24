// DirectWrite renders small hinted glyphs (9-20 px) as pixels. No Direct2D: the pixels come from
// IDWriteFactory::CreateGlyphRunAnalysis + IDWriteGlyphRunAnalysis::CreateAlphaTexture, so the hinting of the
// font (TrueType instructions) is what shows. directwrite.cpp draws 24 px with pixel snapping disabled and cannot
// show the hinting.
#define NOMINMAX
#include <windows.h>
#include <dwrite.h>
#include <wrl/client.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
using Microsoft::WRL::ComPtr;
namespace fs = std::filesystem;
static void ok(HRESULT hr) { if (FAILED(hr)) throw std::runtime_error("HRESULT " + std::to_string(static_cast<unsigned>(hr))); }
struct Mode { char const* name; DWRITE_RENDERING_MODE rendering; DWRITE_MEASURING_MODE measuring; };
// DirectWrite natural (y-direction hinting only), GDI natural and GDI classic (full hinting, integer advances).
static Mode const modes[] = {
    {"natural-symmetric", DWRITE_RENDERING_MODE_NATURAL_SYMMETRIC, DWRITE_MEASURING_MODE_NATURAL},
    {"gdi-natural", DWRITE_RENDERING_MODE_GDI_NATURAL, DWRITE_MEASURING_MODE_GDI_NATURAL},
    {"gdi-classic", DWRITE_RENDERING_MODE_GDI_CLASSIC, DWRITE_MEASURING_MODE_GDI_CLASSIC},
};
// Slashes and diagonals that the hinting thinned: 2 O-slash o-slash 4 Z S A V 8 N M W z nu heart white-shogi-piece
static UINT32 const codes[] = {0x32, 0xD8, 0xF8, 0x34, 0x5A, 0x53, 0x41, 0x56, 0x38, 0x4E, 0x4D, 0x57, 0x7A, 0x3BD, 0x2661, 0x2616};
static void run(wchar_t** argv) {
    ok(CoInitializeEx(nullptr, COINIT_MULTITHREADED));
    ComPtr<IDWriteFactory> factory;
    ok(DWriteCreateFactory(DWRITE_FACTORY_TYPE_ISOLATED, __uuidof(IDWriteFactory), reinterpret_cast<IUnknown**>(factory.GetAddressOf())));
    ComPtr<IDWriteFontFile> file; ok(factory->CreateFontFileReference(argv[1], nullptr, &file));
    IDWriteFontFile* files[] = {file.Get()};
    ComPtr<IDWriteFontFace> face;
    ok(factory->CreateFontFace(DWRITE_FONT_FACE_TYPE_TRUETYPE, 1, files, 0, DWRITE_FONT_SIMULATIONS_NONE, &face));
    std::ofstream out{fs::path(argv[2])};
    if (!out) throw std::runtime_error("cannot open the output");
    out << "{\"font\":\"" << fs::path(argv[1]).filename().string() << "\",\"textureType\":\"cleartype-3x1\",\"glyphs\":[";
    bool first = true;
    for (Mode const& mode : modes) {
        for (UINT32 code : codes) {
            UINT16 glyph = 0;
            ok(face->GetGlyphIndices(&code, 1, &glyph));
            if (!glyph) throw std::runtime_error("a glyph is missing");
            for (int ppem = 9; ppem <= 20; ++ppem) {
                DWRITE_GLYPH_RUN run{};
                run.fontFace = face.Get(); run.fontEmSize = static_cast<FLOAT>(ppem); run.glyphCount = 1; run.glyphIndices = &glyph;
                ComPtr<IDWriteGlyphRunAnalysis> analysis;
                ok(factory->CreateGlyphRunAnalysis(&run, 1.0f, nullptr, mode.rendering, mode.measuring, 0.0f, 0.0f, &analysis));
                RECT bounds{};
                ok(analysis->GetAlphaTextureBounds(DWRITE_TEXTURE_CLEARTYPE_3x1, &bounds));
                long const width = bounds.right - bounds.left, height = bounds.bottom - bounds.top;
                std::vector<BYTE> alpha;
                if (width > 0 && height > 0) {
                    alpha.resize(static_cast<size_t>(width) * height * 3);
                    ok(analysis->CreateAlphaTexture(DWRITE_TEXTURE_CLEARTYPE_3x1, &bounds, alpha.data(), static_cast<UINT32>(alpha.size())));
                }
                if (!first) out << ','; first = false;
                out << "{\"mode\":\"" << mode.name << "\",\"code\":" << code << ",\"ppem\":" << ppem
                    << ",\"bounds\":[" << bounds.left << ',' << bounds.top << ',' << bounds.right << ',' << bounds.bottom << "],\"alpha\":[";
                for (size_t i = 0; i < alpha.size(); ++i) { if (i) out << ','; out << static_cast<int>(alpha[i]); }
                out << "]}";
            }
        }
    }
    out << "]}\n";
    if (!out) throw std::runtime_error("cannot write the output");
}
int wmain(int argc, wchar_t** argv) {
    if (argc != 3) { std::cerr << "font and output required\n"; return 2; }
    try { run(argv); CoUninitialize(); return 0; }
    catch (std::exception const& e) { std::cerr << "DirectWrite hinted pixels failed: " << e.what() << '\n'; return 1; }
}
