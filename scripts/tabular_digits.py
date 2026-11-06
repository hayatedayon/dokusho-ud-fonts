"""等幅の数字 (tnum) と、数字の間のコロンを作る。build.py が使う。

BIZ UDP の数字は、1 だけがほかの数字より狭い (明朝 Regular では 1065、ほかは 1393)。表や目次の
ページ番号で桁がそろうように、1 の左右に同じだけ空きを足して、ほかの数字と同じ字幅にした字
(one.tnum) を足し、tnum でそれにする。形とヒンティングは 1 のまま (横にずらすだけ)。プロポーショナル
の数字 (pnum) は、今の数字のままなので足さない。

BIZ UDP のコロンは、欧文の文章用に、ベースラインから x の高さまでの所にある。数字は x の高さより高い
ので、11:11 や 0213:2004 では、コロンが数字の真ん中より下に見える (BIZ UD の半角のコロンは、数字の
真ん中にある)。前後が数字のときだけ、数字の真ん中まで持ち上げたコロン (colon.num) にする (calt。
ブラウザは既定でかける)。和文の後のコロン (時刻: など。和文の用字系の組に入る) も、漢字の横で低く
見えないように持ち上げる。Note: のように欧文の語の後のコロンは、そのまま。作った字にはヒンティングを付けない
(BIZ UDP の命令は、点をベースラインと x の高さに合わせて戻す)。縦組では、元のコロンに戻す (vert・vrt2。
縦組の数字の間で、コロンが上の字に寄らないように)
"""

import copy

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables

import fraction_digits
import latin_symbols

SUFFIX = ".tnum"
COLON_SUFFIX = ".num"


def add(font: TTFont) -> dict[str, int]:
    cmap = font.getBestCmap()
    digits = [cmap[0x30 + d] for d in range(10)]
    widths = {font["hmtx"][name][0] for name in digits}
    width = font["hmtx"][digits[0]][0]
    narrow = [name for name in digits if font["hmtx"][name][0] != width]
    if len(widths) > 2 or any(font["hmtx"][name][0] > width for name in digits):
        raise SystemExit(f"the digits have unexpected widths: {sorted(widths)}")
    gsub = font["GSUB"].table
    if any(r.FeatureTag == "tnum" for r in gsub.FeatureList.FeatureRecord):
        raise SystemExit("the font already has tnum")

    mapping = {}
    for name in narrow:
        glyph = copy.deepcopy(font["glyf"][name])
        glyph.expand(font["glyf"])
        if glyph.isComposite():
            raise SystemExit(f"{name} is a composite glyph")
        advance, _side = font["hmtx"][name]
        dx = (width - advance) // 2
        glyph.coordinates.translate((dx, 0))
        new = name + SUFFIX
        fraction_digits._add_glyph(font, new, glyph, width, font["vmtx"][name])
        mapping[name] = new

    subtable = otTables.SingleSubst()
    subtable.mapping = mapping
    fraction_digits._new_feature(gsub, "tnum", fraction_digits._lookup(gsub, 1, subtable))
    latin_symbols.sort_features(gsub)
    return {"tabular": len(mapping), "width": width}


def ink(font: TTFont, name: str):
    from fontTools.pens.boundsPen import BoundsPen
    glyph_set = font.getGlyphSet()
    pen = BoundsPen(glyph_set)
    glyph_set[name].draw(pen)
    return pen.bounds


