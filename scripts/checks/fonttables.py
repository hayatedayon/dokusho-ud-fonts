"""フォントの表 (cmap・GSUB・GPOS) と輪郭を読む補助。検査の対象に依らない。"""

import unicodedata

from fontTools.ttLib import TTFont

import spec


def singles(subtable) -> dict:
    """1 対 1 の置き換え (GSUB の型 1) の {字: 置き換え先}。複数の字への置き換え (型 2) は含めない"""
    return {} if type(subtable).__name__ == "MultipleSubst" else getattr(subtable, "mapping", {})


def multiples(subtable) -> dict:
    """複数の字への置き換え (GSUB の型 2) の {字: [置き換え先の字, ...]}"""
    return getattr(subtable, "mapping", {}) if type(subtable).__name__ == "MultipleSubst" else {}


def gsub_multiple(font: TTFont, tag: str) -> dict:
    """tag の複数の字への置き換え (型 2) の {字: [置き換え先の字, ...]}。先の lookup のものを取る"""
    gsub = font["GSUB"].table
    result: dict = {}
    for record in gsub.FeatureList.FeatureRecord:
        if record.FeatureTag != tag:
            continue
        for index in record.Feature.LookupListIndex:
            for subtable in gsub.LookupList.Lookup[index].SubTable:
                for key, value in multiples(getattr(subtable, "ExtSubTable", subtable)).items():
                    result.setdefault(key, list(value))
    return result


def outline(font: TTFont, name: str):
    coordinates, ends, flags = font["glyf"][name].getCoordinates(font["glyf"])
    return list(coordinates), list(ends), list(flags)


def gsub_mapping(font: TTFont, tag: str) -> dict:
    gsub = font["GSUB"].table
    mapping = {}
    for record in gsub.FeatureList.FeatureRecord:
        if record.FeatureTag != tag:
            continue
        for index in record.Feature.LookupListIndex:
            for subtable in gsub.LookupList.Lookup[index].SubTable:
                subtable = getattr(subtable, "ExtSubTable", subtable)
                for key, value in singles(subtable).items():
                    mapping.setdefault(key, value)  # 先の lookup のものを取る
    return mapping


def gsub_alternates(font: TTFont, tag: str) -> dict:
    """{字: [候補, ...]}。1 対 1 の置き換えも候補 1 つとして数える"""
    gsub = font["GSUB"].table
    result: dict = {}
    for record in gsub.FeatureList.FeatureRecord:
        if record.FeatureTag != tag:
            continue
        for index in record.Feature.LookupListIndex:
            for subtable in gsub.LookupList.Lookup[index].SubTable:
                subtable = getattr(subtable, "ExtSubTable", subtable)
                # aalt の機能は用字系ごとにあり、同じ lookup を指すので、同じ候補は 1 つにする
                for key, value in singles(subtable).items():
                    if value not in result.setdefault(key, []):
                        result[key].append(value)
                for key, values in getattr(subtable, "alternates", {}).items():
                    result.setdefault(key, []).extend(v for v in values if v not in result[key])
    return result


def vertical_closure(font: TTFont, glyphs: set[str]) -> set[str]:
    """横・縦組の候補を集める。post が形式3でもグリフ名の接尾辞には依存しない。"""
    result = set(glyphs)
    forms = [gsub_mapping(font, tag) for tag in ("vert", "vrt2")]
    while True:
        expanded = result | {target for mapping in forms for source, target in mapping.items() if source in result}
        if expanded == result:
            return result
        result = expanded


def latin_codes(cmap: dict) -> list[int]:
    """spec.LATIN のうち、フォントにある字 (範囲には BIZ UD・BIZ UDP のどちらにも無い字もある)"""
    return [code for code in spec.LATIN if code in cmap]


