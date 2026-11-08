"""結合用の記号 (アクセント U+0300〜036F と、仮名の濁点・半濁点 U+3099・U+309A) を、前の字に乗せる。
build.py が使う。

元のフォントの結合用の記号は、字幅のある字 (アクセントは半角、濁点・半濁点は全角) で、GPOS も GDEF
も無い。HarfBuzz (Chromium・Firefox・Android など) は、GPOS の無いフォントでは、結合用の記号の
字幅を 0 にして、前の字の上か下に置く (代わりの位置合わせ)。読書 UD は halt などの GPOS を足したので、
これが働かず、q̃ の ~ が q の右に、あ゙ の濁点が あ の後ろに出ていた。合成済みの字 (é・が など) の
ある組み合わせは、文字を並べる仕組みが合成済みの字にするので変わらない。

1. 結合用の記号の字を、字幅 0 にして、前の字に重なるように左へずらす (アクセントは元の字幅の半角
   だけ、二つの字にかかる記号 ͡ は半角の半分、濁点・半濁点は、前の字の枠の右上になる所へ)。BIZ UD
   は、半角の ´ ｀ ¨ (hwid の置き換え先) にも結合用のアクセントの字を使うので、その字は build.py が
   BIZ UD の字のまま <名前>.hwid として残す。˜ (U+02DC) と同じ字の U+0303 には、別の字
   (<名前>.mark) を足す。合字 (ccmp の ə と結合用のアクセントなど) は、そのままつながる
2. GDEF で、新しい字を記号、前に来る字 (欧字・全角の英数字・ギリシャ文字・キリル文字と仮名) を基底の字とし、
   GPOS の mark と mkmk を作る (spacing.py が halt などと一緒に組み込む)。アンカーの位置は:
   - 上の記号 (結合クラス 230): 字のインクの左右の真ん中の、インクの上。x の高さより低い字は x の
     高さ。記号のアンカーは x の高さなので、x の高さの字では、記号は元の字の高さのまま
   - 右上の記号 (232): 字のインクの右の上
   - 下の記号 (220): ベースライン。ディセンダーのある字 (インクの下が em の 1/16 より下) は、
     インクの下
   - 重ねる記号 (1): x の高さか字の高さの半分
   - 濁点・半濁点: 合成済みの濁音・半濁音の字 (が・ぱ など) の、濁点・半濁点の右の端の中央値に、
     記号の右の端がそろう所。高さは元の字のまま。縦組の小書きの仮名 (っ・ゃ・ㇰ など、右上に寄った字) は、
     濁点・半濁点が続くときだけ横組と同じ位置へ戻し、記号と重ならないようにする
   - 上の記号の上と、下の記号の下に、もう一つ重ねられる (mkmk)
3. i の後に上の記号 (2 つの字の上にかかる ͡ も) が続くときは、下に付く記号などを挟んでも、点の無い ı に
   する (ccmp。GDEF の MarkGlyphSetsDef を作ってから足す)。全角の ｉ も、点を除いた字 (uniFF49.dotless) にする
"""

import copy
import unicodedata
from statistics import median

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates

import fraction_digits
import spec

SUFFIX = ".mark"
KANA_MARKS = {0x3099: "voiced", 0x309A: "semivoiced"}
# 結合クラス → 記号の置き方
KINDS = {230: "above", 232: "aboveright", 220: "below", 1: "overlay", 233: "double", 234: "double"}
# アクセントを乗せる字 (欧字と、全角のギリシャ文字・キリル文字・英数字。キリル文字の強勢記号 моло́ко など)
BASE_RANGES = [(0x0370, 0x03FF), (0x0400, 0x052F), (0xFF10, 0xFF19), (0xFF21, 0xFF3A), (0xFF41, 0xFF5A)]
KANA_RANGES = [(0x3041, 0x30FF), (0x31F0, 0x31FF)]
FULLWIDTH_I = 0xFF49


