"""FreeType (libfreetype) で、ヒンティングを動かして字を描く。check.py が使う。

FreeType の Python のパッケージは使わず、ctypes で libfreetype を直接呼ぶ (Debian / Ubuntu の
libfreetype6。依存を増やさない)。構造体は、使う欄までだけを書く。
"""

import ctypes
import ctypes.util
from ctypes import POINTER, Structure, byref, c_char_p, c_int, c_long, c_short, c_ubyte, c_uint, c_ushort, c_void_p


class _Generic(Structure):
    _fields_ = [("data", c_void_p), ("finalizer", c_void_p)]


class _BBox(Structure):
    _fields_ = [("xMin", c_long), ("yMin", c_long), ("xMax", c_long), ("yMax", c_long)]


class _Vector(Structure):
    _fields_ = [("x", c_long), ("y", c_long)]


class _Metrics(Structure):
    _fields_ = [(name, c_long) for name in ("width", "height", "horiBearingX", "horiBearingY", "horiAdvance",
                                             "vertBearingX", "vertBearingY", "vertAdvance")]


class _Bitmap(Structure):
    _fields_ = [("rows", c_uint), ("width", c_uint), ("pitch", c_int), ("buffer", POINTER(c_ubyte)),
                ("num_grays", c_ushort), ("pixel_mode", c_ubyte), ("palette_mode", c_ubyte), ("palette", c_void_p)]


class _Outline(Structure):
    _fields_ = [("n_contours", c_short), ("n_points", c_short), ("points", POINTER(_Vector)),
                ("tags", POINTER(c_ubyte)), ("contours", POINTER(c_short)), ("flags", c_int)]


class _GlyphSlot(Structure):
    _fields_ = [("library", c_void_p), ("face", c_void_p), ("next", c_void_p), ("glyph_index", c_uint),
                ("generic", _Generic), ("metrics", _Metrics), ("linearHoriAdvance", c_long),
                ("linearVertAdvance", c_long), ("advance", _Vector), ("format", c_uint), ("bitmap", _Bitmap),
                ("bitmap_left", c_int), ("bitmap_top", c_int), ("outline", _Outline)]


class _Face(Structure):
    _fields_ = [("num_faces", c_long), ("face_index", c_long), ("face_flags", c_long), ("style_flags", c_long),
                ("num_glyphs", c_long), ("family_name", c_char_p), ("style_name", c_char_p),
                ("num_fixed_sizes", c_int), ("available_sizes", c_void_p), ("num_charmaps", c_int),
                ("charmaps", c_void_p), ("generic", _Generic), ("bbox", _BBox), ("units_per_EM", c_ushort),
                ("ascender", c_short), ("descender", c_short), ("height", c_short), ("max_advance_width", c_short),
                ("max_advance_height", c_short), ("underline_position", c_short), ("underline_thickness", c_short),
                ("glyph", POINTER(_GlyphSlot))]


_LOAD_RENDER = 1 << 2
NO_HINTING = 1 << 1  # ヒンティングを動かさずに描く (Renderer の flags に足す)
_LOAD_TARGET_MONO = 2 << 16

# (名前, TrueType の命令の解釈の版, 読み込みの指定)。v35 は昔の Windows に近く、ヒンティングが縦にも
# 横にも効く。v40 は今の FreeType の既定で、主に縦に効く
MODES = [("v35 gray", 35, 0), ("v35 mono", 35, _LOAD_TARGET_MONO), ("v40 gray", 40, 0)]


def _load_library():
    name = ctypes.util.find_library("freetype") or "libfreetype.so.6"
    try:
        return ctypes.CDLL(name)
    except OSError as error:
        raise SystemExit(f"libfreetype is needed to check the hinting (Debian / Ubuntu: libfreetype6): {error}")


_ft = _load_library()


class Renderer:
    """1 つのフォントを、1 つの描き方で描く"""

    def __init__(self, path: str, interpreter: int, flags: int):
        self.library = c_void_p()
        if _ft.FT_Init_FreeType(byref(self.library)):
            raise SystemExit("FT_Init_FreeType failed")
        version = c_uint(interpreter)
        if _ft.FT_Property_Set(self.library, b"truetype", b"interpreter-version", byref(version)):
            raise SystemExit(f"FreeType cannot use the TrueType interpreter v{interpreter}")
        self.face = POINTER(_Face)()
        if _ft.FT_New_Face(self.library, str(path).encode(), 0, byref(self.face)):
            raise SystemExit(f"FreeType cannot open {path}")
        self.flags = flags | _LOAD_RENDER
        self.ppem = None

    def char_index(self, code: int) -> int:
        return _ft.FT_Get_Char_Index(self.face, c_long(code))

    def _load(self, glyph_index: int, ppem: int, render: bool):
        if ppem != self.ppem:
            if _ft.FT_Set_Pixel_Sizes(self.face, 0, ppem):
                raise SystemExit(f"FT_Set_Pixel_Sizes {ppem} failed")
            self.ppem = ppem
        flags = self.flags if render else self.flags & ~_LOAD_RENDER
        error = _ft.FT_Load_Glyph(self.face, glyph_index, c_int(flags))
        if error:
            raise SystemExit(f"FreeType could not load glyph {glyph_index} at {ppem} ppem (error {error})")
        return self.face.contents.glyph.contents

    def render(self, glyph_index: int, ppem: int):
        """描いた字 (位置・送り・大きさ・画素)。描けなければ例外"""
        slot = self._load(glyph_index, ppem, True)
        bitmap = slot.bitmap
        size = bitmap.rows * abs(bitmap.pitch)
        pixels = ctypes.string_at(bitmap.buffer, size) if size else b""
        return (slot.bitmap_left, slot.bitmap_top, slot.advance.x, bitmap.width, bitmap.rows, pixels)

    def outline(self, glyph_index: int, ppem: int) -> list[tuple[int, int]]:
        """描画前の、ヒント適用後の全輪郭の点。単位は 1/64 px。"""
        outline = self._load(glyph_index, ppem, False).outline
        return [(outline.points[i].x, outline.points[i].y) for i in range(outline.n_points)]

    def close(self) -> None:
        _ft.FT_Done_Face(self.face)
        _ft.FT_Done_FreeType(self.library)
