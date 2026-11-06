"""欧文の中の記号を、BIZ UDP の字にする (GSUB の locl)。build.py が使う。

引用符・アポストロフィ・ダッシュなどの記号 (spec.LATIN_SYMBOL_RANGES) は、BIZ UD では和文に
合わせた幅 (‘ ’ “ ” は全角) を持つ。和文ではそれが正しいが、欧文の中では Alice’s の ’ の前後が
全角ぶん空く。文字の割り当て (cmap) は BIZ UD のままにし、BIZ UDP の字を別のグリフ
(<名前>.latn) として足して、欧字の用字系 (latn) の中でだけ置き換える。

- 記号には用字系が無く、文字を並べる仕組み (HarfBuzz など) は前後の字の用字系に入れるので、
  英語の文の中の記号は latn、和文の中の記号は hani・kana として並べられる
- ただし、和文の中に引いた英語 (彼は“Hello”と) では、開きの “ は和文、閉じの ” は英語に入り、
  左右がそろわない。日本語の文書 (lang="ja") では置き換えない。latn に日本語の言語体系 (JAN)
  を足し、そこには置き換えを入れない。日本語の本の中の英語は、これまでどおり BIZ UD の記号になる
- 選ぶのは、BIZ UD と BIZ UDP で形か幅が違う記号だけ。同じものは置き換えない
- 書式の文字 (一般カテゴリ Cf。ソフトハイフン U+00AD など) は置き換えない。HarfBuzz は、普段は
  見えないこれらの文字を幅 0 にして隠すが、フォントが GSUB で置き換えた字は隠さない (1.003 から
  1.004 まで、英語の文の中のソフトハイフンが、幅のある字として出ていた)
"""

import copy
import unicodedata

from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables

import spec

SUFFIX = ".latn"
FEATURE = "locl"


def symbols(ud: TTFont, udp: TTFont) -> list[tuple[int, str, str]]:
    """置き換える記号 (コードポイント, BIZ UD のグリフ名, BIZ UDP のグリフ名)。BIZ UD と BIZ UDP で
    形か幅が違うもの"""
    cmap_ud, cmap_udp = ud.getBestCmap(), udp.getBestCmap()
    glyphs_ud, glyphs_udp = ud.getGlyphSet(), udp.getGlyphSet()
    chosen = []
    for code in spec.LATIN_SYMBOLS:
        name, name_udp = cmap_ud.get(code), cmap_udp.get(code)
        if name is None or name_udp is None or unicodedata.category(chr(code)) == "Cf":
            continue
        if ud["hmtx"][name] == udp["hmtx"][name_udp] and drawing(glyphs_ud, name) == drawing(glyphs_udp, name_udp):
            continue
        chosen.append((code, name, name_udp))
    return chosen


def drawing(glyph_set, name: str) -> list:
    pen = DecomposingRecordingPen(glyph_set)
    glyph_set[name].draw(pen)
    return pen.value


def add_glyph(ud: TTFont, udp: TTFont, source: str, name: str) -> None:
    """BIZ UDP の source の字 (形・字幅・縦の字送り) を、ud に name として足す。部品でできた字は
    分解する。そうでない字は点の並びをそのまま写す (hinting.py が、BIZ UDP の命令を点の番号の
    まま入れる)。ヒンティングの命令はいったん外す (BIZ UD と BIZ UDP は cvt が違う)"""
    original = udp["glyf"][source]
    if original.isComposite():
        recording = DecomposingRecordingPen(udp.getGlyphSet())
        udp.getGlyphSet()[source].draw(recording)
        pen = TTGlyphPen(None)
        recording.replay(pen)
        glyph = pen.glyph()
    else:
        glyph = copy.deepcopy(original)
        glyph.expand(udp["glyf"])
        glyph.removeHinting()
    order = ud.getGlyphOrder() + [name]
    ud.setGlyphOrder(order)
    ud["glyf"].glyphOrder = order
    ud["glyf"][name] = glyph
    ud["hmtx"][name] = udp["hmtx"][source]
    ud["vmtx"][name] = udp["vmtx"][source]