def gsub_ligatures(font: TTFont, tag: str) -> dict:
    """{最初の字: [(つなぐ字, 置き換え先), ...]}"""
    gsub = font["GSUB"].table
    ligatures = {}
    for record in gsub.FeatureList.FeatureRecord:
        if record.FeatureTag != tag:
            continue
        for index in record.Feature.LookupListIndex:
            for subtable in gsub.LookupList.Lookup[index].SubTable:
                subtable = getattr(subtable, "ExtSubTable", subtable)
                for first, items in getattr(subtable, "ligatures", {}).items():
                    ligatures[first] = [(tuple(item.Component), item.LigGlyph) for item in items]
    return ligatures


def latin_targets(font: TTFont, latin_glyphs: set[str]) -> dict[str, str]:
    """欧字からの置き換え先と合字 ({グリフ名: どの機能か})。BIZ UDP と同じ名前の、BIZ UDP の字"""
    targets = {}
    for tag in spec.LATIN_FEATURES:
        targets.update({v: tag for k, v in gsub_mapping(font, tag).items() if k in latin_glyphs})
    for tag in spec.LATIN_LIGATURE_FEATURES:
        for first, items in gsub_ligatures(font, tag).items():
            if first in latin_glyphs:
                targets.update({target: tag for _, target in items})
    return targets


def gpos_values(font: TTFont, tag: str) -> dict:
    """GPOS の tag の、グリフごとの (XPlacement, YPlacement, XAdvance, YAdvance)"""
    gpos = font["GPOS"].table
    values = {}
    for record in gpos.FeatureList.FeatureRecord:
        if record.FeatureTag != tag:
            continue
        for index in record.Feature.LookupListIndex:
            for subtable in gpos.LookupList.Lookup[index].SubTable:
                subtable = getattr(subtable, "ExtSubTable", subtable)
                glyphs = subtable.Coverage.glyphs
                records = [subtable.Value] * len(glyphs) if subtable.Format == 1 else subtable.Value
                for glyph, record in zip(glyphs, records):
                    values[glyph] = tuple(getattr(record, a, 0) or 0
                                          for a in ("XPlacement", "YPlacement", "XAdvance", "YAdvance"))
    return values


def lang_system(font: TTFont, script: str, language: str | None):
    gsub = font["GSUB"].table
    record = next((r for r in gsub.ScriptList.ScriptRecord if r.ScriptTag == script), None)
    if record is None:
        return None
    if language is None:
        return record.Script.DefaultLangSys
    return next((r.LangSys for r in record.Script.LangSysRecord if r.LangSysTag == language), None)


def latin_symbol_mapping(font: TTFont, script: str, language: str | None, vertical: bool = False) -> dict:
    """その用字系・言語体系で働く locl の置き換え。vertical が False なら、文字に割り当てた字 (横組の字)
    からの置き換えだけ (locl は、BIZ UD の縦組の字を BIZ UDP の縦組の字にする置き換えも持つ)"""
    gsub = font["GSUB"].table
    system = lang_system(font, script, language)
    mapping: dict = {}
    if system is None:
        return mapping
    for index in system.FeatureIndex:
        record = gsub.FeatureList.FeatureRecord[index]
        if record.FeatureTag != "locl":
            continue
        for lookup_index in record.Feature.LookupListIndex:
            for subtable in gsub.LookupList.Lookup[lookup_index].SubTable:
                subtable = getattr(subtable, "ExtSubTable", subtable)
                for key, value in singles(subtable).items():
                    mapping.setdefault(key, value)  # 先の lookup のものを取る
    if not vertical:
        encoded = set(font.getBestCmap().values())
        mapping = {key: value for key, value in mapping.items() if key in encoded}
    return mapping


def lookup_subtables(gsub, index: int) -> list:
    return [getattr(s, "ExtSubTable", s) for s in gsub.LookupList.Lookup[index].SubTable]


def lookup_type(gsub, index: int) -> int:
    lookup = gsub.LookupList.Lookup[index]
    return lookup.SubTable[0].ExtensionLookupType if lookup.LookupType == 7 else lookup.LookupType