def raise_colon(font: TTFont) -> dict[str, int]:
    """数字の間のコロンを、数字の真ん中まで持ち上げる (calt)。持ち上げた量を返す"""
    import build
    from statistics import median

    cmap = font.getBestCmap()
    gsub = font["GSUB"].table
    if any(r.FeatureTag == "calt" for r in gsub.FeatureList.FeatureRecord):
        raise SystemExit("the font already has calt")
    colon = cmap[0x3A]
    digits = [cmap[0x30 + d] for d in range(10)]
    # tnum の 1 と、斜線の 0 (zero) の後でも
    digits += [build.single_mapping(gsub, tag, set(digits)).get(d) for tag in ("tnum", "zero") for d in digits]
    digits = sorted({d for d in digits if d}, key=font.getGlyphID)
    middle = median((ink(font, d)[1] + ink(font, d)[3]) / 2 for d in digits)
    _x0, y0, _x1, y1 = ink(font, colon)
    dy = round(middle - (y0 + y1) / 2)

    glyph = copy.deepcopy(font["glyf"][colon])
    glyph.expand(font["glyf"])
    if glyph.isComposite():
        raise SystemExit("the colon is a composite glyph")
    glyph.coordinates.translate((0, dy))
    glyph.removeHinting()
    raised = colon + COLON_SUFFIX
    advance, _side = font["hmtx"][colon]
    fraction_digits._add_glyph(font, raised, glyph, advance, font["vmtx"][colon])

    single = otTables.SingleSubst()
    single.mapping = {colon: raised}
    nested = fraction_digits._lookup(gsub, 1, single)
    chain = otTables.ChainContextSubst()
    chain.Format = 3
    chain.BacktrackGlyphCount, chain.BacktrackCoverage = 1, [fraction_digits._coverage(font, digits)]
    chain.InputGlyphCount, chain.InputCoverage = 1, [fraction_digits._coverage(font, [colon])]
    chain.LookAheadGlyphCount, chain.LookAheadCoverage = 1, [fraction_digits._coverage(font, digits)]
    record = otTables.SubstLookupRecord()
    record.SequenceIndex, record.LookupListIndex = 0, nested
    chain.SubstCount, chain.SubstLookupRecord = 1, [record]
    between = fraction_digits._lookup(gsub, 6, chain)
    fraction_digits._new_feature(gsub, "calt", between)

    # 和文の後のコロン (時刻: など) も持ち上げる。ブラウザは和文の後の記号を和文の組 (kana・hani) に入れる。
    # 文字を並べる仕組みは、1 つの言語体系で同じタグの機能を 1 つしか使わないので、和文の用字系の calt は、
    # 数字の間の lookup と合わせた別の機能にする
    japanese = otTables.SingleSubst()
    japanese.mapping = {colon: raised}
    feature = otTables.Feature()
    feature.FeatureParams = None
    feature.LookupListIndex = [between, fraction_digits._lookup(gsub, 1, japanese)]
    feature.LookupCount = 2
    record = otTables.FeatureRecord()
    record.FeatureTag, record.Feature = "calt", feature
    gsub.FeatureList.FeatureRecord.append(record)
    gsub.FeatureList.FeatureCount = len(gsub.FeatureList.FeatureRecord)
    common = next(i for i, r in enumerate(gsub.FeatureList.FeatureRecord)
                  if r.FeatureTag == "calt" and r.Feature.LookupListIndex == [between])
    for script in gsub.ScriptList.ScriptRecord:
        if script.ScriptTag in ("kana", "hani"):
            system = script.Script.DefaultLangSys
            system.FeatureIndex = [i for i in system.FeatureIndex if i != common] + \
                [len(gsub.FeatureList.FeatureRecord) - 1]
            system.FeatureCount = len(system.FeatureIndex)

    # 縦組では元のコロンに戻す。lookup は番号の順にかかるので、calt より後の番号で vert・vrt2 に足す
    back = otTables.SingleSubst()
    back.mapping = {raised: colon}
    index = fraction_digits._lookup(gsub, 1, back)
    for record in gsub.FeatureList.FeatureRecord:
        if record.FeatureTag in ("vert", "vrt2"):
            record.Feature.LookupListIndex = record.Feature.LookupListIndex + [index]
            record.Feature.LookupCount = len(record.Feature.LookupListIndex)
    latin_symbols.sort_features(gsub)
    return {"raise": dy}