def kind(code: int) -> str:
    if code in KANA_MARKS:
        return "kana"
    combining = unicodedata.combining(chr(code))
    if combining not in KINDS:
        raise SystemExit(f"U+{code:04X} has the combining class {combining}, which is not handled")
    return KINDS[combining]


def ink(font: TTFont, name: str):
    """インクの外形 (曲線そのものの外形。glyf の外形は、曲線の外の制御点も含む)"""
    glyph_set = font.getGlyphSet()
    pen = BoundsPen(glyph_set)
    glyph_set[name].draw(pen)
    return pen.bounds


def unicode_tables(font: TTFont):
    return [table for table in font["cmap"].tables if table.isUnicode()]


def kana_target(font: TTFont, mark: int) -> float:
    """合成済みの濁音・半濁音の字の、インクの右の端 (濁点・半濁点の右の端) の中央値"""
    cmap = font.getBestCmap()
    ends = []
    for code in range(0x3041, 0x3100):
        parts = unicodedata.decomposition(chr(code)).split()
        if len(parts) == 2 and int(parts[1], 16) == mark and code in cmap:
            ends.append(ink(font, cmap[code])[2])
    if len(ends) < 5:
        raise SystemExit(f"too few precomposed kana with U+{mark:04X}")
    return median(ends)


def prepare(font: TTFont) -> dict:
    """結合用の記号の字を、字幅 0 にして左へずらす。BIZ UD のヒンティングはそのまま。欧字を BIZ UDP
    の字にする前 (˜ U+02DC が BIZ UDP の字になる前) に、hwid の字を取っておいた後で呼ぶ。返す changed
    は、その場で変えた字 (build.keep_half_widths が、hwid の置き換え先なら BIZ UD の字を残す)"""
    cmap = font.getBestCmap()
    em = font["head"].unitsPerEm
    glyf, hmtx, vmtx = font["glyf"], font["hmtx"], font["vmtx"]
    marks = {code: name for code, name in cmap.items() if unicodedata.category(chr(code)) in ("Mn", "Me")}
    unexpected = [code for code in marks if not (0x0300 <= code <= 0x036F or code in KANA_MARKS)]
    if unexpected:
        raise SystemExit(f"combining marks not handled: {[f'U+{c:04X}' for c in unexpected]}")
    # ほかの文字 (˜ U+02DC など) にも割り当てられた字は、結合用の記号に別の字を足す
    shared = {name for code, name in cmap.items() if code not in marks and name in marks.values()}
    composite = {c.glyphName for name in font.getGlyphOrder() if glyf[name].isComposite()
                 for c in glyf[name].components}
    targets = {code: kana_target(font, code) for code in KANA_MARKS if code in marks}
    kinds: dict[str, str] = {}
    changed: set[str] = set()
    for code, old in sorted(marks.items()):
        if old in composite:
            raise SystemExit(f"U+{code:04X}: {old} is a component of other glyphs")
        k = kind(code)
        glyph = glyf[old]
        glyph.expand(glyf)
        if old in shared:
            glyph = copy.deepcopy(glyph)
        if glyph.isComposite() or not glyph.numberOfContours:
            raise SystemExit(f"U+{code:04X}: expected a simple glyph with an outline")
        advance = hmtx[old][0]
        if k == "kana":
            dx = round(targets[code] - em - ink(font, old)[2])  # 前の字の枠の右上
        elif k == "double":
            dx = -advance // 2
        else:
            dx = -advance
        glyph.coordinates.translate((dx, 0))
        glyph.recalcBounds(glyf)
        if old in shared:
            name = old + SUFFIX
            fraction_digits._add_glyph(font, name, glyph, 0, (0, vmtx[old][1]))
            for table in unicode_tables(font):
                if table.cmap.get(code) == old:
                    table.cmap[code] = name
        else:
            name = old
            hmtx[name] = (0, glyph.xMin)
            vmtx[name] = (0, vmtx[name][1])
            changed.add(name)
        kinds[name] = k
    return {"kinds": kinds, "changed": changed, "targets": targets}


