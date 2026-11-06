"""HarfBuzz (libharfbuzz) で文字を並べる (組む)。check.py が使う。

Chromium・Firefox・Android などは、HarfBuzz で文字を並べる。フォントの表を読むだけでは分からない
振る舞い (GPOS の無いフォントでの、結合用の記号の代わりの位置合わせや、見えない文字を隠すことなど)
を確かめるため、実際に組む。freetype_render.py と同じく、HarfBuzz の Python のパッケージは使わず、
ctypes で libharfbuzz を直接呼ぶ (Debian / Ubuntu の libharfbuzz0b。依存を増やさない)。
"""

import ctypes
import ctypes.util
from ctypes import POINTER, Structure, byref, c_char_p, c_int, c_int32, c_uint, c_uint32, c_void_p


class _Info(Structure):
    _fields_ = [("codepoint", c_uint32), ("mask", c_uint32), ("cluster", c_uint32),
                ("var1", c_uint32), ("var2", c_uint32)]


class _Position(Structure):
    _fields_ = [("x_advance", c_int32), ("y_advance", c_int32), ("x_offset", c_int32), ("y_offset", c_int32),
                ("var", c_uint32)]


class _Feature(Structure):
    _fields_ = [("tag", c_uint32), ("value", c_uint32), ("start", c_uint), ("end", c_uint)]


_TOP_TO_BOTTOM = 6  # HB_DIRECTION_TTB


def _load_library():
    name = ctypes.util.find_library("harfbuzz") or "libharfbuzz.so.0"
    try:
        library = ctypes.CDLL(name)
    except OSError as error:
        raise SystemExit(f"libharfbuzz is needed to check the shaping (Debian / Ubuntu: libharfbuzz0b): {error}")
    signatures = {
        "hb_blob_create_from_file": ([c_char_p], c_void_p),
        "hb_blob_destroy": ([c_void_p], None),
        "hb_face_create": ([c_void_p, c_uint], c_void_p),
        "hb_face_destroy": ([c_void_p], None),
        "hb_font_create": ([c_void_p], c_void_p),
        "hb_font_destroy": ([c_void_p], None),
        "hb_buffer_create": ([], c_void_p),
        "hb_buffer_destroy": ([c_void_p], None),
        "hb_buffer_add_utf8": ([c_void_p, c_char_p, c_int, c_uint, c_int], None),
        "hb_buffer_set_language": ([c_void_p, c_void_p], None),
        "hb_buffer_set_direction": ([c_void_p, c_int], None),
        "hb_buffer_guess_segment_properties": ([c_void_p], None),
        "hb_buffer_set_script": ([c_void_p, c_uint32], None),
        "hb_script_from_string": ([c_char_p, c_int], c_uint32),
        "hb_language_from_string": ([c_char_p, c_int], c_void_p),
        "hb_feature_from_string": ([c_char_p, c_int, POINTER(_Feature)], c_int),
        "hb_shape": ([c_void_p, c_void_p, c_void_p, c_uint], None),
        "hb_buffer_get_glyph_infos": ([c_void_p, POINTER(c_uint)], POINTER(_Info)),
        "hb_buffer_get_glyph_positions": ([c_void_p, POINTER(c_uint)], POINTER(_Position)),
    }
    for function, (arguments, result) in signatures.items():
        getattr(library, function).argtypes = arguments
        getattr(library, function).restype = result
    return library


_hb = _load_library()


class Shaper:
    """1 つのフォントで組む。大きさは 1 em = unitsPerEm (位置はフォントの単位)"""

    def __init__(self, path):
        blob = _hb.hb_blob_create_from_file(str(path).encode())
        self.face = _hb.hb_face_create(blob, 0)
        _hb.hb_blob_destroy(blob)
        self.font = _hb.hb_font_create(self.face)
        self.languages: dict[str, int] = {}

    def shape(self, text: str, language: str, vertical: bool = False, features=(), script: str | None = None) -> list[tuple]:
        """[(グリフの番号, クラスター, 送り x, 送り y, ずれ x, ずれ y), ...]。用字系は、script (ISO 15924 の
        Latn・Hira など) が無ければ文字から決める (ブラウザのように、記号を前後の字の用字系に入れるには、
        前後に字を置くか、script を指定する)"""
        if language not in self.languages:
            self.languages[language] = _hb.hb_language_from_string(language.encode(), -1)
        buffer = _hb.hb_buffer_create()
        data = text.encode()
        _hb.hb_buffer_add_utf8(buffer, data, len(data), 0, len(data))
        _hb.hb_buffer_set_language(buffer, self.languages[language])
        if script is not None:
            _hb.hb_buffer_set_script(buffer, _hb.hb_script_from_string(script.encode(), -1))
        _hb.hb_buffer_guess_segment_properties(buffer)
        if vertical:
            _hb.hb_buffer_set_direction(buffer, _TOP_TO_BOTTOM)
        array = (_Feature * max(1, len(features)))()
        for i, feature in enumerate(features):
            if not _hb.hb_feature_from_string(feature.encode(), -1, byref(array[i])):
                raise SystemExit(f"HarfBuzz cannot read the feature {feature!r}")
        _hb.hb_shape(self.font, buffer, array, len(features))
        count = c_uint()
        infos = _hb.hb_buffer_get_glyph_infos(buffer, byref(count))
        positions = _hb.hb_buffer_get_glyph_positions(buffer, byref(count))
        result = [(infos[i].codepoint, infos[i].cluster, positions[i].x_advance, positions[i].y_advance,
                   positions[i].x_offset, positions[i].y_offset) for i in range(count.value)]
        _hb.hb_buffer_destroy(buffer)
        return result

    def close(self) -> None:
        _hb.hb_font_destroy(self.font)
        _hb.hb_face_destroy(self.face)
