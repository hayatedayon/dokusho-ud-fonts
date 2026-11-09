"""欧文の中の記号を、BIZ UDP の字にする (GSUB の locl)。build.py が使う。

引用符・アポストロフィ・ダッシュなどの記号 (spec.LATIN_SYMBOL_RANGES) は、BIZ UD では和文に
合わせた幅 (‘ ’ “ ” は全角) を持つ。和文ではそれが正しいが、欧文の中では Alice’s の ’ の前後が
全角ぶん空く。文字の割り当て (cmap) は BIZ UD のままにし、BIZ UDP の字を別のグリフ
(<名前>.latn) として足して、欧字の用字系 (latn) の中でだけ置き換える。

- 記号には用字系が無く、文字を並べる仕組み (HarfBuzz など) は前後の字の用字系に入れるので、
  英語の文の中の記号は latn、和文の中の記号は hani・kana として並べられる
- 引用符とアポストロフィ、— − ¼ ½ ¾ ⅓ ⅔ ⅕ ° ‼ ⁇ ⁈ ⁉ (spec.ALWAYS_UDP) は、日本語の文書 (lang="ja") でも、
  和文の用字系 (kana・hani) などでも置き換える (いつも BIZ UDP の字)。和文の中に引いた英語 (画面に
  “Hello”と) では、開きの “ は前の和文と同じ組に入り、閉じの ” は英語に入る (Chromium で確かめた)。
  フォントは組の外の字を見られないので、“ の後ろが英語か和文かは分からない。どちらも BIZ UDP の
  字にして、左右をそろえる
- 記号だけの組 (用字系の決まらない DFLT。ブラウザは、行末に足すハイフン ‐ を 1 字で組む) も、
  欧字の用字系と同じにする。1.005 の前までは、英語の文の行末のハイフンが BIZ UD の全角の字だった
- latn と DFLT に日本語の言語体系 (JAN) を足し、そこには spec.ALWAYS_UDP の置き換えだけを入れる。
  ほかの記号は、日本語の文書では BIZ UD の字のまま
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
from fontTools.pens.transformPen import TransformPen
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


def append_feature_mapping(gsub, tag: str, mapping: dict[str, str]) -> None:
    """既存の tag のすべての FeatureRecord に、最後に適用する単置換を加える。"""
    if not mapping:
        return
    records = [record for record in gsub.FeatureList.FeatureRecord if record.FeatureTag == tag]
    if not records:
        raise SystemExit(f"cannot append substitutions: GSUB has no {tag} feature")
    index = single(gsub, mapping)
    for record in records:
        record.Feature.LookupListIndex = [*record.Feature.LookupListIndex, index]
        record.Feature.LookupCount = len(record.Feature.LookupListIndex)


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


def stylistic_vertical_forms(ud: TTFont, udp: TTFont, mapping: dict, sources: dict) -> dict:
    """横組では同じでも縦組候補が違う記号を、ss02 専用に用意する。通常の locl は変えない。"""
    import build

    cmap, cmap_udp = ud.getBestCmap(), udp.getBestCmap()
    forms = {tag: (build.single_mapping(ud["GSUB"].table, tag, set(cmap.values())),
                   build.single_mapping(udp["GSUB"].table, tag, set(cmap_udp.values())))
             for tag in ("vert", "vrt2")}
    extra, after = {}, {"vert": {}, "vrt2": {}}
    for code in spec.LATIN_SYMBOLS:
        if code not in cmap or code not in cmap_udp or code in spec.LATIN_QUOTES or unicodedata.category(chr(code)) == "Cf":
            continue
        base, source = cmap[code], cmap_udp[code]
        if base in mapping:
            continue
        for tag, (ours, reference) in forms.items():
            actual, wanted = ours.get(base, base), reference.get(source, source)
            if (ud["hmtx"][actual] == udp["hmtx"][wanted]
                    and ud["vmtx"][actual] == udp["vmtx"][wanted]
                    and drawing(ud.getGlyphSet(), actual) == drawing(udp.getGlyphSet(), wanted)):
                continue
            target = base + ".ss02." + tag
            if target in sources:
                if sources[target] != wanted:
                    raise SystemExit(f"{tag}: incompatible ss02 forms share {base}")
            else:
                add_glyph(ud, udp, wanted, target)
            sources[target] = wanted  # hinting.add が UDP の命令の CVT 番号を移す。
            extra[base] = base
            after[tag][base] = target
    return {"mapping": extra, "after": after}


def swap_vertical_quotes(ud: TTFont) -> None:
    """spec.VERTICAL_SWAPPED_QUOTES の元の vert・vrt2 を入れ替える。locl と ss01 はこの出力を引き継ぐ。

    輪郭を入れ替えるとヒンティングが字に合わなくなるので、置き換えの表だけを変える。vertical_forms の後に呼ぶ
    (locl の対応は、入れ替える前の字どうしで作る)。
    """
    import build

    gsub, cmap = ud["GSUB"].table, ud.getBestCmap()
    left, right = (cmap[code] for code in sorted(spec.VERTICAL_SWAPPED_QUOTES))
    indexes = {*build.feature_lookups(gsub, "vert"), *build.feature_lookups(gsub, "vrt2")}
    swapped = 0
    for index in sorted(indexes):
        for subtable in build.subtables(gsub, index, "mapping"):
            if left in subtable.mapping and right in subtable.mapping:
                subtable.mapping[left], subtable.mapping[right] = subtable.mapping[right], subtable.mapping[left]
                swapped += 1
    if not swapped:
        raise SystemExit("the vertical forms of the single quotes were not found")


def minute_glyph(ud: TTFont, source: str, single_stroke: bool):
    """縦組の 〝 〟 の字の複製。‘ ’ 用は 1 画だけを残し、2 画の中央へ移す (ヒンティングは持たない)"""
    glyph = copy.deepcopy(ud["glyf"][source])
    glyph.expand(ud["glyf"])
    if not single_stroke:
        return glyph
    if glyph.numberOfContours != 2:
        raise SystemExit(f"{source}: expected the two strokes of a double minute")
    pen = DecomposingRecordingPen(ud.getGlyphSet())
    ud.getGlyphSet()[source].draw(pen)
    strokes, current = [], None
    for operator, arguments in pen.value:
        if operator == "moveTo":
            current = []
            strokes.append(current)
        current.append((operator, arguments))
    xs = lambda stroke: [p[0] for _operator, arguments in stroke for p in arguments if p]
    pair = (min(map(min, map(xs, strokes))) + max(map(max, map(xs, strokes)))) / 2
    stroke = strokes[0]
    dx = round(pair - (min(xs(stroke)) + max(xs(stroke))) / 2)
    out = TTGlyphPen(None)
    for operator, arguments in stroke:
        getattr(out, operator)(*[(p[0] + dx, p[1]) if p else p for p in arguments])
    return out.glyph()


def vertical_minutes(ud: TTFont, mapping: dict, vertical: dict, after: dict) -> dict:
    """縦組の “ ” ‘ ’ をミニュートの形にする (spec.VERTICAL_MINUTES)。locl の後に足し、横組は変えない。
    用字系で形を変えるので、finish_vertical_quotes に渡す。

    〝 〟 自身と区別するため複製を使う (ss01 が元の引用符へ戻す入力になる)。返すのは 複製 → ss01 の出力 と、
    複製 → 詰めの量を引き継ぐ縦組の 〝 〟。
    """
    import build
    import fraction_digits

    gsub, cmap = ud["GSUB"].table, ud.getBestCmap()
    forms, restore, sources, quotes, sideways_names = {}, {}, {}, {}, {}
    for code, source_code in spec.VERTICAL_MINUTES.items():
        name = f"uni{code:04X}.minute"
        source = build.single_mapping(gsub, "vert", {cmap[source_code]})[cmap[source_code]]
        glyph = minute_glyph(ud, source, code in spec.VERTICAL_SWAPPED_QUOTES)
        fraction_digits._add_glyph(ud, name, glyph, ud["hmtx"][source][0], ud["vmtx"][source])
        forms[code], sources[name] = name, source
    for tag in ("vert", "vrt2"):
        final = {}
        for code, name in forms.items():
            base = cmap[code]
            ud_form = build.single_mapping(gsub, tag, {base}).get(base)
            if ud_form in vertical:  # ‘ ’: BIZ UD の縦組の字 → locl で BIZ UDP の縦組の字
                source = vertical[ud_form][1]
                restore[name] = ud_form
            else:  # “ ”: locl で BIZ UDP の横組の字 → その縦組の字
                source = after[tag][mapping[base]]
                restore[name] = base
            if code not in spec.VERTICAL_SWAPPED_QUOTES:  # “ ” は日本語に続く英語でも開きと閉じをそろえ、常にミニュート
                final[source] = name
                continue
            turned = build.single_mapping(gsub, "vrt2", {cmap[0x48]})[cmap[0x48]]
            if code not in sideways_names:
                glyph, advance, vmtx = sideways_quote(ud, mapping[base], cmap[0x48], turned)
                fraction_digits._add_glyph(ud, f"uni{code:04X}.sideways", glyph, advance, vmtx)
                sideways_names[code] = f"uni{code:04X}.sideways"
            quotes.setdefault(tag, {})[source] = (name, sideways_names[code])
        append_feature_mapping(gsub, tag, final)
    return {"restore": restore, "sources": sources, "quotes": quotes}


def sideways_quote(ud: TTFont, source: str, reference: str, turned: str):
    """横組の字を、vrt2 の欧字 (reference → turned) と同じ変換で右へ 90 度回した字と、その縦の字送りの情報"""
    glyf, glyphs = ud["glyf"], ud.getGlyphSet()
    plain, target = glyf[reference], glyf[turned]
    dx, dy = target.xMin - plain.yMin, target.yMax + plain.xMin
    pen = TTGlyphPen(None)
    glyphs[source].draw(TransformPen(pen, (0, -1, 1, 0, dx, dy)))
    glyph = pen.glyph()
    glyph.recalcBounds(glyf)
    origin = ud["vmtx"][turned][1] + target.yMax
    return glyph, ud["hmtx"][turned][0], (ud["hmtx"][source][0], origin - glyph.yMax)


def finish_vertical_quotes(font: TTFont, quotes: dict) -> None:
    """縦組の ‘ ’ を用字系で分ける。欧字の組 (英語の It’s など) では横倒し、ほかではミニュートの形。

    ブラウザは引用符を前の字の用字系で組むが、前後の字とは別の組にするので、前後の字では区別できない。すべての lookup を
    足し終えてから呼ぶ (ss01 は先に元の字へ戻している)。
    """
    gsub = font["GSUB"].table
    for tag, forms in quotes.items():
        minute = single(gsub, {source: name for source, (name, _sideways) in forms.items()})
        sideways = single(gsub, {source: turned for source, (_name, turned) in forms.items()})
        records = gsub.FeatureList.FeatureRecord
        latin = next(r.Script for r in gsub.ScriptList.ScriptRecord if r.ScriptTag == "latn")
        clones: dict[int, int] = {}
        for system in filter(None, [latin.DefaultLangSys, *(r.LangSys for r in latin.LangSysRecord)]):
            for position, index in enumerate(system.FeatureIndex):
                if records[index].FeatureTag != tag:
                    continue
                if index not in clones:
                    feature = otTables.Feature()
                    feature.FeatureParams = records[index].Feature.FeatureParams
                    feature.LookupListIndex = [*records[index].Feature.LookupListIndex, sideways]
                    feature.LookupCount = len(feature.LookupListIndex)
                    record = otTables.FeatureRecord()
                    record.FeatureTag, record.Feature = tag, feature
                    records.append(record)
                    clones[index] = len(records) - 1
                system.FeatureIndex[position] = clones[index]
        gsub.FeatureList.FeatureCount = len(records)
        for record in records:
            if record.FeatureTag == tag and sideways not in record.Feature.LookupListIndex:
                record.Feature.LookupListIndex = [*record.Feature.LookupListIndex, minute]
                record.Feature.LookupCount = len(record.Feature.LookupListIndex)


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

    # 日本語 (JAN) と、欧字のほかの用字系は、spec.ALWAYS_UDP だけを置き換える locl
    cmap = ud.getBestCmap()
    always_names = {cmap[code] for code in spec.ALWAYS_UDP}
    always = {name: mapping[name] for name in always_names}
    always.update({key: value for key, (name, value) in vertical.items() if name in always_names})
    japanese_feature = new_feature(gsub, [single(gsub, always)])
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
        append_feature_mapping(gsub, tag, forms)

    # spec.ALWAYS_UDP は、ほかの用字系 (和文・ギリシャ文字・キリル文字と、記号だけの DFLT) でも
    # 置き換える。和文の後の “Hello の “ は、前の和文と同じ組に入る
    for script in gsub.ScriptList.ScriptRecord:
        if script.ScriptTag == "latn":
            continue
        if script.Script.LangSysRecord:
            raise SystemExit(f"the {script.ScriptTag} script of BIZ UD has language systems")
        system = script.Script.DefaultLangSys
        if script.ScriptTag == "DFLT":
            # 記号だけの組 (ブラウザが行末に足すハイフン ‐ など、記号を 1 字で組むとき) は、欧字の
            # 用字系と同じにする。日本語の文書 (JAN) では、spec.ALWAYS_UDP だけ
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
    stylistic = stylistic_vertical_forms(ud, udp, mapping, sources)
    swap_vertical_quotes(ud)
    minutes = vertical_minutes(ud, mapping, vertical, after)
    # glyphs は、足した字 → BIZ UDP の元の字 (hinting.py が、その字の命令を入れる)
    return {"symbols": len(chosen), "glyphs": sources, "vertical": len(vertical) + sum(map(len, after.values())),
            "shared": shared, "mapping": mapping, "vertical_mapping": vertical, "after": after,
            "stylistic": stylistic, "minutes": minutes}