def add_fullwidth_dotless(font: TTFont) -> str:
    """全角の ｉ から点 (いちばん上の輪郭) を除いた字を足し、その名前を返す。縦組の原点は元の字と同じにする"""
    glyf, name = font["glyf"], font.getBestCmap()[FULLWIDTH_I]
    glyph = copy.deepcopy(glyf[name])
    glyph.expand(glyf)
    glyph.removeHinting()
    if glyph.isComposite() or glyph.numberOfContours != 2:
        raise SystemExit("full-width i is expected to have a stem and a dot")
    ends = list(glyph.endPtsOfContours)
    ranges = [(0, ends[0] + 1), (ends[0] + 1, ends[1] + 1)]
    bottoms = [min(glyph.coordinates[i][1] for i in range(*r)) for r in ranges]
    start, stop = ranges[bottoms.index(min(bottoms))]
    glyph.coordinates = GlyphCoordinates(glyph.coordinates[start:stop])
    glyph.flags = glyph.flags[start:stop]
    glyph.endPtsOfContours = [stop - start - 1]
    glyph.numberOfContours = 1
    glyph.recalcBounds(glyf)
    advance, top_side = font["vmtx"][name]
    dotless = name + ".dotless"
    fraction_digits._add_glyph(font, dotless, glyph, font["hmtx"][name][0],
                               (advance, top_side + glyf[name].yMax - glyph.yMax))
    return dotless


