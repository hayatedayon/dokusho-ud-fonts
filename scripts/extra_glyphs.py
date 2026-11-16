"""元のフォントに無い、本や Web の文章で使う文字を足す。build.py が使う。

- 見えない文字 (ゼロ幅スペース U+200B・ZWNJ U+200C・ZWJ U+200D・単語結合子 U+2060・BOM U+FEFF):
  幅 0 の空の字。フォントに無いと、環境によっては □ が出る
- 空白 (U+2000〜200A・U+202F・U+205F): 決まった幅の空の字。幅は Unicode の決まりに従う (数字の幅の
  空白 U+2007 は 0 の幅、句読点の幅の空白 U+2008 は . の幅)
- 改行しないハイフン (U+2011): - と同じ字
- 2 倍・3 倍ダッシュ (⸺ U+2E3A・⸻ U+2E3B): ― (U+2015) を 2 つ・3 つつないだ字。縦組では、縦組の ―
  をつないだ字にする (vert・vrt2)。部品を並べた字 (複合グリフ) にする (横組の ― はヒンティングを外した字)
- 〞 (U+301E): 〝 (U+301D) を全角の枠の中心で左右反転した字 (Noto Serif CJK JP などと同じ向き)。縦方向の
  ヒントは small_type.hint_marks が付ける。縦組では 〟 の縦組の字にする
- 𠮷 (U+20BB7): 圭の上部の土と、吉の下部の口を組み合わせる。元の線の太さを保つ (ヒントなし)
- 〱・〲 (U+3031・3032): 〳/〴 と 〵 をつなぎ、縦組では２セルの１字にする (ヒントなし)
- 縦組の 2 セル・3 セルの字 (〱 〲 ⸺ ⸻): vert・vrt2 の 2 段目で、輪郭のある字 1 つと空白の字に置き換える
  (split_vertical_cells。縦の送りに vmtx を使わない環境のため)
"""

import copy
from array import array

from fontTools.pens.reverseContourPen import ReverseContourPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphComponent, GlyphCoordinates

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
REPEAT_MARKS = (0x3031, 0x3032)  # 〱 〲
VERTICAL_CELL_CODES = (*REPEAT_MARKS, *DASHES)  # 縦組で 2 セル以上の字 (split_vertical_cells が 1 セルずつの字に分ける)
BLANK_CELL = "vertical.blank"  # 縦組の 2 セル以上の字の、2 つ目からの空白の字 (横の送りが 1 em。vrt2 用)
BLANK_ZERO = "vertical.blank0"  # 同じ、横の送りが 0 の空白の字 (vert 用。GPOS で横の送りを足す)
SPACING_FEATURE = "curs"  # 上の GPOS を入れる機能 (DirectWrite が使わず、WebKitGTK が使うもの)
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
    # BMP の format 4 には非 BMP の文字を入れない。従来の割り当てを写した format 12 を
    # Windows / Unicode に用意し、𠮷をそこにだけ加える。BMP の既存表はそのまま保つ。
    if any(code > 0xFFFF for code in codes):
        for platform, encoding in ((3, 10), (0, 4)):
            if not any(t.format == 12 and (t.platformID, t.platEncID) == (platform, encoding)
                       for t in font["cmap"].tables):
                table = CmapSubtable.newSubtable(12)
                table.platformID, table.platEncID, table.language = platform, encoding, 0
                table.cmap = dict(cmap)
                font["cmap"].tables.append(table)
    for code in codes:
        if code in cmap:
            raise SystemExit(f"U+{code:04X} is already in the font")
        for table in font["cmap"].tables:
            if table.isUnicode() and table.format != 14 and (code <= 0xFFFF or table.format in (12, 13)):
                table.cmap[code] = name


def _contours(font: TTFont, name: str):
    coordinates, ends, flags = font["glyf"][name].getCoordinates(font["glyf"])
    start = 0
    result = []
    for end in ends:
        result.append((list(coordinates[start:end + 1]), list(flags[start:end + 1])))
        start = end + 1
    return result


