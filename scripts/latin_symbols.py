"""欧文の中の記号を、BIZ UDP の字にする (GSUB の locl)。build.py が使う。

引用符・アポストロフィ・ダッシュなどの記号 (spec.LATIN_SYMBOL_RANGES) は、BIZ UD では和文に
合わせた幅 (‘ ’ “ ” は全角) を持つ。和文ではそれが正しいが、欧文の中では Alice’s の ’ の前後が
全角ぶん空く。文字の割り当て (cmap) は BIZ UD のままにし、BIZ UDP の字を別のグリフ
(<名前>.latn) として足して、欧字の用字系 (latn) の中でだけ置き換える。

- 記号には用字系が無く、文字を並べる仕組み (HarfBuzz など) は前後の字の用字系に入れるので、
  英語の文の中の記号は latn、和文の中の記号は hani・kana として並べられる
- 引用符とアポストロフィ (spec.LATIN_QUOTES) は、日本語の文書 (lang="ja") でも、和文の用字系
  (kana・hani) などでも置き換える (横組では、いつも BIZ UDP の字)。和文の中に引いた英語 (画面に
  “Hello”と) では、開きの “ は前の和文と同じ組に入り、閉じの ” は英語に入る (Chromium で確かめた)。
  フォントは組の外の字を見られないので、“ の後ろが英語か和文かは分からない。どちらも BIZ UDP の
  字にして、左右をそろえる
- 記号だけの組 (用字系の決まらない DFLT。ブラウザは、行末に足すハイフン ‐ を 1 字で組む) も、
  欧字の用字系と同じにする。1.005 の前までは、英語の文の行末のハイフンが BIZ UD の全角の字だった
- latn と DFLT に日本語の言語体系 (JAN) を足し、そこには引用符とアポストロフィの置き換えだけを入れる。
  ダッシュ・三点リーダーなどは、日本語の本の使い方 (OK―― など) があるので、日本語の文書では
  BIZ UD の記号のまま
- 選ぶのは、BIZ UD と BIZ UDP で形か幅が違う記号だけ。同じものは置き換えない
- 縦組でも、置き換える所では BIZ UDP の縦組の字にする (vertical_forms。Chromium は、縦組の引用符を
  正立させ、縦組の字で組む。BIZ UDP の縦組の引用符は、字送りが半角)
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


def single(gsub, mapping: dict) -> int:
    """1 対 1 の置き換えの lookup を足して、その番号を返す"""
    subtable = otTables.SingleSubst()
    subtable.mapping = mapping
    lookup = otTables.Lookup()
    lookup.LookupType, lookup.LookupFlag, lookup.SubTable, lookup.SubTableCount = 1, 0, [subtable], 1
    gsub.LookupList.Lookup.append(lookup)
    gsub.LookupList.LookupCount = len(gsub.LookupList.Lookup)
    return len(gsub.LookupList.Lookup) - 1


def new_feature(gsub, lookups: list[int]) -> int:
    """lookups を持つ locl の機能を足して、その番号を返す (どの言語体系に入れるかは呼ぶ側が決める)"""
    feature = otTables.Feature()
    feature.FeatureParams, feature.LookupListIndex, feature.LookupCount = None, lookups, len(lookups)
    record = otTables.FeatureRecord()
    record.FeatureTag, record.Feature = FEATURE, feature
    gsub.FeatureList.FeatureRecord.append(record)
    gsub.FeatureList.FeatureCount = len(gsub.FeatureList.FeatureRecord)
    return len(gsub.FeatureList.FeatureRecord) - 1


def vertical_forms(ud: TTFont, udp: TTFont, chosen, mapping: dict, sources: dict):
    """縦組の字を、横組と同じく BIZ UDP のものにする。BIZ UDP の縦組の字 (vert・vrt2 の置き換え先) を
    <名前>.latn.vert・.latn.vrt2 として足す (BIZ UDP に縦組の字が無ければ、横組の字のまま正立させる)。

    文字を並べる仕組みは lookup を番号の順にかけ、縦組の字への置き換え (BIZ UD の vert・vrt2) は locl より
    先にかかる。そこで
    - BIZ UD に縦組の字がある記号 (‘ ’ など) は、locl で、その BIZ UD の縦組の字を BIZ UDP の縦組の字に
      する (返す vertical: BIZ UD の縦組の字 → (元の字, BIZ UDP の縦組の字))
    - 無い記号 (“ ” × など) は、locl が BIZ UDP の横組の字にした後で、vert・vrt2 に足す lookup で BIZ UDP の
      縦組の字にする (返す after: {機能: {横組の字: 縦組の字}})
    BIZ UD の vert と vrt2 が同じ字で、BIZ UDP では違う字になる記号 (‐) は、vert のほうにする (返す shared)"""
    import build

    gsub_ud, gsub_udp = ud["GSUB"].table, udp["GSUB"].table
    names = {name for _code, name, _name_udp in chosen}
    vertical, after, shared = {}, {"vert": {}, "vrt2": {}}, []
    for tag in ("vert", "vrt2"):
        ud_forms = build.single_mapping(gsub_ud, tag, set(ud.getGlyphOrder()))
        users: dict[str, set[str]] = {}
        for key, value in ud_forms.items():
            users.setdefault(value, set()).add(key)
        for _code, name, name_udp in chosen:
            form_udp = build.single_mapping(gsub_udp, tag, {name_udp}).get(name_udp)
            # BIZ UDP に縦組の字が無ければ、横組の字のまま正立させる
            target = mapping[name] if form_udp is None else f"{name}{SUFFIX}.{tag}"

            def take() -> None:
                if target != mapping[name] and target not in ud["hmtx"].metrics:
                    add_glyph(ud, udp, form_udp, target)
                    sources[target] = form_udp

            form_ud = ud_forms.get(name)
            if form_ud is None:
                if target != mapping[name]:
                    take()
                    after[tag][mapping[name]] = target
                continue
            if users[form_ud] - names:
                raise SystemExit(f"{tag} of {name} in BIZ UD is shared with {sorted(users[form_ud] - names)}")
            if form_ud in vertical:
                # BIZ UD の vert と vrt2 が同じ字で、BIZ UDP では違う字 (‐)。locl からはどちらで置き換えた
                # 字か分からないので、ブラウザなどがかける vert のほうにする
                shared.append(name)
                continue
            take()
            vertical[form_ud] = (name, target)
    return vertical, after, shared


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
    vertical, after, shared = vertical_forms(ud, udp, chosen, mapping, sources)

    # 置き換えの lookup (1 対 1) と、それだけを持つ locl の機能
    subtable = otTables.SingleSubst()
    subtable.mapping = {**mapping, **{key: value for key, (_name, value) in vertical.items()}}
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

    # 日本語 (JAN) と、欧字のほかの用字系は、引用符とアポストロフィだけを置き換える locl
    cmap = ud.getBestCmap()
    quote_names = {cmap[code] for code in spec.LATIN_QUOTES}
    quotes = {cmap[code]: mapping[cmap[code]] for code in spec.LATIN_QUOTES}
    quotes.update({key: value for key, (name, value) in vertical.items() if name in quote_names})
    japanese_feature = new_feature(gsub, [single(gsub, quotes)])
    japanese = otTables.LangSys()
    japanese.LookupOrder, japanese.ReqFeatureIndex = None, latn.DefaultLangSys.ReqFeatureIndex
    japanese.FeatureIndex = list(latn.DefaultLangSys.FeatureIndex) + [japanese_feature]
    japanese.FeatureCount = len(japanese.FeatureIndex)
    system = otTables.LangSysRecord()
    system.LangSysTag, system.LangSys = "JAN ", japanese
    latn.LangSysRecord = [system]
    latn.LangSysCount = 1
    latn.DefaultLangSys.FeatureIndex = latn.DefaultLangSys.FeatureIndex + [new]
    latn.DefaultLangSys.FeatureCount = len(latn.DefaultLangSys.FeatureIndex)

    # BIZ UD に縦組の字が無い記号 (“ ” × など) は、locl が BIZ UDP の横組の字にした後で、BIZ UDP の
    # 縦組の字にする。lookup は番号の順にかかるので、locl より後の番号で vert・vrt2 に足す
    for tag, forms in after.items():
        if not forms:
            continue
        index = single(gsub, forms)
        for record in gsub.FeatureList.FeatureRecord:
            if record.FeatureTag == tag:
                record.Feature.LookupListIndex = record.Feature.LookupListIndex + [index]
                record.Feature.LookupCount = len(record.Feature.LookupListIndex)

    # 引用符とアポストロフィは、ほかの用字系 (和文・ギリシャ文字・キリル文字と、記号だけの DFLT) でも
    # 置き換える。和文の後の “Hello の “ は、前の和文と同じ組に入る
    for script in gsub.ScriptList.ScriptRecord:
        if script.ScriptTag == "latn":
            continue
        if script.Script.LangSysRecord:
            raise SystemExit(f"the {script.ScriptTag} script of BIZ UD has language systems")
        system = script.Script.DefaultLangSys
        if script.ScriptTag == "DFLT":
            # 記号だけの組 (ブラウザが行末に足すハイフン ‐ など、記号を 1 字で組むとき) は、欧字の
            # 用字系と同じにする。日本語の文書 (JAN) では、引用符とアポストロフィだけ
            dflt_japanese = otTables.LangSys()
            dflt_japanese.LookupOrder, dflt_japanese.ReqFeatureIndex = None, system.ReqFeatureIndex
            dflt_japanese.FeatureIndex = list(system.FeatureIndex) + [japanese_feature]
            dflt_japanese.FeatureCount = len(dflt_japanese.FeatureIndex)
            record = otTables.LangSysRecord()
            record.LangSysTag, record.LangSys = "JAN ", dflt_japanese
            script.Script.LangSysRecord, script.Script.LangSysCount = [record], 1
            system.FeatureIndex = system.FeatureIndex + [new]
        else:
            system.FeatureIndex = system.FeatureIndex + [japanese_feature]
        system.FeatureCount = len(system.FeatureIndex)
    sort_features(gsub)
    # glyphs は、足した字 → BIZ UDP の元の字 (hinting.py が、その字の命令を入れる)
    return {"symbols": len(chosen), "glyphs": sources, "vertical": len(vertical) + sum(map(len, after.values())),
            "shared": shared}