def sort_features(gsub) -> None:
    """FeatureRecord をタグの順に並べ直し (OpenType の決まり)、LangSys の番号を付け直す"""
    records = gsub.FeatureList.FeatureRecord
    order = sorted(range(len(records)), key=lambda i: records[i].FeatureTag)
    new_index = {old: new for new, old in enumerate(order)}
    gsub.FeatureList.FeatureRecord = [records[i] for i in order]
    for script in gsub.ScriptList.ScriptRecord:
        systems = [script.Script.DefaultLangSys] + [r.LangSys for r in script.Script.LangSysRecord]
        for system in filter(None, systems):
            system.FeatureIndex = sorted(new_index[i] for i in system.FeatureIndex)
            if system.ReqFeatureIndex != 0xFFFF:
                system.ReqFeatureIndex = new_index[system.ReqFeatureIndex]


def add(ud: TTFont, udp: TTFont) -> dict[str, int]:
    gsub = ud["GSUB"].table
    latn = next((r.Script for r in gsub.ScriptList.ScriptRecord if r.ScriptTag == "latn"), None)
    if latn is None or latn.DefaultLangSys is None:
        raise SystemExit("BIZ UD has no latn script in GSUB")
    if latn.LangSysRecord:
        raise SystemExit("the latn script of BIZ UD already has language systems; merge JAN into them")
    if any(gsub.FeatureList.FeatureRecord[i].FeatureTag == FEATURE for i in latn.DefaultLangSys.FeatureIndex):
        raise SystemExit(f"the latn script of BIZ UD already has {FEATURE}")

    chosen = symbols(ud, udp)
    mapping, sources = {}, {}
    for _code, name, name_udp in chosen:
        target = name + SUFFIX
        add_glyph(ud, udp, name_udp, target)
        mapping[name] = target
        sources[target] = name_udp

    # 置き換えの lookup (1 対 1) と、それだけを持つ locl の機能
    subtable = otTables.SingleSubst()
    subtable.mapping = mapping
    lookup = otTables.Lookup()
    lookup.LookupType, lookup.LookupFlag, lookup.SubTable = 1, 0, [subtable]
    lookup.SubTableCount = 1
    gsub.LookupList.Lookup.append(lookup)
    gsub.LookupList.LookupCount = len(gsub.LookupList.Lookup)
    feature = otTables.Feature()
    feature.FeatureParams, feature.LookupListIndex = None, [len(gsub.LookupList.Lookup) - 1]
    feature.LookupCount = 1
    record = otTables.FeatureRecord()
    record.FeatureTag, record.Feature = FEATURE, feature
    gsub.FeatureList.FeatureRecord.append(record)
    gsub.FeatureList.FeatureCount = len(gsub.FeatureList.FeatureRecord)
    new = len(gsub.FeatureList.FeatureRecord) - 1

    # 日本語 (JAN) は、置き換えの無い今の機能のまま。欧字の既定 (dflt) にだけ locl を足す
    japanese = otTables.LangSys()
    japanese.LookupOrder, japanese.ReqFeatureIndex = None, latn.DefaultLangSys.ReqFeatureIndex
    japanese.FeatureIndex = list(latn.DefaultLangSys.FeatureIndex)
    japanese.FeatureCount = len(japanese.FeatureIndex)
    system = otTables.LangSysRecord()
    system.LangSysTag, system.LangSys = "JAN ", japanese
    latn.LangSysRecord = [system]
    latn.LangSysCount = 1
    latn.DefaultLangSys.FeatureIndex = latn.DefaultLangSys.FeatureIndex + [new]
    latn.DefaultLangSys.FeatureCount = len(latn.DefaultLangSys.FeatureIndex)
    sort_features(gsub)
    # glyphs は、足した字 → BIZ UDP の元の字 (hinting.py が、その字の命令を入れる)
    return {"symbols": len(chosen), "glyphs": sources}