def feature_lookup_indexes(font: TTFont, tags) -> dict[int, set[str]]:
    """欧字の用字系の既定で、tags の機能が使う lookup → その機能"""
    gsub = font["GSUB"].table
    result: dict[int, set[str]] = {}
    for index in lang_system(font, "latn", None).FeatureIndex:
        record = gsub.FeatureList.FeatureRecord[index]
        if record.FeatureTag in tags:
            for lookup in record.Feature.LookupListIndex:
                result.setdefault(lookup, set()).add(record.FeatureTag)
    return result


def outputs(font: TTFont, tags) -> set[str]:
    """tags の機能 (文脈の lookup から呼ぶ lookup も) が置き換えてできる字"""
    gsub = font["GSUB"].table
    pending, seen, result = list(feature_lookup_indexes(font, tags)), set(), set()
    while pending:
        index = pending.pop()
        if index in seen:
            continue
        seen.add(index)
        for subtable in lookup_subtables(gsub, index):
            result |= set(singles(subtable).values()) | set(getattr(subtable, "Substitute", []))
            result |= {glyph for values in multiples(subtable).values() for glyph in values}
            pending += [record.LookupListIndex for record in getattr(subtable, "SubstLookupRecord", [])]
    return result


def apply_features(font: TTFont, glyphs: list[str], masks: list[set[str]]) -> list[str]:
    """GSUB の、1 対 1 (1)・文脈 (6 の形式 3)・右からの文脈 (8) の lookup を、文字を並べる仕組みと同じ
    順 (lookup の番号の順) にかける。masks は、字ごとにかける機能 (分数を作る仕組みを確かめるため。
    build.py とは別に書く)"""
    gsub = font["GSUB"].table
    glyphs = list(glyphs)

    def single(index: int, glyph: str) -> str:
        for subtable in lookup_subtables(gsub, index):
            if glyph in singles(subtable):
                return subtable.mapping[glyph]
        return glyph

    for index, tags in sorted(feature_lookup_indexes(font, {t for m in masks for t in m}).items()):
        kind = lookup_type(gsub, index)
        on = [bool(tags & mask) for mask in masks]
        if kind == 1:
            glyphs = [single(index, g) if on[i] else g for i, g in enumerate(glyphs)]
        elif kind == 6:
            for i in range(len(glyphs)):
                if not on[i]:
                    continue
                for subtable in lookup_subtables(gsub, index):
                    if subtable.Format != 3 or subtable.InputGlyphCount != 1:
                        raise SystemExit(f"lookup {index}: only one-glyph chained contexts of format 3 are checked")
                    back = [c.glyphs for c in subtable.BacktrackCoverage]
                    ahead = [c.glyphs for c in subtable.LookAheadCoverage]
                    if (glyphs[i] in subtable.InputCoverage[0].glyphs
                            and i >= len(back) and all(glyphs[i - 1 - k] in back[k] for k in range(len(back)))
                            and i + len(ahead) < len(glyphs)
                            and all(glyphs[i + 1 + k] in ahead[k] for k in range(len(ahead)))):
                        for record in subtable.SubstLookupRecord:
                            glyphs[i] = single(record.LookupListIndex, glyphs[i])
                        break
        elif kind == 8:
            for i in reversed(range(len(glyphs))):
                if not on[i]:
                    continue
                for subtable in lookup_subtables(gsub, index):
                    back = [c.glyphs for c in subtable.BacktrackCoverage]
                    ahead = [c.glyphs for c in subtable.LookAheadCoverage]
                    covered = subtable.Coverage.glyphs
                    if (glyphs[i] in covered
                            and i >= len(back) and all(glyphs[i - 1 - k] in back[k] for k in range(len(back)))
                            and i + len(ahead) < len(glyphs)
                            and all(glyphs[i + 1 + k] in ahead[k] for k in range(len(ahead)))):
                        glyphs[i] = subtable.Substitute[covered.index(glyphs[i])]
                        break
        else:
            raise SystemExit(f"lookup {index} of {sorted(tags)} has type {kind}, which the check cannot apply")
    return glyphs