def add(font: TTFont, prepared: dict, ruby: dict[str, str] | None = None) -> dict:
    """GPOS と GDEF の機能ファイルの文と、i を ı にする上の記号の並びを返す (spacing.add の後に dotless_i を呼ぶ)"""
    import build

    kinds, targets = prepared["kinds"], prepared["targets"]
    fullwidth_dotless = add_fullwidth_dotless(font)
    gsub = font["GSUB"].table
    cmap = font.getBestCmap()
    x_height = ink(font, cmap[0x78])[3]
    em = font["head"].unitsPerEm
    descender = -em / 16  # これより下に出る字 (ディセンダーのある字) だけ、下の記号を下げる。丸い字の
    # オーバーシュート (o の下で -41 ほど) は、ベースラインとみなす
    mark_names = set(kinds)
    latin_bases, kana_bases = {}, set()
    base_codes = list(spec.LATIN) + [c for start, end in BASE_RANGES for c in range(start, end + 1)]
    for code in base_codes:
        name = cmap.get(code)
        if name and name not in mark_names and unicodedata.category(chr(code))[0] in "LN":
            bounds = ink(font, name)
            if bounds:
                latin_bases[name] = bounds
    # tnum の 1・斜線の 0 (zero)・半角 (hwid)・全角 (fwid) に置き換えた字にもアクセントを乗せる
    for tag in ("tnum", "zero", "hwid", "fwid"):
        for target in build.single_mapping(gsub, tag, set(latin_bases)).values():
            if target not in mark_names and target not in latin_bases:
                bounds = ink(font, target)
                if bounds:
                    latin_bases[target] = bounds
    latin_bases[fullwidth_dotless] = ink(font, fullwidth_dotless)
    vertical = {}
    for tag in ("vert", "vrt2"):
        for subtable in build.feature_subtables(gsub, tag, "mapping"):
            for key, value in subtable.mapping.items():
                vertical.setdefault(key, set()).add(value)
    small_vert: dict[str, tuple[int, int]] = {}
    for code in [c for start, end in KANA_RANGES for c in range(start, end + 1)]:
        name = cmap.get(code)
        if name and name not in mark_names and unicodedata.category(chr(code))[0] == "L":
            kana_bases.add(name)
            verts = vertical.get(name, ())
            kana_bases.update(verts)
            # 小書きの仮名 (っ・ゃ・ㇰ など、Lo で縦組の字があるもの) は、縦組では右上に寄っており、
            # そのままでは濁点・半濁点と重なる。記号が続くときだけ横組と同じ位置へ戻し、記号も同じだけずらす
            if unicodedata.category(chr(code)) == "Lo":
                bh = ink(font, name)
                for vert_name in sorted(verts):
                    if vert_name != name:
                        bv = ink(font, vert_name)
                        dx = round(((bv[0] + bv[2]) - (bh[0] + bh[2])) / 2)
                        dy = round(((bv[1] + bv[3]) - (bh[1] + bh[3])) / 2)
                        if dx <= 0 or dy <= 0:
                            raise SystemExit(f"{vert_name}: unexpected vertical small kana shift ({dx}, {dy})")
                        small_vert[vert_name] = (dx, dy)
    for source, target in (ruby or {}).items():
        if source in kana_bases:
            kana_bases.add(target)
        if source in small_vert:
            small_vert[target] = small_vert[source]
    if set(latin_bases) & kana_bases:
        raise SystemExit("a glyph is both a Latin and a kana base")

    def anchor(x: float, y: float) -> str:
        return f"<anchor {round(x)} {round(y)}>"

    lines = []
    above, below, dotless_above = [], [], []
    for name, k in sorted(kinds.items()):
        x0, y0, x1, y1 = ink(font, name)
        center = (x0 + x1) / 2
        if k == "above":
            lines.append(f"markClass {name} {anchor(center, x_height)} @above;")
            above.append(name)
            dotless_above.append(name)
        elif k == "aboveright":
            lines.append(f"markClass {name} {anchor(x0, x_height)} @aboveright;")
            above.append(name)
            dotless_above.append(name)
        elif k == "below":
            lines.append(f"markClass {name} {anchor(center, 0)} @below;")
            below.append(name)
        elif k == "overlay":
            lines.append(f"markClass {name} {anchor(center, x_height / 2)} @overlay;")
        elif k == "double" and unicodedata.combining(chr(cmap_code(cmap, name))) == 234:
            dotless_above.append(name)
        elif k == "kana":
            lines.append(f"markClass {name} {anchor(x1 - targets[cmap_code(cmap, name)], 0)} @kana;")
    used = set(kinds.values())
    lines.append("lookup MarkLatin {")
    for name, (x0, y0, x1, y1) in sorted(latin_bases.items()):
        center, top = (x0 + x1) / 2, max(y1, x_height)
        parts = [f"{anchor(center, top)} mark @above"]
        if "aboveright" in used:
            parts.append(f"{anchor(x1, top)} mark @aboveright")
        if "below" in used:
            parts.append(f"{anchor(center, y0 if y0 < descender else 0)} mark @below")
        if "overlay" in used:
            parts.append(f"{anchor(center, top / 2)} mark @overlay")
        lines.append(f"  pos base {name} {' '.join(parts)};")
    lines.append("} MarkLatin;")
    kana_marks = sorted(n for n, k in kinds.items() if k == "kana")
    if "kana" in used:
        if small_vert:
            lines.append("lookup KanaSmallShift {")
            for vert_name, (dx, dy) in sorted(small_vert.items()):
                lines.append(f"  pos {vert_name} <{-dx} {-dy} 0 0>;")
            lines.append("} KanaSmallShift;")
            lines.append("lookup KanaSmallVert {")
            # 間にほかの記号 (U+0334 など) があっても、濁点・半濁点を見る (MarkKana のアンカーは、ずらす前提)
            lines.append(f"  lookupflag UseMarkFilteringSet [{' '.join(kana_marks)}];")
            lines.append(f"  pos [{' '.join(sorted(small_vert))}]' lookup KanaSmallShift "
                         f"[{' '.join(kana_marks)}];")
            lines.append("} KanaSmallVert;")
        lines.append("lookup MarkKana {")
        plain_kana = sorted(kana_bases - set(small_vert))
        if plain_kana:
            lines.append(f"  pos base [{' '.join(plain_kana)}] <anchor 0 0> mark @kana;")
        for vert_name, (dx, dy) in sorted(small_vert.items()):
            lines.append(f"  pos base {vert_name} {anchor(dx, dy)} mark @kana;")
        lines.append("} MarkKana;")
    lines.append("feature mark {")
    lines.append("  lookup MarkLatin;")
    if "kana" in used:
        if small_vert:
            lines.append("  lookup KanaSmallVert;")
        lines.append("  lookup MarkKana;")
    lines.append("} mark;")

    # 上の記号の上に上の記号を、下の記号の下に下の記号を重ねる。ほかの種類の記号は飛ばす
    lines.append("feature mkmk {")
    for label, group, cls in (("Above", above, "@above"), ("Below", below, "@below")):
        stacked = [n for n in group if kinds[n] != "aboveright"]
        if not stacked:
            continue
        lines.append(f"  lookup Mkmk{label} {{")
        lines.append(f"    lookupflag UseMarkFilteringSet [{' '.join(sorted(stacked))}];")
        for name in sorted(stacked):
            x0, y0, x1, y1 = ink(font, name)
            lines.append(f"    pos mark {name} {anchor((x0 + x1) / 2, y1 if label == 'Above' else y0)} mark {cls};")
        lines.append(f"  }} Mkmk{label};")
    lines.append("} mkmk;")

    lines.append("table GDEF {")
    lines.append(f"  GlyphClassDef [{' '.join(sorted(set(latin_bases) | kana_bases))}], , "
                 f"[{' '.join(sorted(mark_names))}], ;")
    lines.append("} GDEF;")

    return {"marks": len(kinds), "bases": len(latin_bases) + len(kana_bases), "fea": "\n".join(lines) + "\n",
            "dotless_above": dotless_above, "fullwidth_dotless": fullwidth_dotless}