def _simple(contours) -> Glyph:
    glyph = _empty()
    glyph.coordinates, glyph.flags, glyph.endPtsOfContours = GlyphCoordinates(), array("B"), []
    for points, flags in contours:
        glyph.coordinates.extend(points)
        glyph.flags.extend(flags)
        glyph.endPtsOfContours.append(len(glyph.coordinates) - 1)
    glyph.numberOfContours = len(contours)
    return glyph


def _translate(contour, dx=0, dy=0, scale=1):
    points, flags = contour
    return ([(round(x * scale + dx), round(y * scale + dy)) for x, y in points], flags)


def _kanji(font: TTFont) -> None:
    cmap = font.getBestCmap()
    kichi = _contours(font, cmap[0x5409])
    # 圭の上部は、既に漢字の上半分に収まる「土」。土全体を縦に縮めると横画だけが
    # 細くなるので、この部品を平行移動だけで吉の上部と入れ替える。口の輪郭はそのまま。
    upper = max(kichi, key=lambda c: min(y for x, y in c[0]))
    earth = max(_contours(font, cmap[0x572D]), key=lambda c: min(y for x, y in c[0]))
    dx = round((min(x for x, y in upper[0]) + max(x for x, y in upper[0])
                - min(x for x, y in earth[0]) - max(x for x, y in earth[0])) / 2)
    dy = max(y for x, y in upper[0]) - max(y for x, y in earth[0])
    contours = [c for c in kichi if c is not upper] + [_translate(earth, dx, dy)]
    _add(font, "u20BB7", _simple(contours), font["hmtx"][cmap[0x5409]][0],
         font["vmtx"][cmap[0x5409]], [0x20BB7])


def _repeat(font: TTFont, upper_code: int):
    cmap = font.getBestCmap()
    upper = _contours(font, cmap[upper_code])
    lower = _contours(font, cmap[0x3035])[0]
    # 上下部品の接合辺の２点を一致させ、辺を除いて１輪郭へつなぐ (1 単位の丸め差も吸収)。
    points, flags = upper[0]
    bottom = min(y for x, y in points)
    lower = _translate(lower, dy=bottom - max(y for x, y in lower[0]))
    def chain(contour, y):
        pts, fl = contour
        i = next(i for i in range(len(pts)) if pts[i][1] == pts[(i + 1) % len(pts)][1] == y)
        j = (i + 1) % len(pts)
        return pts[j:] + pts[:j], fl[j:] + fl[:j]
    a, af = chain((points, flags), bottom)
    b, bf = chain(lower, bottom)
    if a[-1] != b[0] or a[0] != b[-1]:
        raise SystemExit("repeat-mark halves do not share a joining edge")
    return [(a + b[1:-1], af + bf[1:-1]), *upper[1:]]


def _japanese_additions(font: TTFont, vertical_lookups) -> None:
    import build
    _kanji(font)
    em = font["head"].unitsPerEm
    for code, upper in ((0x3031, 0x3033), (0x3032, 0x3034)):
        contours = _repeat(font, upper)
        name, vertical = f"uni{code:04X}", f"uni{code:04X}.vert"
        # Unicode §6.2 は２つの仮名セルを使う double-height 字形と規定する。
        # https://www.unicode.org/versions/Unicode17.0.0/core-spec/chapter-6/
        # 手元の Noto Serif CJK JP も hAdvance=1 em / vAdvance=2 em (輪郭は使わない)。
        # 横組表示は１セル内の縮小見本とし、縦組だけ等倍の線と２セルの字送りを使う。
        # 縦組字は１行の上下枠ではなく、原点から２セルの縦枠内に収める (⸺ ⸻ と同じ扱い)。
        ys = [y for pts, flags in contours for x, y in pts]
        dy = (font["hhea"].ascent + font["hhea"].descent - .5 * (min(ys) + max(ys))) / 2
        compact = [_translate(c, dx=em / 4, dy=dy, scale=.5) for c in contours]
        glyph = _simple(compact)
        glyph.recalcBounds(font["glyf"])
        _add(font, name, glyph, em, (2 * em, font["hhea"].ascent - glyph.yMax), [code])
        glyph = _simple(contours)
        glyph.recalcBounds(font["glyf"])
        _add(font, vertical, glyph, em, (2 * em, font["hhea"].ascent - glyph.yMax))
        for index in vertical_lookups:
            next(build.subtables(font["GSUB"].table, index, "mapping")).mapping[name] = vertical


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

    # 〞。〝 を em の中心で左右反転する。輪郭の向きを保つため、点の順序も逆にする
    low, high = cmap[LOW_DOUBLE_PRIME_QUOTE], cmap[REVERSED_DOUBLE_PRIME_QUOTE]
    low_form = build.single_mapping(gsub, "vert", {low}).get(low)
    if low_form is None:
        raise SystemExit("〟 has no vertical form")
    name = f"uni{DOUBLE_PRIME_QUOTE:04X}"
    glyphs = font.getGlyphSet()
    pen = TTGlyphPen(glyphs)
    glyphs[high].draw(TransformPen(ReverseContourPen(pen), (-1, 0, 0, 1, em, 0)))
    _add(font, name, pen.glyph(), font["hmtx"][high][0], font["vmtx"][high], [DOUBLE_PRIME_QUOTE])
    for index in vertical_lookups:
        next(build.subtables(gsub, index, "mapping")).mapping[name] = low_form
    _japanese_additions(font, vertical_lookups)
    return {"invisible": len(INVISIBLE), "spaces": len(SPACES), "dashes": len(DASHES), "japanese": 3}


