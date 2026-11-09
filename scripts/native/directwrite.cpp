// DirectWrite shapes; Direct2D/WIC renders. The fonts stay in a private collection.
#define NOMINMAX
#include <windows.h>
#include <dwrite_3.h>
#include <d2d1.h>
#include <wincodec.h>
#include <wrl/client.h>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include <iostream>
#include <stdexcept>
using Microsoft::WRL::ComPtr;
namespace fs = std::filesystem;
static void ok(HRESULT hr) { if (FAILED(hr)) throw std::runtime_error("HRESULT " + std::to_string(static_cast<unsigned>(hr))); }
static std::wstring wide(std::string const& s) {
    int n = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, s.data(), static_cast<int>(s.size()), nullptr, 0);
    if (!n) throw std::runtime_error("invalid UTF-8");
    std::wstring w(n, L'\0');
    MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, s.data(), static_cast<int>(s.size()), w.data(), n);
    return w;
}
static std::string fontFile(IDWriteFontFace* face) {
    UINT32 n = 1; ComPtr<IDWriteFontFile> file;
    ok(face->GetFiles(&n, file.GetAddressOf()));
    ComPtr<IDWriteFontFileLoader> loader; ok(file->GetLoader(&loader));
    ComPtr<IDWriteLocalFontFileLoader> local; ok(loader.As(&local));
    void const* key = nullptr; UINT32 size = 0, length = 0;
    ok(file->GetReferenceKey(&key, &size)); ok(local->GetFilePathLengthFromKey(key, size, &length));
    std::wstring path(length + 1, L'\0'); ok(local->GetFilePathFromKey(key, size, path.data(), length + 1));
    path.resize(length); return fs::path(path).filename().string();
}
// Collect both old and vertical-aware callbacks; Direct2D separately draws the same layout.
class Recorder final : public IDWriteTextRenderer1 {
    LONG refs = 1;
    std::ostream& out;
    bool first = true;
public:
    explicit Recorder(std::ostream& stream) : out(stream) {}
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** object) override {
        if (!object) return E_POINTER;
        *object = nullptr;
        if (iid == __uuidof(IUnknown) || iid == __uuidof(IDWritePixelSnapping) ||
            iid == __uuidof(IDWriteTextRenderer) || iid == __uuidof(IDWriteTextRenderer1)) {
            *object = static_cast<IDWriteTextRenderer1*>(this); AddRef(); return S_OK;
        }
        return E_NOINTERFACE;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return InterlockedIncrement(&refs); }
    ULONG STDMETHODCALLTYPE Release() override { ULONG n = InterlockedDecrement(&refs); if (!n) delete this; return n; }
    HRESULT STDMETHODCALLTYPE IsPixelSnappingDisabled(void*, BOOL* disabled) override { *disabled = TRUE; return S_OK; }
    HRESULT STDMETHODCALLTYPE GetCurrentTransform(void*, DWRITE_MATRIX* m) override { *m = {1, 0, 0, 1, 0, 0}; return S_OK; }
    HRESULT STDMETHODCALLTYPE GetPixelsPerDip(void*, FLOAT* value) override { *value = 1; return S_OK; }
    HRESULT record(FLOAT x, FLOAT y, DWRITE_GLYPH_ORIENTATION_ANGLE angle, DWRITE_GLYPH_RUN const* run) {
        try {
            if (!first) out << ','; first = false;
            out << "{\"font\":\"" << fontFile(run->fontFace) << "\",\"baseline\":[" << x << ',' << y
                << "],\"orientation\":" << angle << ",\"sideways\":" << (run->isSideways ? "true" : "false") << ",\"glyphs\":[";
            for (UINT32 i = 0; i < run->glyphCount; ++i) { if (i) out << ','; out << run->glyphIndices[i]; }
            out << "],\"advances\":[";
            for (UINT32 i = 0; i < run->glyphCount; ++i) { if (i) out << ','; out << run->glyphAdvances[i]; }
            out << "],\"offsets\":[";
            for (UINT32 i = 0; i < run->glyphCount; ++i) {
                if (i) out << ',';
                out << '[' << run->glyphOffsets[i].advanceOffset << ',' << run->glyphOffsets[i].ascenderOffset << ']';
            }
            out << "]}"; return S_OK;
        } catch (...) { return E_FAIL; }
    }
    HRESULT STDMETHODCALLTYPE DrawGlyphRun(void*, FLOAT x, FLOAT y, DWRITE_MEASURING_MODE,
        DWRITE_GLYPH_RUN const* r, DWRITE_GLYPH_RUN_DESCRIPTION const*, IUnknown*) override {
        return record(x, y, DWRITE_GLYPH_ORIENTATION_ANGLE_0_DEGREES, r);
    }
    HRESULT STDMETHODCALLTYPE DrawGlyphRun(void*, FLOAT x, FLOAT y, DWRITE_GLYPH_ORIENTATION_ANGLE a,
        DWRITE_MEASURING_MODE, DWRITE_GLYPH_RUN const* r, DWRITE_GLYPH_RUN_DESCRIPTION const*, IUnknown*) override {
        return record(x, y, a, r);
    }
    HRESULT STDMETHODCALLTYPE DrawUnderline(void*, FLOAT, FLOAT, DWRITE_UNDERLINE const*, IUnknown*) override { return E_NOTIMPL; }
    HRESULT STDMETHODCALLTYPE DrawUnderline(void*, FLOAT, FLOAT, DWRITE_GLYPH_ORIENTATION_ANGLE,
        DWRITE_UNDERLINE const*, IUnknown*) override { return E_NOTIMPL; }
    HRESULT STDMETHODCALLTYPE DrawStrikethrough(void*, FLOAT, FLOAT, DWRITE_STRIKETHROUGH const*, IUnknown*) override { return E_NOTIMPL; }
    HRESULT STDMETHODCALLTYPE DrawStrikethrough(void*, FLOAT, FLOAT, DWRITE_GLYPH_ORIENTATION_ANGLE,
        DWRITE_STRIKETHROUGH const*, IUnknown*) override { return E_NOTIMPL; }
    HRESULT STDMETHODCALLTYPE DrawInlineObject(void*, FLOAT, FLOAT, IDWriteInlineObject*, BOOL, BOOL, IUnknown*) override { return E_NOTIMPL; }
    HRESULT STDMETHODCALLTYPE DrawInlineObject(void*, FLOAT, FLOAT, DWRITE_GLYPH_ORIENTATION_ANGLE,
        IDWriteInlineObject*, BOOL, BOOL, IUnknown*) override { return E_NOTIMPL; }
};
static void run(wchar_t** argv) {
    ok(CoInitializeEx(nullptr, COINIT_MULTITHREADED));
    ComPtr<IDWriteFactory5> factory;
    ok(DWriteCreateFactory(DWRITE_FACTORY_TYPE_ISOLATED, __uuidof(IDWriteFactory5),
                          reinterpret_cast<IUnknown**>(factory.GetAddressOf())));
    ComPtr<IDWriteFontFile> file; ok(factory->CreateFontFileReference(argv[1], nullptr, &file));
    ComPtr<IDWriteFontSetBuilder1> builder; ok(factory->CreateFontSetBuilder(&builder));
    ok(builder->AddFontFile(file.Get()));
    ComPtr<IDWriteFontSet> fontSet; ok(builder->CreateFontSet(&fontSet));
    ComPtr<IDWriteFontCollection1> collection; ok(factory->CreateFontCollectionFromFontSet(fontSet.Get(), &collection));
    ComPtr<ID2D1Factory> d2d; ok(D2D1CreateFactory(D2D1_FACTORY_TYPE_SINGLE_THREADED, d2d.GetAddressOf()));
    ComPtr<IWICImagingFactory> wic; ok(CoCreateInstance(CLSID_WICImagingFactory, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&wic)));
    std::ifstream cases{fs::path(argv[2])};
    if (!cases) throw std::runtime_error("cannot open cases.tsv");
    std::string line;
    while (std::getline(cases, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        std::istringstream row(line); std::vector<std::string> fields; std::string field;
        while (std::getline(row, field, '\t')) fields.push_back(field);
        if (fields.size() != 6) throw std::runtime_error("bad cases.tsv row");
        const bool vertical = fields[2] == "1";
        auto text = wide(fields[5]), locale = wide(fields[1]);
        ComPtr<IDWriteTextFormat> format;
        ok(factory->CreateTextFormat(argv[4], collection.Get(), std::wstring(argv[5]) == L"Bold" ? DWRITE_FONT_WEIGHT_BOLD : DWRITE_FONT_WEIGHT_NORMAL,
            DWRITE_FONT_STYLE_NORMAL, DWRITE_FONT_STRETCH_NORMAL, 24, locale.c_str(), &format));
        ComPtr<IDWriteTextLayout> layout;
        ok(factory->CreateTextLayout(text.data(), static_cast<UINT32>(text.size()), format.Get(), 1520, 820, &layout));
        ComPtr<IDWriteTextLayout2> layout2; ok(layout.As(&layout2));
        DWRITE_TEXT_RANGE all{0, static_cast<UINT32>(text.size())};
        // DirectWrite needs an explicit pair-kerning request; preserve the off control.
        ok(layout2->SetPairKerning(fields[3] != "0", all));
        if (fields[4] != "-1") {
            ComPtr<IDWriteTypography> typography; ok(factory->CreateTypography(&typography));
            ok(typography->AddFontFeature({DWRITE_FONT_FEATURE_TAG_LOCALIZED_FORMS, static_cast<UINT32>(std::stoi(fields[4]))}));
            ok(layout->SetTypography(typography.Get(), all));
        }
        if (vertical) {
            ok(layout->SetReadingDirection(DWRITE_READING_DIRECTION_TOP_TO_BOTTOM));
            ok(layout->SetFlowDirection(DWRITE_FLOW_DIRECTION_RIGHT_TO_LEFT));
            ok(layout2->SetVerticalGlyphOrientation(DWRITE_VERTICAL_GLYPH_ORIENTATION_DEFAULT));
        }
        DWRITE_TEXT_METRICS metrics; ok(layout->GetMetrics(&metrics));
        if (metrics.width > 1520 || metrics.height > 820) throw std::runtime_error("clipped layout");
        auto prefix = fs::path(argv[3]) / fields[0];
        std::ofstream json(prefix.string() + ".json");
        json << "{\"engine\":\"directwrite\",\"sample\":\"" << fields[0] << "\",\"emSize\":24,\"vertical\":"
             << (vertical ? "true" : "false") << ",\"extent\":[" << metrics.width << ',' << metrics.height << "],\"runs\":[";
        ComPtr<Recorder> recorder; recorder.Attach(new Recorder(json));
        ok(layout->Draw(nullptr, recorder.Get(), 40, 40)); json << "]}\n"; json.close();
        ComPtr<IWICBitmap> bitmap; ok(wic->CreateBitmap(1600, 900, GUID_WICPixelFormat32bppPBGRA, WICBitmapCacheOnLoad, &bitmap));
        ComPtr<ID2D1RenderTarget> target;
        ok(d2d->CreateWicBitmapRenderTarget(bitmap.Get(), D2D1::RenderTargetProperties(), &target));
        ComPtr<ID2D1SolidColorBrush> brush; ok(target->CreateSolidColorBrush(D2D1::ColorF(D2D1::ColorF::Black), &brush));
        target->BeginDraw(); target->Clear(D2D1::ColorF(D2D1::ColorF::White));
        target->DrawTextLayout(D2D1::Point2F(40, 40), layout.Get(), brush.Get()); ok(target->EndDraw());
        ComPtr<IWICStream> stream; ok(wic->CreateStream(&stream));
        ok(stream->InitializeFromFilename((prefix.wstring() + L".png").c_str(), GENERIC_WRITE));
        ComPtr<IWICBitmapEncoder> encoder; ok(wic->CreateEncoder(GUID_ContainerFormatPng, nullptr, &encoder));
        ok(encoder->Initialize(stream.Get(), WICBitmapEncoderNoCache));
        ComPtr<IWICBitmapFrameEncode> frame; ok(encoder->CreateNewFrame(&frame, nullptr));
        ok(frame->Initialize(nullptr)); ok(frame->SetSize(1600, 900));
        WICPixelFormatGUID pixel = GUID_WICPixelFormat32bppBGRA; ok(frame->SetPixelFormat(&pixel));
        ok(frame->WriteSource(bitmap.Get(), nullptr)); ok(frame->Commit()); ok(encoder->Commit());
    }
}
int wmain(int argc, wchar_t** argv) {
    if (argc != 6) { std::cerr << "font, cases, output, family, weight required\n"; return 2; }
    try { run(argv); CoUninitialize(); return 0; }
    catch (std::exception const& e) { std::cerr << "DirectWrite proof failed: " << e.what() << '\n'; return 1; }
}
