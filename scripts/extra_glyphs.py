"""元のフォントに無い、本や Web の文章で使う文字を足す。build.py が使う。

- 見えない文字 (ゼロ幅スペース U+200B・ZWNJ U+200C・ZWJ U+200D・単語結合子 U+2060・BOM U+FEFF):
  幅 0 の空の字。フォントに無いと、環境によっては □ が出る
- 空白 (U+2000〜200A・U+202F・U+205F): 決まった幅の空の字。幅は Unicode の決まりに従う (数字の幅の
  空白 U+2007 は 0 の幅、句読点の幅の空白 U+2008 は . の幅)
- 改行しないハイフン (U+2011): - と同じ字
- 2 倍・3 倍ダッシュ (⸺ U+2E3A・⸻ U+2E3B): ― (U+2015) を 2 つ・3 つつないだ字。縦組では、縦組の ―
  をつないだ字にする (vert・vrt2)。部品を並べた字 (複合グリフ) にする (横組の ― はヒンティングを外した字)
- 〞 (U+301E): 〟 (U+301F) を、〝 (U+301D) と同じ高さへ持ち上げた字。縦組では 〟 の縦組の字にする
"""

from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphComponent

INVISIBLE = {0x200B: "uni200B", 0x200C: "uni200C", 0x200D: "uni200D", 0x2060: "uni2060", 0xFEFF: "uniFEFF"}

# 空白 → 幅 (em に対する割合)。"digit" は 0 の幅、"period" は . の幅
SPACES = {
    0x2000: 1 / 2,  # EN QUAD
    0x2001: 1,  # EM QUAD
    0x2002: 1 / 2,  # EN SPACE
    0x2003: 1,  # EM SPACE
    0x2004: 1 / 3,  # THREE-PER-EM SPACE
    0x2005: 1 / 4,  # FOUR-PER-EM SPACE
    0x2006: 1 / 6,  # SIX-PER-EM SPACE
    0x2007: "digit",  # FIGURE SPACE
    0x2008: "period",  # PUNCTUATION SPACE
    0x2009: 1 / 5,  # THIN SPACE
    0x200A: 1 / 10,  # HAIR SPACE
    0x202F: 1 / 5,  # NARROW NO-BREAK SPACE (THIN SPACE と同じ幅)
    0x205F: 4 / 18,  # MEDIUM MATHEMATICAL SPACE
}

NON_BREAKING_HYPHEN = 0x2011
DASHES = {0x2E3A: 2, 0x2E3B: 3}  # ⸺ ⸻ → ― の数
HORIZONTAL_BAR = 0x2015
DOUBLE_PRIME_QUOTE, LOW_DOUBLE_PRIME_QUOTE, REVERSED_DOUBLE_PRIME_QUOTE = 0x301E, 0x301F, 0x301D


def _add(font: TTFont, name: str, glyph: Glyph, advance: int, vertical: tuple[int, int], codes=()) -> None:
    if name in font["hmtx"].metrics:
        raise SystemExit(f"{name} is already in the font")
    order = font.getGlyphOrder() + [name]
    font.setGlyphOrder(order)
    font["glyf"].glyphOrder = order
    font["glyf"][name] = glyph
    glyph.recalcBounds(font["glyf"])
    font["hmtx"][name] = (advance, getattr(glyph, "xMin", 0) if glyph.numberOfContours else 0)
    font["vmtx"][name] = vertical
    _map(font, codes, name)


def _map(font: TTFont, codes, name: str) -> None:
    cmap = font.getBestCmap()
    for code in codes:
        if code in cmap:
            raise SystemExit(f"U+{code:04X} is already in the font")
        for table in font["cmap"].tables:
            if table.isUnicode():  # 同じ表を分け合う subtable もある
                table.cmap[code] = name


def _empty() -> Glyph:
    return TTGlyphPen(None).glyph()


def _joined(name: str, count: int, dx: int, dy: int) -> Glyph:
    """name を count 個、(dx, dy) ずつずらして並べた複合グリフ"""
    glyph = Glyph()
    glyph.numberOfContours = -1
    glyph.components = []
    for k in range(count):
        component = GlyphComponent()
        component.glyphName, component.x, component.y = name, dx * k, dy * k
        component.flags = 0x4  # ROUND_XY_TO_GRID
        glyph.components.append(component)
    return glyph


def add(font: TTFont) -> dict[str, int]:
    import build  # feature_lookups など (build.py がこのモジュールを読み込むので、ここで読み込む)

    cmap = font.getBestCmap()
    em = font["head"].unitsPerEm

    # 見えない文字は、1 つの空の字を指す
    _add(font, "zerowidth", _empty(), 0, (0, 0), INVISIBLE)

    widths = {"digit": font["hmtx"][cmap[0x30]][0], "period": font["hmtx"][cmap[0x2E]][0]}
    for code, width in SPACES.items():
        advance = widths[width] if isinstance(width, str) else round(em * width)
        _add(font, f"uni{code:04X}", _empty(), advance, (advance, 0), [code])

    _map(font, [NON_BREAKING_HYPHEN], cmap[0x2D])

    # ⸺ ⸻。横組は ― を右へ、縦組は縦組の ― を下へつなぐ
    bar = cmap[HORIZONTAL_BAR]
    gsub = font["GSUB"].table
    vertical_lookups = sorted({*build.feature_lookups(gsub, "vert"), *build.feature_lookups(gsub, "vrt2")})
    upright = build.single_mapping(gsub, "vert", {bar}).get(bar)
    if upright is None:
        raise SystemExit("― has no vertical form")
    if font["hmtx"][bar][0] != em or font["vmtx"][upright][0] != em:
        raise SystemExit("― is not 1 em wide and high")
    for code, count in DASHES.items():
        name, vertical = f"uni{code:04X}", f"uni{code:04X}.vert"
        _add(font, name, _joined(bar, count, em, 0), em * count, (font["vmtx"][bar][0] * count, font["vmtx"][bar][1]), [code])
        _add(font, vertical, _joined(upright, count, 0, -em), font["hmtx"][upright][0],
             (em * count, font["vmtx"][upright][1]))
        for index in vertical_lookups:
            next(build.subtables(gsub, index, "mapping")).mapping[name] = vertical

    # 〞。〟 を 〝 の高さへ持ち上げる
    low, high = cmap[LOW_DOUBLE_PRIME_QUOTE], cmap[REVERSED_DOUBLE_PRIME_QUOTE]
    low_form = build.single_mapping(gsub, "vert", {low}).get(low)
    if low_form is None:
        raise SystemExit("〟 has no vertical form")
    glyf = font["glyf"]
    lift = glyf[high].yMin - glyf[low].yMin
    name = f"uni{DOUBLE_PRIME_QUOTE:04X}"
    glyph = _joined(low, 1, 0, 0)
    glyph.components[0].y = lift
    advance, top_side = font["vmtx"][low]
    _add(font, name, glyph, font["hmtx"][low][0], (advance, top_side - lift), [DOUBLE_PRIME_QUOTE])
    for index in vertical_lookups:
        next(build.subtables(gsub, index, "mapping")).mapping[name] = low_form
    return {"invisible": len(INVISIBLE), "spaces": len(SPACES), "dashes": len(DASHES)}