def _add_feature(table, tag: str, lookup_index: int) -> None:
    """GSUB / GPOS の table に、lookup_index だけを使う tag の機能を足し、すべての文字体系・言語系に入れる
    (機能の記録は tag の順に並べ直す)"""
    feature = otTables.Feature()
    feature.FeatureParams, feature.LookupListIndex, feature.LookupCount = None, [lookup_index], 1
    record = otTables.FeatureRecord()
    record.FeatureTag, record.Feature = tag, feature
    records = [*table.FeatureList.FeatureRecord, record]
    order = sorted(range(len(records)), key=lambda i: (records[i].FeatureTag, i))
    remap = {old: new for new, old in enumerate(order)}
    table.FeatureList.FeatureRecord = [records[i] for i in order]
    table.FeatureList.FeatureCount = len(records)
    for script in table.ScriptList.ScriptRecord:
        systems = [script.Script.DefaultLangSys] if script.Script.DefaultLangSys else []
        systems += [r.LangSys for r in script.Script.LangSysRecord]
        for system in systems:
            system.FeatureIndex = sorted([remap[i] for i in system.FeatureIndex] + [remap[len(records) - 1]])
            system.FeatureCount = len(system.FeatureIndex)


def split_vertical_cells(font: TTFont, codes=VERTICAL_CELL_CODES) -> dict[str, dict[str, list[str]]]:
    """縦組で 2 セル (以上) の字を、輪郭のある字 1 つと空白の字の並びに置き換える。build.py が、vert・vrt2 の
    lookup を足し終えた後 (どの lookup よりも後に適用する lookup を足すため) に呼ぶ。

    縦組の字の送りは、環境で決め方が違う。HarfBuzz (Chrome・Firefox) と DirectWrite は縦の送り (vmtx) を使い、
    WebKitGTK は 1 em ずつ (縦の送りは使わず、横の送り hmtx と GPOS の横の送りを足したもの) 、CoreText は
    横の送り (hmtx) を足したものを使う。1 段目 (今までどおり) は cmap の字 → 2 セルの字 (縦の送り 2 em)。
    2 段目は、その 2 セルの字 → [輪郭が同じで縦の送りも 2 em の字, 空白の字 (縦の送り 0) …] (3 セルなら空白が 2 つ)。
    空白の字は環境ごとに変える。vert (HarfBuzz・DirectWrite・WebKitGTK) では横の送りが 0 の空白 (BLANK_ZERO) に、
    GPOS の curs で横の送りを 1 em 足す。DirectWrite は、1 つの文字から出た字の横の送りの合計で、字を左右に
    ずらして置く (横の送りが 0 でないと 1 つ目の字が半 em 左にずれる)。curs の GPOS は DirectWrite が使わない。
    WebKitGTK は使う (vert の GPOS や kern は、DirectWrite が使うか、WebKitGTK が使わない)。vrt2 (CoreText) では
    横の送りが 1 em の空白 (BLANK_CELL)。CoreText は GPOS の横の送りを使わず、hmtx を足す。
    どの環境でも、合計は 2 em (3 セルなら 3 em) になり、輪郭は 1 つ目の字だけが持つ。複数の字への置き換え
    (GSUB の型 2) を使えない環境は、2 段目を飛ばして 1 段目の字 (縦の送り 2 em) をそのまま使う。"""
    import build
    gsub, gpos = font["GSUB"].table, font["GPOS"].table
    cmap, em = font.getBestCmap(), font["head"].unitsPerEm
    mappings: dict[str, dict[str, list[str]]] = {"vert": {}, "vrt2": {}}
    for code in codes:
        name = cmap[code]
        wide = build.single_mapping(gsub, "vert", {name}).get(name)
        if wide is None or build.single_mapping(gsub, "vrt2", {name}).get(name) != wide:
            raise SystemExit(f"U+{code:04X} has no common vertical form in vert and vrt2")
        advance, bearing = font["vmtx"][wide]
        if advance % em or advance // em < 2:
            raise SystemExit(f"{wide} does not advance a whole number of cells (at least 2) in vertical text")
        if wide in mappings["vert"]:
            raise SystemExit(f"{wide} is the vertical form of more than one character")
        if font["hmtx"][wide][0] != em:
            raise SystemExit(f"{wide} is not one cell wide")
        glyph = copy.deepcopy(font["glyf"][wide])
        glyph.expand(font["glyf"])
        # 輪郭も、縦の原点 (yMax + 上側ベアリング) も縦の送りも 2 セルの字と同じ。2 セルの字そのものを使わないのは、
        # vert と vrt2 の両方を使う環境で、2 段目が 2 度かからないようにするため
        _add(font, f"{wide}.cell", glyph, em, (advance, bearing))
        for blank, horizontal in ((BLANK_ZERO, 0), (BLANK_CELL, em)):
            if blank not in font["hmtx"].metrics:
                _add(font, blank, _empty(), horizontal, (0, 0))
        mappings["vert"][wide] = [f"{wide}.cell"] + [BLANK_ZERO] * (advance // em - 1)
        mappings["vrt2"][wide] = [f"{wide}.cell"] + [BLANK_CELL] * (advance // em - 1)
    for tag, mapping in mappings.items():
        subtable = otTables.MultipleSubst()
        subtable.Format, subtable.mapping = 1, mapping
        lookup = otTables.Lookup()
        lookup.LookupType, lookup.LookupFlag, lookup.SubTable, lookup.SubTableCount = 2, 0, [subtable], 1
        gsub.LookupList.Lookup.append(lookup)
        gsub.LookupList.LookupCount = len(gsub.LookupList.Lookup)
        index = len(gsub.LookupList.Lookup) - 1
        seen = set()
        for record in gsub.FeatureList.FeatureRecord:
            if record.FeatureTag == tag and id(record.Feature) not in seen:
                seen.add(id(record.Feature))
                record.Feature.LookupListIndex = [*record.Feature.LookupListIndex, index]
                record.Feature.LookupCount = len(record.Feature.LookupListIndex)
    # 空白 (横の送りが 0) に、横の送りを 1 em 足す GPOS。WebKitGTK だけが、機能 curs のこの調整を使う
    position = otTables.SinglePos()
    position.Format = 1
    position.Coverage = otTables.Coverage()
    position.Coverage.glyphs = [BLANK_ZERO]
    position.ValueFormat = 0x4  # XAdvance
    position.Value = otTables.ValueRecord()
    position.Value.XAdvance = em
    lookup = otTables.Lookup()
    lookup.LookupType, lookup.LookupFlag, lookup.SubTable, lookup.SubTableCount = 1, 0, [position], 1
    gpos.LookupList.Lookup.append(lookup)
    gpos.LookupList.LookupCount = len(gpos.LookupList.Lookup)
    _add_feature(gpos, SPACING_FEATURE, len(gpos.LookupList.Lookup) - 1)
    return mappings