def shape(font: TTFont, text: str, tags: set[str]) -> list[str]:
    cmap = font.getBestCmap()
    return apply_features(font, [cmap[ord(c)] for c in text], [set(tags)] * len(text))


def combining_codes(cmap: dict) -> list[int]:
    return sorted(code for code in cmap if unicodedata.category(chr(code)) in ("Mn", "Me"))


def semi_voiced_kana_ligatures(font: TTFont, udp: TTFont) -> list[tuple[str, str, str]]:
    """ccmp の仮名と半濁点・濁点の合字 (か゚・ㇷ゚ など) の、(文字列, 読書 UD の字, BIZ UDP の字)"""
    cmap, cmap_udp = font.getBestCmap(), udp.getBestCmap()
    ligs, ligs_udp = gsub_ligatures(font, "ccmp"), gsub_ligatures(udp, "ccmp")
    result = []
    for base in [*range(0x3041, 0x3100), *range(0x31F0, 0x3200)]:
        if base not in cmap or base not in cmap_udp:
            continue
        ours_map = dict(ligs.get(cmap[base], ()))
        udp_map = dict(ligs_udp.get(cmap_udp[base], ()))
        for mark in (0x3099, 0x309A):
            target = ours_map.get((cmap.get(mark),))
            other = udp_map.get((cmap_udp.get(mark),))
            if target is not None and other is not None:
                result.append((chr(base) + chr(mark), target, other))
    return result


def kerning_pairs(font: TTFont) -> dict[tuple[str, str], int]:
    """できた GPOS の実効 kern ペアを展開する。生成用のクラス・文字範囲には依存しない。

    同じ lookup の先に一致したゼロ値も後のサブテーブルを遮る。Format 2 は Coverage に
    入った左の字について、クラス0を含むすべての右の字に一致する。返すのは実効値が非ゼロのペア。
    """
    table = font["GPOS"].table
    indexes = sorted({i for r in table.FeatureList.FeatureRecord if r.FeatureTag == "kern"
                      for i in r.Feature.LookupListIndex})
    result = {}
    for index in indexes:
        pairs = {}
        covered_left = set()
        for raw in table.LookupList.Lookup[index].SubTable:
            sub = getattr(raw, "ExtSubTable", raw)
            if not (sub.ValueFormat1 in (0, 4) and sub.ValueFormat2 == 0):
                raise ValueError("kern collision check requires XAdvance-only pair positioning")
            if sub.Format == 1:
                for first, pair_set in zip(sub.Coverage.glyphs, sub.PairSet):
                    if first in covered_left:
                        continue
                    for record in pair_set.PairValueRecord:
                        pairs.setdefault((first, record.SecondGlyph), getattr(record.Value1, "XAdvance", 0))
            elif sub.Format == 2:
                classes = {}
                for glyph in font.getGlyphOrder():
                    classes.setdefault(sub.ClassDef2.classDefs.get(glyph, 0), []).append(glyph)
                for first in sub.Coverage.glyphs:
                    if first in covered_left:
                        continue
                    row = sub.Class1Record[sub.ClassDef1.classDefs.get(first, 0)]
                    for cls, record in enumerate(row.Class2Record):
                        amount = getattr(record.Value1, "XAdvance", 0)
                        # クラス0の巨大なゼロ行は展開せず covered_left で表現する。
                        # 明示クラスのゼロ値と、先行する Format 1 のゼロ値は pairs に残す。
                        if amount or cls != 0:
                            for second in classes.get(cls, ()):
                                pairs.setdefault((first, second), amount)
                    covered_left.add(first)
            else:
                raise ValueError(f"unsupported kern pair format: {sub.Format}")
        for pair, amount in pairs.items():
            if amount:
                result[pair] = result.get(pair, 0) + amount
    return {pair: amount for pair, amount in result.items() if amount}