def cmap_code(cmap: dict, name: str) -> int:
    return next(code for code, glyph in cmap.items() if glyph == name)


def dotless_i(font: TTFont, above: list[str], fullwidth_dotless: str) -> int:
    """i (全角の ｉ も) の後に上の記号が続くときは、下の記号などを挟んでも点の無い字にする (ccmp)。GDEF を作った後に呼ぶ"""
    gsub = font["GSUB"].table
    cmap = font.getBestCmap()
    i, dotless = cmap[0x69], cmap.get(0x131)
    if dotless is None or not above:
        return 0
    mark_sets = font["GDEF"].table.MarkGlyphSetsDef
    mark_set_index = len(mark_sets.Coverage)
    mark_sets.Coverage.append(fraction_digits._coverage(font, above))
    mark_sets.MarkSetCount = len(mark_sets.Coverage)

    single = otTables.SingleSubst()
    fullwidth_i = cmap[FULLWIDTH_I]
    single.mapping = {i: dotless, fullwidth_i: fullwidth_dotless}
    nested = fraction_digits._lookup(gsub, 1, single)
    chain = otTables.ChainContextSubst()
    chain.Format = 3
    chain.BacktrackGlyphCount, chain.BacktrackCoverage = 0, []
    chain.InputGlyphCount, chain.InputCoverage = 1, [fraction_digits._coverage(font, [i, fullwidth_i])]
    chain.LookAheadGlyphCount, chain.LookAheadCoverage = 1, [fraction_digits._coverage(font, above)]
    record = otTables.SubstLookupRecord()
    record.SequenceIndex, record.LookupListIndex = 0, nested
    chain.SubstCount, chain.SubstLookupRecord = 1, [record]
    # 0x0010 は USE_MARK_FILTERING_SET: 下に付く記号などを飛ばして上の記号を見る
    index = fraction_digits._lookup(gsub, 6, chain, 0x0010, mark_set_index)
    records = [r for r in gsub.FeatureList.FeatureRecord if r.FeatureTag == "ccmp"]
    if not records:
        raise SystemExit("the font has no ccmp")
    for r in records:
        r.Feature.LookupListIndex = r.Feature.LookupListIndex + [index]
        r.Feature.LookupCount = len(r.Feature.LookupListIndex)
    return 1
