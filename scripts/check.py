"""fonts/ の読書 UD を、元の BIZ UD・BIZ UDP と突き合わせて確かめる。

build.py とは別の書き方で、できたものだけを見る。1 つでも合わなければ 1 で終わる。
"""

import copy
import math
import sys
import unicodedata
from pathlib import Path
from statistics import median

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont

import freetype_render
import harfbuzz_shape
import kerning
import small_type
import spec
import width_reference

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "sources"
FONTS = ROOT / "fonts"

# 和文の字。BIZ UD のままで、全角 (横も縦も 1 em) であること
JAPANESE = "あいうえおっゃー漢字読書。、・「」（）：！？　"

problems: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        problems.append(message)


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
                for key, value in getattr(subtable, "mapping", {}).items():
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
                for key, value in getattr(subtable, "mapping", {}).items():
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


def check_font(family: dict, weight: str) -> None:
    label = spec.output_name(family, weight)
    font = TTFont(FONTS / label)
    ud = TTFont(SOURCES / f"{family['ud']}-{weight}.ttf")
    udp = TTFont(SOURCES / f"{family['udp']}-{weight}.ttf")
    cmap, cmap_ud, cmap_udp = font.getBestCmap(), ud.getBestCmap(), udp.getBestCmap()
    em = font["head"].unitsPerEm

    # 文字の割り当ては BIZ UD のまま。足すのは、作った上付きの数字 ⁰ ⁵ ⁶ ⁷ ⁸ ⁹ などだけ。変えるのは、
    # ほかの文字と字を分け合っていた結合用の記号 (˜ U+02DC と同じ字の U+0303) だけ
    added = {code: cmap[code] for code in cmap.keys() - cmap_ud.keys()}
    remapped = {code for code in cmap_ud if cmap.get(code) != cmap_ud[code]}
    shared_marks = {code for code in combining_codes(cmap_ud)
                    if any(c != code and g == cmap_ud[code] for c, g in cmap_ud.items())}
    check(remapped <= shared_marks and set(added) == set(NEW_SUPERSCRIPTS) | set(EXTRA_CODES) | {0x301E},
          f"{label}: the character map differs from BIZ UD by more than the superscripts and subscripts")
    # BIZ UD のグリフの後に、欧文の中の記号 (BIZ UDP の字) だけが足してあること
    order, order_ud = font.getGlyphOrder(), ud.getGlyphOrder()
    check(order[: len(order_ud)] == order_ud, f"{label}: the glyph order of BIZ UD is not kept")
    # と、hwid の置き換え先として残した BIZ UD の半角の字
    extra = set(order[len(order_ud):])
    half_widths = {v for v in gsub_mapping(font, "hwid").values() if v not in order_ud}
    fraction_glyphs = (set(added.values()) | outputs(font, spec.FRACTION_FEATURES)) - set(order_ud)
    # 縦組の ⸺ ⸻
    fraction_glyphs |= {gsub_mapping(font, "vert").get(cmap.get(code)) for code in (0x2E3A, 0x2E3B)} - {None}
    # 等幅の数字 (tnum) と、字を分け合っていた結合用の記号
    fraction_glyphs |= outputs(font, ["tnum", "calt", "ss02", "ss03"]) | {cmap[code] for code in remapped}
    # 上の記号の前の、点の無い全角の ｉ
    # (post は形式 3 で、足した字の名前はファイルに残らないので、ｉ からの置き換え先から引く)
    gsub_table = font["GSUB"].table
    fraction_glyphs |= {getattr(s, "mapping", {}).get(cmap[0xFF49])
                        for i in range(len(gsub_table.LookupList.Lookup)) for s in lookup_subtables(gsub_table, i)} - {None}
    # 欧文の中の記号の、BIZ UDP の縦組の字
    fraction_glyphs |= (set(latin_symbol_mapping(font, "latn", None, vertical=True).values())
                        | outputs(font, ["vert", "vrt2"])) - set(order_ud)
    check(extra == set(latin_symbol_mapping(font, "latn", None).values()) | half_widths | fraction_glyphs,
          f"{label}: glyphs other than the symbols for Latin text, the half widths for hwid and the fraction "
          "digits and stylistic sets were added")

    check(latin_codes(cmap) == latin_codes(cmap_udp), f"{label}: BIZ UDP has other Latin letters than BIZ UD")
    for code in latin_codes(cmap):
        g, gp = cmap[code], cmap_udp[code]
        check(font["hmtx"][g] == udp["hmtx"][gp] and font["vmtx"][g] == udp["vmtx"][gp],
              f"{label}: U+{code:04X} metrics are not BIZ UDP's")
        check(outline(font, g) == outline(udp, gp), f"{label}: U+{code:04X} outline is not BIZ UDP's")
    # ピンインの ǐ ǎ は、BIZ UD では全角。アクセントの無い字と同じ幅になること
    widths = {chr(c): font["hmtx"][cmap[c]][0] for c in map(ord, "iWmaǐǎ")}
    check(widths["i"] * 2 < widths["W"] and widths["ǐ"] == widths["i"] and widths["ǎ"] == widths["a"],
          f"{label}: Latin letters are not proportional: {widths}")

    for char in JAPANESE:
        g = cmap[ord(char)]
        check(font["hmtx"][g][0] == em, f"{label}: {char} is not full width")
        check(font["vmtx"][g][0] == em, f"{label}: {char} does not advance 1 em in vertical text")
        check(outline(font, g) == outline(ud, cmap_ud[ord(char)]), f"{label}: {char} outline is not BIZ UD's")
    for char in "×÷":
        g = cmap[ord(char)]
        check(font["hmtx"][g] == ud["hmtx"][cmap_ud[ord(char)]], f"{label}: {char} is not BIZ UD's")

    latin_glyphs = {cmap[c] for c in latin_codes(cmap)}
    for tag in spec.LATIN_FEATURES:
        if tag in spec.FRACTION_FEATURES:
            continue  # check_fractions が確かめる
        ours = {k: v for k, v in gsub_mapping(font, tag).items() if k in latin_glyphs}
        theirs = {k: v for k, v in gsub_mapping(udp, tag).items() if k in latin_glyphs}
        check(ours == theirs, f"{label}: {tag} of the Latin letters differs from BIZ UDP")
    for tag in spec.LATIN_LIGATURE_FEATURES:
        ours = {k: v for k, v in gsub_ligatures(font, tag).items() if k in latin_glyphs}
        theirs = {k: v for k, v in gsub_ligatures(udp, tag).items() if k in latin_glyphs}
        check(ours == theirs, f"{label}: {tag} ligatures of the Latin letters differ from BIZ UDP")
    for target, tag in sorted(latin_targets(udp, latin_glyphs).items()):
        check(font["hmtx"][target] == udp["hmtx"][target] and font["vmtx"][target] == udp["vmtx"][target],
              f"{label}: {tag} target {target} metrics are not BIZ UDP's")
        check(outline(font, target) == outline(udp, target), f"{label}: {tag} target {target} outline is not BIZ UDP's")
    # 結合用のアクセントを付けた字 (ə + ́ など) は、BIZ UDP の幅の字になること
    schwa_acute = dict(gsub_ligatures(font, "ccmp").get(cmap[0x0259], [])).get((cmap[0x0301],))
    check(schwa_acute is not None and font["hmtx"][schwa_acute][0] == font["hmtx"][cmap[0x0259]][0],
          f"{label}: ə with U+0301 is not as wide as ə")
    # 字形の候補 (aalt) の欧字の候補に、BIZ UD の古い置き換え先 (今の置き換えには無い、等幅の横倒しの
    # 字など。BIZ UDP でも候補のものは除く) が残らず、BIZ UDP の aalt にある今の置き換え先が入っていること
    ours_aalt, udp_aalt = gsub_alternates(font, "aalt"), gsub_alternates(udp, "aalt")
    for tag in spec.LATIN_FEATURES:
        now = {k: v for k, v in gsub_mapping(font, tag).items() if k in latin_glyphs}
        old = {v for k, v in gsub_mapping(ud, tag).items() if k in latin_glyphs} - set(now.values())
        stale = sorted((k, v) for k in latin_glyphs for v in ours_aalt.get(k, [])
                       if v in old and v not in udp_aalt.get(k, []))
        check(not stale, f"{label}: aalt offers {len(stale)} old {tag} glyphs of BIZ UD, such as {stale[:3]}")
        missing = sorted(k for k, v in now.items() if v in udp_aalt.get(k, []) and v not in ours_aalt.get(k, []))
        check(not missing, f"{label}: aalt lacks the {tag} glyphs of {len(missing)} Latin letters, such as {missing[:3]}")
    # hwid (全角の英数字 Ａ ％ などを半角に) は、BIZ UD と同じ半角の字 (形・字幅・縦の字送り) になり、
    # 縦組では BIZ UD と同じ横に倒した字になること (欧字を BIZ UDP の字にしても、半角のまま)。
    # BIZ UDP の字になった欧字 (A・1 など) も、hwid で BIZ UD の半角の字になること (読書 UD で足した)
    ours_hwid, ud_hwid = gsub_mapping(font, "hwid"), gsub_mapping(ud, "hwid")
    ours_vrt2, ud_vrt2 = gsub_mapping(font, "vrt2"), gsub_mapping(ud, "vrt2")
    expected = dict(ud_hwid)
    mark_glyphs = {cmap_ud[code] for code in combining_codes(cmap_ud)}
    for name in set(ud_hwid.values()) - mark_glyphs:  # 字幅 0 にした結合用の記号からは、hwid は無い
        if name in font["hmtx"].metrics and (font["hmtx"][name] != ud["hmtx"][name] or outline(font, name) != outline(ud, name)):
            expected[name] = name
    # 除外できるのは ss02 専用の複製だけ。通常の locl と共有していないことも必須。
    style_inputs = vertical_closure(font, outputs(font, ("ss02",)))
    ordinary = set(cmap.values()) | vertical_closure(font, outputs(font, ("locl",)))
    check(not style_inputs & ordinary, f"{label}: ss02 shares width-guard inputs with ordinary glyphs")
    check(ours_hwid.keys() - style_inputs == expected.keys(),
          f"{label}: hwid changed its original coverage outside ss02-only copies")
    ours_fwid, ud_fwid = gsub_mapping(font, "fwid"), gsub_mapping(ud, "fwid")
    check({key: target for key, target in ours_fwid.items() if key not in style_inputs} == ud_fwid,
          f"{label}: fwid changed original substitutions outside ss02-only copies")
    for key in sorted(ours_hwid.keys() & expected.keys()):
        pairs = [(ours_hwid[key], expected[key])]
        if expected[key] in ud_vrt2:
            pairs.append((ours_vrt2.get(ours_hwid[key]), ud_vrt2[expected[key]]))
        for g, gu in pairs:
            check(g is not None and font["hmtx"][g] == ud["hmtx"][gu] and font["vmtx"][g] == ud["vmtx"][gu]
                  and outline(font, g) == outline(ud, gu), f"{label}: hwid of {key} gives {g}, not BIZ UD's {gu}")
    # 字形の候補 (aalt) に、半角の字も出ること。欧字 (A) の候補にも、全角の字 (Ａ) の候補にも
    # (BIZ UD で全角の字が欧字を候補に持つなら、プロポーショナルの欧字と半角の字の両方)
    ud_aalt = gsub_alternates(ud, "aalt")
    for key, name in sorted(ud_hwid.items()):
        half = ours_hwid.get(key)
        if half is None or half == name or name not in ours_hwid:
            continue  # 欧字そのものが半角のままなら (横組の形が BIZ UDP と同じ *)、候補は増やさない
        check(half in ours_aalt.get(name, []), f"{label}: aalt of {name} does not offer {half}")
        if name in ud_aalt.get(key, []):
            check(name in ours_aalt.get(key, []) and half in ours_aalt.get(key, []),
                  f"{label}: aalt of {key} does not offer both {name} and {half}")
    features = {r.FeatureTag for r in font["GSUB"].table.FeatureList.FeatureRecord}
    check({"vert", "vrt2", "fwid"} <= features, f"{label}: vertical or full-width features are missing")
    check("vhea" in font and "vmtx" in font, f"{label}: vertical metrics are missing")

    names = {(r.nameID, r.langID): r.toUnicode() for r in font["name"].names}
    check(names.get((1, 0x409)) == family["name_en"], f"{label}: English family name {names.get((1, 0x409))!r}")
    check(names.get((1, 0x411)) == family["name_ja"], f"{label}: Japanese family name {names.get((1, 0x411))!r}")
    check(names.get((2, 0x409)) == weight, f"{label}: style name {names.get((2, 0x409))!r}")
    check(names.get((6, 0x409)) == f"{family['postscript']}-{weight}", f"{label}: PostScript name")
    check((7, 0x409) not in names, f"{label}: the trademark of BIZ UD is still in the name table")
    # 版の表記 (5) が、元のフォントの版 ("Version 1.05" など) を正しく書くこと
    based_on = [f"{source['name'].getDebugName(1)} {source['name'].getDebugName(5).split()[1]}" for source in (ud, udp)]
    check(names.get((5, 0x409)) == f"Version {spec.VERSION}; based on {based_on[0]} and {based_on[1]}",
          f"{label}: name 5 is {names.get((5, 0x409))!r}, not based on {based_on}")
    for (name_id, _), text in names.items():
        # BIZ UD の名前は、元の著作権表示 (0)・説明 (5・10)・使用許諾の全文 (13。著作権表示を含む) にだけ出る
        if name_id not in (0, 5, 10, 13):
            check("BIZ" not in text, f"{label}: name {name_id} still says {text!r}")
    check(spec.COPYRIGHT in names.get((0, 0x409), ""), f"{label}: our copyright line is missing")
    # フォントのファイルだけで配るので、使用許諾の全文がフォントの中にあること
    license_text = (ROOT / "OFL.txt").read_text(encoding="utf-8").replace("\r\n", "\n").strip()
    check(names.get((13, 0x409)) == license_text, f"{label}: name 13 is not the full text of OFL.txt")
    check(names.get((14, 0x409)) == "https://scripts.sil.org/OFL", f"{label}: name 14 is not the OFL URL")
    check(font["post"].isFixedPitch == 0, f"{label}: still marked as fixed pitch")
    check("DSIG" not in font, f"{label}: the signature of BIZ UD is still there")
    check(f"{font['head'].fontRevision:.3f}" == spec.VERSION, f"{label}: font revision")
    check(font["OS/2"].fsType == 0, f"{label}: embedding is restricted")
    # BIZ UD の範囲ビットに、足した上付きと下付きの bit 32 だけを加える (BOM を足しただけで bit 67 などを名乗らない)
    ranges = ("ulUnicodeRange1", "ulUnicodeRange2", "ulUnicodeRange3", "ulUnicodeRange4")
    check([getattr(font["OS/2"], a) for a in ranges]
          == [ud["OS/2"].ulUnicodeRange1, ud["OS/2"].ulUnicodeRange2 | 1, ud["OS/2"].ulUnicodeRange3, ud["OS/2"].ulUnicodeRange4],
          f"{label}: OS/2 Unicode ranges are not those of BIZ UD plus bit 32")
    check(bool(font["OS/2"].ulUnicodeRange2 & 1), f"{label}: OS/2 bit 32 (Superscripts And Subscripts) is not set")
    check_latin_symbols(label, font, ud, udp)
    check_hinting(label, font, family, weight, latin_targets(udp, latin_glyphs), udp, ud)
    check_spacing(label, font)
    check_fractions(label, font, udp)
    check_extra(label, font)
    check_proportional(label, font, udp)
    check_proportional_vertical(label, font, udp)
    check_tabular(label, font)
    check_marks(label, font, ud)
    check_overflow(label, font, ud, udp)
    check_shaping(label, family, weight)
    check_colon(label, family, weight)
    check_reading_features(label, family, weight)


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
                for key, value in getattr(subtable, "mapping", {}).items():
                    mapping.setdefault(key, value)  # 先の lookup のものを取る
    if not vertical:
        encoded = set(font.getBestCmap().values())
        mapping = {key: value for key, value in mapping.items() if key in encoded}
    return mapping


def drawing(font: TTFont, name: str) -> list:
    pen = DecomposingRecordingPen(font.getGlyphSet())
    font.getGlyphSet()[name].draw(pen)
    return pen.value


def check_latin_symbols(label: str, font: TTFont, ud: TTFont, udp: TTFont) -> None:
    """欧文の中の記号。できたフォントと BIZ UDP で違う記号は、欧字の用字系 (latn) の既定でだけ BIZ UDP の
    字 (形と字幅) に置き換わり、日本語 (latn の JAN) と和文などの用字系では、spec.ALWAYS_UDP だけが
    置き換わること。書式の文字
    (ソフトハイフンなど) は、どこでも置き換わらないこと"""
    cmap, cmap_ud, cmap_udp = font.getBestCmap(), ud.getBestCmap(), udp.getBestCmap()
    latin = latin_symbol_mapping(font, "latn", None)
    for code in spec.LATIN_SYMBOLS:
        if code not in cmap_ud or code not in cmap_udp:
            continue
        # 比べるのは、できたフォントの字。欧字の置き換え先 (sups の ² など) は、すでに BIZ UDP の字に
        # なっているので、欧文の中でも置き換えなくてよい
        name, name_udp = cmap[code], cmap_udp[code]
        differs = font["hmtx"][name] != udp["hmtx"][name_udp] or drawing(font, name) != drawing(udp, name_udp)
        target = latin.get(name)
        # 書式の文字 (ソフトハイフンなど) は置き換えない。HarfBuzz は、フォントが置き換えた字を隠さない
        if unicodedata.category(chr(code)) == "Cf":
            check(target is None, f"{label}: the format character U+{code:04X} is substituted in Latin text")
            continue
        if not differs:
            check(target is None, f"{label}: U+{code:04X} is the same in BIZ UDP but is substituted")
            continue
        if target is None:
            problems.append(f"{label}: U+{code:04X} is not substituted in Latin text")
            continue
        check(font["hmtx"][target] == udp["hmtx"][name_udp], f"{label}: U+{code:04X} in Latin text is not as wide as BIZ UDP's")
        check(drawing(font, target) == drawing(udp, name_udp), f"{label}: U+{code:04X} in Latin text is not BIZ UDP's shape")
    for char in "‘’“”":
        check(cmap[ord(char)] in latin, f"{label}: {char} is not substituted in Latin text")
    check(lang_system(font, "latn", "JAN ") is not None, f"{label}: latn has no JAN language system")
    # 日本語 (latn の JAN) と、和文などほかの用字系では、spec.ALWAYS_UDP だけを置き換える
    always = {cmap[code]: latin[cmap[code]] for code in spec.ALWAYS_UDP}
    # 記号だけの組 (DFLT) は欧字の用字系と同じ (ブラウザが行末に足すハイフンは、1 字で組まれる)
    check(latin_symbol_mapping(font, "DFLT", None) == latin, f"{label}: DFLT does not substitute as latn does")
    for script, language in [("latn", "JAN "), ("DFLT", "JAN "), ("hani", None), ("kana", None), ("grek", None),
                             ("cyrl", None)]:
        check(latin_symbol_mapping(font, script, language) == always,
              f"{label}: the symbols substituted in {script} {language or 'dflt'} are not spec.ALWAYS_UDP")


# 描いて比べる大きさ (1 em の画素の数)。ヒンティングが効くのは小さな大きさ
HINTING_PPEMS = range(8, 25)


def check_hinting(label: str, font: TTFont, family: dict, weight: str, targets: dict[str, str],
                  udp_font: TTFont, ud_font: TTFont) -> None:
    """BIZ UDP から持ってきた字のヒンティングが BIZ UDP と同じで、和文のヒンティングが BIZ UD と
    同じこと。FreeType でヒンティングを動かして描き、画素を比べる (hinting.py が cvt の番号を
    ずらし損ねていれば、字の形がずれる)"""
    paths = {"ours": FONTS / label, "ud": SOURCES / f"{family['ud']}-{weight}.ttf",
             "udp": SOURCES / f"{family['udp']}-{weight}.ttf"}
    cmap, cmap_ud = font.getBestCmap(), ud_font.getBestCmap()
    unhinted_ud = {cmap_ud[code] for code in spec.UNHINTED if code in cmap_ud}
    symbols = latin_symbol_mapping(font, "latn", None)
    by_name = {name: code for code, name in cmap.items()}
    order_ud = set(ud_font.getGlyphOrder())
    ud_hwid = gsub_mapping(ud_font, "hwid")
    # 後段の ss02 用入力は追加グリフなので、元フォントにある入力からだけ控えの由来を引く。
    half_widths = {half: ud_hwid.get(key, key) for key, half in gsub_mapping(font, "hwid").items()
                   if half not in order_ud and key in order_ud}
    check(half_widths, f"{label}: no half widths for hwid to draw")
    plain_gray = freetype_render.Renderer(paths["ours"], freetype_render.MODES[0][1], freetype_render.NO_HINTING)
    # 字全体が消えうるのは、インクの幅か高さが細い字だけ (漢字などは、線が 1 本消えても字は残る)
    glyf = font["glyf"]
    thin = [(name, index) for index, name in enumerate(font.getGlyphOrder()) if glyf[name].numberOfContours
            and min(glyf[name].xMax - glyf[name].xMin, glyf[name].yMax - glyf[name].yMin) <= font["head"].unitsPerEm // 8]
    has_ink_gray = [(name, index, ppem) for name, index in thin for ppem in HINTING_PPEMS
                    if any(plain_gray.render(index, ppem)[5])]
    plain_gray.close()
    for mode, interpreter, flags in freetype_render.MODES:
        renderers = {key: freetype_render.Renderer(path, interpreter, flags) for key, path in paths.items()}
        ours, ud, udp = renderers["ours"], renderers["ud"], renderers["udp"]
        # (何を, 読書 UD のグリフの番号, 比べる相手, 相手のグリフの番号)
        # ヒンティングを付けない字 (spec.UNHINTED) は、元のフォントと同じには描かれない
        cases = [(f"U+{code:04X}", ours.char_index(code), udp, udp.char_index(code)) for code in latin_codes(cmap)
                 if code not in spec.UNHINTED]
        cases += [(f"U+{by_name[source]:04X} in Latin text", font.getGlyphID(target), udp, udp.char_index(by_name[source]))
                  for source, target in symbols.items() if by_name[source] not in spec.UNHINTED]
        # 欧字からの置き換え先と合字 (² ・斜線の 0・縦組で横に倒した欧字・ﬁ など)。グリフの番号は
        # BIZ UD と BIZ UDP で違うので、名前で引く
        cases += [(f"{target} ({tag})", font.getGlyphID(target), udp, udp_font.getGlyphID(target))
                  for target, tag in sorted(targets.items())]
        cases += [(char, ours.char_index(ord(char)), ud, ud.char_index(ord(char))) for char in JAPANESE]
        # hwid の置き換え先として残した、BIZ UD の半角の字 (足した字。post は形式 3 で、名前は番号から
        # 付くので、hwid の置き換えから BIZ UD の字を引く。欧字 A からの置き換えなら、BIZ UD の A)
        cases += [(f"{name} (hwid of {source})", font.getGlyphID(name), ud, ud_font.getGlyphID(source))
                  for name, source in sorted(half_widths.items()) if source not in unhinted_ud]
        differ = []
        for what, ours_index, other, other_index in cases:
            for ppem in HINTING_PPEMS:
                if ours.render(ours_index, ppem) != other.render(other_index, ppem):
                    differ.append(f"{what} at {ppem} ppem")
        check(not differ, f"{label}: {mode}: {len(differ)} glyphs are not drawn as in BIZ UD / BIZ UDP, "
                          f"such as {differ[:3]}")
        for renderer in renderers.values():
            renderer.close()
        check_nothing_vanishes(label, font, mode, interpreter, flags, symbols, by_name, targets, half_widths,
                               unhinted_ud, has_ink_gray)
    # 細い横線だけの字 (spec.UNHINTED) は、文字が指す字・欧文の中の置き換え先・hwid の半角の字・2 倍と 3 倍の
    # ダッシュのどれもヒンティングを持たないこと
    for code in [*spec.UNHINTED, 0x2E3A, 0x2E3B]:
        names = [cmap[code]] if code in cmap else []
        names += [target for source, target in symbols.items() if by_name[source] == code]
        names += [half for half, source in half_widths.items() if source == cmap_ud.get(code)]
        for name in names:
            program = getattr(font["glyf"][name], "program", None)
            check(program is None or not program.getBytecode(), f"{label}: U+{code:04X} ({name}) still has hinting")


def check_nothing_vanishes(label: str, font: TTFont, mode: str, interpreter: int, flags: int,
                           symbols: dict, by_name: dict, targets: dict[str, str], half_widths: dict,
                           unhinted_ud: set[str], has_ink_gray: list) -> None:
    """ヒンティングを動かすと何も描かれなくなる字が無いこと (動かさなければ描ける字)。グレースケールでは
    フォントの全てのグリフを、モノクロでは欧字・記号・細い横線の字を確かめる"""
    hinted = freetype_render.Renderer(FONTS / label, interpreter, flags)
    if not flags:
        gone = [f"{name} at {ppem} ppem" for name, index, ppem in has_ink_gray
                if not any(hinted.render(index, ppem)[5])]
    else:
        plain = freetype_render.Renderer(FONTS / label, interpreter, flags | freetype_render.NO_HINTING)
        cmap = font.getBestCmap()
        glyphs = [(f"U+{code:04X}", hinted.char_index(code))
                  for code in sorted({*latin_codes(cmap), *(c for c in spec.UNHINTED if c in cmap), 0x2E3A, 0x2E3B})]
        glyphs += [(f"U+{by_name[source]:04X} in Latin text", font.getGlyphID(target))
                   for source, target in symbols.items()]
        glyphs += [(f"{target} ({tag})", font.getGlyphID(target)) for target, tag in sorted(targets.items())]
        glyphs += [(f"{half} (hwid)", font.getGlyphID(half))
                   for half, source in sorted(half_widths.items()) if source in unhinted_ud]
        gone = [f"{what} at {ppem} ppem" for what, index in glyphs for ppem in HINTING_PPEMS
                if not any(hinted.render(index, ppem)[5]) and any(plain.render(index, ppem)[5])]
        plain.close()
    check(not gone, f"{label}: {mode}: hinting erases {len(gone)} glyphs, such as {gone[:3]}")
    hinted.close()


def check_spacing(label: str, font: TTFont) -> None:
    """約物の詰め (halt・vhal)。詰めた後もインクが字の枠に収まり、代表の字が JLReq の値であること"""
    if "GPOS" not in font:
        problems.append(f"{label}: no GPOS (halt and vhal are missing)")
        return
    em, half, quarter = font["head"].unitsPerEm, font["head"].unitsPerEm // 2, font["head"].unitsPerEm // 4
    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap()
    vertical_forms = gsub_mapping(font, "vert")
    halt, vhal = gpos_values(font, "halt"), gpos_values(font, "vhal")
    for glyph, (x, y, x_advance, y_advance) in halt.items():
        pen = BoundsPen(glyph_set)
        glyph_set[glyph].draw(pen)
        left, right = pen.bounds[0] + x, pen.bounds[2] + x
        width = font["hmtx"][glyph][0] + x_advance
        check(0 <= left and right <= width, f"{label}: halt of {glyph} puts its ink outside its width")
    for glyph, (x, y, x_advance, y_advance) in vhal.items():
        pen = BoundsPen(glyph_set)
        glyph_set[glyph].draw(pen)
        advance, top_side = font["vmtx"][glyph]
        top = top_side - y  # 上へ動かすと、枠の上からの位置は小さくなる
        bottom = top + (pen.bounds[3] - pen.bounds[1])
        check(0 <= top and bottom <= advance + y_advance, f"{label}: vhal of {glyph} puts its ink outside its advance")
    expected = {
        "「": ((-half, 0, -half, 0), (0, half, 0, -half)),
        "」": ((0, 0, -half, 0), (0, 0, 0, -half)),
        "。": ((0, 0, -half, 0), (0, 0, 0, -half)),
        "、": ((0, 0, -half, 0), (0, 0, 0, -half)),
        "・": ((-quarter, 0, -half, 0), (0, quarter, 0, -half)),
    }
    for char, (horizontal, vertical) in expected.items():
        glyph = cmap[ord(char)]
        check(halt.get(glyph) == horizontal, f"{label}: halt of {char} is {halt.get(glyph)}, not {horizontal}")
        upright = vertical_forms.get(glyph, glyph)
        check(vhal.get(upright) == vertical, f"{label}: vhal of {char} is {vhal.get(upright)}, not {vertical}")
    scripts = {r.ScriptTag for r in font["GPOS"].table.ScriptList.ScriptRecord}
    check({"hani", "kana", "DFLT"} <= scripts, f"{label}: GPOS scripts {sorted(scripts)}")


# --- 分数と上付きの数字 -----------------------------------------------------------------------

SUPERSCRIPT_CODES = {0: 0x2070, 1: 0x00B9, 2: 0x00B2, 3: 0x00B3, 4: 0x2074,
                     **{d: 0x2070 + d for d in range(5, 10)}}
# 元のフォントに無く、作った字 (⁰ ⁵〜⁹ ⁺ ⁻ ⁼ ⁽ ⁾ と、₀〜₉ ₊ ₋ ₌ ₍ ₎)
NEW_SUPERSCRIPTS = {0x2070, *range(0x2075, 0x207F), *range(0x2080, 0x208F)}
# 上付きの記号 → 元の字 (− は BIZ UDP の字) と、sups でそれになる字
SUPERSCRIPT_SYMBOLS = {0x207A: (0x002B, "+"), 0x207B: (0x2212, "−-"), 0x207C: (0x003D, "="),
                       0x207D: (0x0028, "("), 0x207E: (0x0029, ")")}


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
            result |= set(getattr(subtable, "mapping", {}).values()) | set(getattr(subtable, "Substitute", []))
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
            if glyph in getattr(subtable, "mapping", {}):
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


def flattened(font: TTFont, name: str, dx: float = 0, dy: float = 0) -> list[list[tuple[float, float]]]:
    """グリフの輪郭を、折れ線にしたもの (曲線は 16 に分ける)"""
    pen = DecomposingRecordingPen(font.getGlyphSet())
    font.getGlyphSet()[name].draw(pen)
    polygons, current, start = [], [], None
    for op, args in pen.value:
        if op == "moveTo":
            current, start = [args[0]], args[0]
        elif op == "lineTo":
            current.append(args[0])
        elif op == "qCurveTo":
            points = list(args)
            if points[-1] is None:  # 曲線の上の点が無い輪郭
                raise SystemExit(f"{name}: contours without on-curve points are not checked")
            p0 = current[-1]
            controls, end = points[:-1], points[-1]
            for k, control in enumerate(controls):
                target = end if k == len(controls) - 1 else (
                    ((control[0] + controls[k + 1][0]) / 2, (control[1] + controls[k + 1][1]) / 2))
                for step in range(1, 17):
                    t = step / 16
                    current.append(((1 - t) ** 2 * p0[0] + 2 * t * (1 - t) * control[0] + t * t * target[0],
                                    (1 - t) ** 2 * p0[1] + 2 * t * (1 - t) * control[1] + t * t * target[1]))
                p0 = target
        elif op in ("closePath", "endPath"):
            if current:
                polygons.append(current)
            current = []
    return [[(x + dx, y + dy) for x, y in polygon] for polygon in polygons]


def row(polygons, y: float) -> list[float]:
    xs = []
    for polygon in polygons:
        for (x0, y0), (x1, y1) in zip(polygon, polygon[1:] + polygon[:1]):
            if (y0 <= y < y1) or (y1 <= y < y0):
                xs.append(x0 + (y - y0) / (y1 - y0) * (x1 - x0))
    return sorted(xs)


def ink_gap(left, right) -> float:
    """left のインクの右から right のインクの左までの、同じ高さどうしのいちばん近い横の距離"""
    ys = [y for polygon in left + right for _x, y in polygon]
    best = None
    for y in range(int(min(ys)), int(max(ys)) + 1, 3):
        a, b = row(left, y + 0.5), row(right, y + 0.5)
        if a and b:
            best = b[0] - a[-1] if best is None else min(best, b[0] - a[-1])
    return best


def ink_area(font: TTFont, name: str) -> float:
    total = 0.0
    for polygon in flattened(font, name):
        total += sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(polygon, polygon[1:] + polygon[:1])) / 2
    return abs(total)


def glyph_bounds(font: TTFont, name: str):
    pen = BoundsPen(font.getGlyphSet())
    font.getGlyphSet()[name].draw(pen)
    return pen.bounds


def offset_of(font: TTFont, name: str, other: str):
    """name の輪郭が other の輪郭を平行に動かしたものなら、その (dx, dy)。違えば None"""
    a, b = outline(font, name), outline(font, other)
    if a[1:] != b[1:] or not a[0]:
        return None
    dx, dy = a[0][0][0] - b[0][0][0], a[0][0][1] - b[0][0][1]
    return (dx, dy) if all((x - u, y - v) == (dx, dy) for (x, y), (u, v) in zip(a[0], b[0])) else None


def check_fractions(label: str, font: TTFont, udp: TTFont) -> None:
    """上付きの数字 0〜9 (sups と ⁰ ¹ … ⁹)、分子 (numr)・分母 (dnom) の数字、frac の分数。
    - 上付きの数字: 1〜4 は BIZ UDP の ¹ ² ³ ⁴。作った 0・5〜9 は、普通の数字に対するインクの面積の比
      (縮めて太らせた度合い) と高さが、¹ ² ³ ⁴ と同じくらい
    - 分子・分母は上付きの数字と同じ形で、分母はそれを同じだけ下げたもの (下が数字の下にそろう)
    - frac は分数の数字だけを置き換え、数字と斜線のインクの距離が、BIZ UDP の合成済みの分数
      (¼ ½ ¾ ⅓ …) の中央値になる"""
    cmap = font.getBestCmap()
    digits = [cmap[0x30 + d] for d in range(10)]
    sups = {d: cmap[code] for d, code in SUPERSCRIPT_CODES.items()}
    for tag in spec.FRACTION_FEATURES:
        check(tag in {r.FeatureTag for r in font["GSUB"].table.FeatureList.FeatureRecord}, f"{label}: no {tag}")

    # 上付きの数字
    ratios = {d: ink_area(font, sups[d]) / ink_area(font, digits[d]) for d in range(10)}
    heights = {d: glyph_bounds(font, sups[d])[3] - glyph_bounds(font, sups[d])[1] for d in range(10)}
    bottoms = {d: glyph_bounds(font, sups[d])[1] for d in range(10)}
    designed = [1, 2, 3, 4]
    low, high = min(ratios[d] for d in designed), max(ratios[d] for d in designed)
    for d in (0, 5, 6, 7, 8, 9):
        check(low * 0.9 <= ratios[d] <= high * 1.1,
              f"{label}: superscript {d} has {ratios[d]:.3f} of the ink of {d}, not like ¹ ² ³ ⁴ ({low:.3f}-{high:.3f})")
        check(abs(heights[d] - sum(heights[k] for k in designed) / 4) <= 0.06 * heights[2],
              f"{label}: superscript {d} is {heights[d]:.0f} high, not like ¹ ² ³ ⁴")
        check(min(bottoms[k] for k in designed) - 30 <= bottoms[d] <= max(bottoms[k] for k in designed) + 30,
              f"{label}: superscript {d} does not sit as ¹ ² ³ ⁴ do")
        program = getattr(font["glyf"][sups[d]], "program", None)
        check(program is not None and program.getBytecode(), f"{label}: superscript {d} lacks its small-digit hinting")
    for d in range(10):
        for source in (digits[d], cmap[0xFF10 + d]):
            check(shape(font, chr(cmap_code(cmap, source)), {"sups"}) == [sups[d]], f"{label}: sups of {source}")
        check(sups[d] in gsub_alternates(font, "aalt").get(digits[d], []), f"{label}: aalt of {d} lacks its superscript")

    # 上付きの記号: 本文の字との高さの関係が、数字と同じ (1〜4 の下と上から、本文の y を上付きの y に
    # する式を求める)。インクの面積の比も、¹ ² ³ ⁴ と同じくらい
    pairs = [(glyph_bounds(font, digits[d])[k], glyph_bounds(font, sups[d])[k]) for d in designed for k in (1, 3)]
    mean_x = sum(x for x, _ in pairs) / len(pairs)
    mean_y = sum(y for _, y in pairs) / len(pairs)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in pairs) / sum((x - mean_x) ** 2 for x, _ in pairs)
    cmap_udp = udp.getBestCmap()
    for code, (source, inputs) in SUPERSCRIPT_SYMBOLS.items():
        name = cmap.get(code)
        if name is None:
            problems.append(f"{label}: U+{code:04X} is missing")
            continue
        base, base_name = (udp, cmap_udp[source]) if source == 0x2212 else (font, cmap[source])
        body, sup = glyph_bounds(base, base_name), glyph_bounds(font, name)
        for k in (1, 3):
            want = mean_y + slope * (body[k] - mean_x)
            check(abs(sup[k] - want) <= 25, f"{label}: U+{code:04X} {'bottom' if k == 1 else 'top'} is at "
                                            f"{sup[k]:.0f}, not {want:.0f} as the digits")
        ratio = ink_area(font, name) / ink_area(base, base_name)
        check(low * 0.85 <= ratio <= high * 1.15, f"{label}: U+{code:04X} has {ratio:.3f} of the ink of its source")
        program = getattr(font["glyf"][name], "program", None)
        check(program is None or not program.getBytecode(), f"{label}: U+{code:04X} has hinting")
        for char in inputs:
            check(shape(font, char, {"sups"}) == [name], f"{label}: sups of {char} is not U+{code:04X}")

    # 下付きの数字と記号: 上付きの字を同じだけ下げたもの。₍ の下が p の下にそろい、行の下
    # (usWinDescent) からはみ出さない。subs・sinf で、数字と記号がこの字になる
    drops_sub = set()
    pairs_sub = [(0x2080 + d, SUPERSCRIPT_CODES[d], str(d)) for d in range(10)]
    pairs_sub += [(code + 0x10, code, inputs) for code, (_source, inputs) in SUPERSCRIPT_SYMBOLS.items()]
    for code, sup_code, inputs in pairs_sub:
        name = cmap.get(code)
        if name is None:
            problems.append(f"{label}: U+{code:04X} is missing")
            continue
        moved = offset_of(font, name, cmap[sup_code])
        check(moved is not None and moved[0] == 0, f"{label}: U+{code:04X} is not U+{sup_code:04X} moved down")
        if moved is not None:
            drops_sub.add(moved[1])
        check(glyph_bounds(font, name)[1] >= -font["OS/2"].usWinDescent, f"{label}: U+{code:04X} goes below the line")
        check(font["hmtx"][name] == font["hmtx"][cmap[sup_code]], f"{label}: U+{code:04X} is not as wide as U+{sup_code:04X}")
        for char in inputs:
            for tag in ("subs", "sinf"):
                check(shape(font, char, {tag}) == [name], f"{label}: {tag} of {char} is not U+{code:04X}")
    check(len(drops_sub) == 1, f"{label}: the subscripts are moved down by {sorted(drops_sub)}")
    if 0x208D in cmap:
        bottom = glyph_bounds(font, cmap[0x208D])[1] - glyph_bounds(font, cmap[0x70])[1]
        check(abs(bottom) <= 2, f"{label}: ₍ does not reach the bottom of p ({bottom:.0f})")

    # 分子・分母
    numr = {d: shape(font, str(d), {"numr"})[0] for d in range(10)}
    dnom = {d: shape(font, str(d), {"dnom"})[0] for d in range(10)}
    drops = set()
    for d in range(10):
        n, m = offset_of(font, numr[d], sups[d]), offset_of(font, dnom[d], sups[d])
        check(n is not None and n[1] == 0, f"{label}: numr of {d} is not the superscript {d}")
        check(m is not None, f"{label}: dnom of {d} is not the superscript {d} moved down")
        if m is not None:
            drops.add(m[1])
    check(len(drops) == 1, f"{label}: the denominators are moved down by {sorted(drops)}")
    two = glyph_bounds(font, dnom[2])[1] - glyph_bounds(font, digits[2])[1] * 0.5
    check(abs(two) <= 40, f"{label}: the denominator 2 does not sit on the baseline ({two:.0f})")

    # frac: どの字が分子・分母・斜線になるか
    slash = shape(font, "1/2", {"frac"})[1]
    check(slash != cmap[0x2F], f"{label}: frac does not make a fraction slash")
    for text, expect in [("1/2", "nsd"), ("10/25", "nnsdd"), ("1 1/2", "--nsd"), ("and/or", "------"),
                         ("2026", "----"), ("１／２", "nsd"), ("3⁄4", "nsd")]:
        got = shape(font, text, {"frac"})
        kinds = "".join("s" if g == slash else "-" if g == cmap[ord(c)] else
                        fraction_kind(font, g, sups, drops) or "?" for g, c in zip(got, text))
        check(kinds == expect, f"{label}: frac of {text!r} gives {kinds}, not {expect}")
    # ⁄ (U+2044) では、文字を並べる仕組みが分子に numr、分母に dnom、全体に frac をかける
    auto = apply_features(font, [cmap[ord(c)] for c in "12⁄34"],
                          [{"numr", "frac"}, {"numr", "frac"}, {"frac"}, {"dnom", "frac"}, {"dnom", "frac"}])
    check(auto == shape(font, "12/34", {"frac"}), f"{label}: 12⁄34 is not set as 12/34 with frac")
    # 斜線の 0 (zero) と一緒にかけても、分数・上付き・下付きの 0 になること (半角の 0 も全角の ０ も)
    for zero_char in ("0", "０"):
        for tag, want in [("sups", sups[0]), ("subs", cmap[0x2080]), ("sinf", cmap[0x2080]),
                          ("numr", numr[0]), ("dnom", dnom[0])]:
            check(shape(font, zero_char, {"zero", tag}) == [want], f"{label}: zero with {tag} of {zero_char!r}")
    for text in ("10/20", "１０／２０"):
        check(shape(font, text, {"zero", "frac"}) == shape(font, text, {"frac"}),
              f"{label}: zero breaks frac of {text!r}")
    for text, plain_text in [("10⁄20", "10/20"), ("１０⁄２０", "１０／２０")]:
        slashed = apply_features(font, [cmap[ord(c)] for c in text],
                                 [{"zero", "numr", "frac"}, {"zero", "numr", "frac"}, {"zero", "frac"},
                                  {"zero", "dnom", "frac"}, {"zero", "dnom", "frac"}])
        check(slashed == shape(font, plain_text, {"frac"}), f"{label}: zero breaks {text!r}")

    # frac: 数字と斜線のインクの距離 (どの数字の組でも)
    want_before, want_after = fraction_targets(udp)
    worst = []
    for a in range(10):
        for b in range(10):
            glyphs = shape(font, f"{a}/{b}", {"frac"})
            x = 0
            placed = []
            for g in glyphs:
                placed.append(flattened(font, g, x))
                x += font["hmtx"][g][0]
            before, after = ink_gap(placed[0], placed[1]), ink_gap(placed[1], placed[2])
            if abs(before - want_before) > 4 or abs(after - want_after) > 4:
                worst.append(f"{a}/{b} ({before:.0f}, {after:.0f})")
    check(not worst, f"{label}: {len(worst)} fractions are not spaced as BIZ UDP's ({want_before:.0f}, "
                     f"{want_after:.0f}), such as {worst[:3]}")


def cmap_code(cmap: dict, name: str) -> int:
    return next(code for code, g in cmap.items() if g == name)


def fraction_kind(font: TTFont, name: str, sups: dict, drops: set) -> str | None:
    """上付きの数字を横に動かしただけの字なら "n" (分子)、分母の高さまで下げた字なら "d" (分母)"""
    for sup in sups.values():
        moved = offset_of(font, name, sup)
        if moved is not None:
            return "n" if moved[1] == 0 else "d" if moved[1] in drops else None
    return None


def fraction_targets(udp: TTFont) -> tuple[float, float]:
    """BIZ UDP の合成済みの分数の、分子と斜線、斜線と分母のインクの距離の中央値"""
    cmap = udp.getBestCmap()
    befores, afters = [], []
    for code in [0x00BC, 0x00BD, 0x00BE, *range(0x2153, 0x215F)]:
        if code not in cmap:
            continue
        polygons = flattened(udp, cmap[code])
        heights = [max(y for _x, y in p) - min(y for _x, y in p) for p in polygons]
        slash = polygons[heights.index(max(heights))]
        middle = (max(y for _x, y in slash) + min(y for _x, y in slash)) / 2
        rest = [p for p in polygons if p is not slash]
        upper = [p for p in rest if (max(y for _x, y in p) + min(y for _x, y in p)) / 2 > middle]
        lower = [p for p in rest if (max(y for _x, y in p) + min(y for _x, y in p)) / 2 <= middle]
        befores.append(ink_gap(upper, [slash]))
        afters.append(ink_gap([slash], lower))
    return median(befores), median(afters)


# --- 足した文字と palt・vpal ----------------------------------------------------------------

INVISIBLE_CODES = [0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF]
SPACE_WIDTHS = {0x2000: 1 / 2, 0x2001: 1, 0x2002: 1 / 2, 0x2003: 1, 0x2004: 1 / 3, 0x2005: 1 / 4, 0x2006: 1 / 6,
                0x2007: "0", 0x2008: ".", 0x2009: 1 / 5, 0x200A: 1 / 10, 0x202F: 1 / 5, 0x205F: 4 / 18}
EXTRA_CODES = [*INVISIBLE_CODES, *SPACE_WIDTHS, 0x2011, 0x2E3A, 0x2E3B]


def check_extra(label: str, font: TTFont) -> None:
    """見えない文字は幅 0、空白は決まった幅で、どちらもインクが無い。‑ は - と同じ字。⸺ ⸻ は ― を
    2 つ・3 つ横に並べた字で、縦組では縦組の ― を縦に並べた字になる"""
    cmap, em = font.getBestCmap(), font["head"].unitsPerEm
    for code in INVISIBLE_CODES + list(SPACE_WIDTHS):
        name = cmap.get(code)
        if name is None:
            problems.append(f"{label}: U+{code:04X} is missing")
            continue
        width = SPACE_WIDTHS.get(code, 0)
        want = font["hmtx"][cmap[ord(width)]][0] if isinstance(width, str) else round(em * width)
        check(font["hmtx"][name][0] == want, f"{label}: U+{code:04X} is {font['hmtx'][name][0]} wide, not {want}")
        check(font["glyf"][name].numberOfContours == 0, f"{label}: U+{code:04X} has ink")
    check(cmap.get(0x2011) == cmap[0x2D], f"{label}: ‑ is not the glyph of -")
    # 〞 は 〟 を 〝 の高さへ持ち上げた字で、縦組は 〟 の縦組の字
    name, low, high = cmap.get(0x301E), cmap[0x301F], cmap[0x301D]
    if name is None:
        problems.append(f"{label}: U+301E is missing")
    else:
        lift = glyph_bounds(font, high)[1] - glyph_bounds(font, low)[1]
        check(list(map(tuple, outline(font, name)[0])) == [(x, y + lift) for x, y in outline(font, low)[0]],
              f"{label}: 〞 is not 〟 at the height of 〝")
        for tag in ("vert", "vrt2"):
            check(gsub_mapping(font, tag).get(name) == gsub_mapping(font, tag).get(low),
                  f"{label}: {tag} of 〞 is not that of 〟")
        check(name in gpos_values(font, "halt"), f"{label}: 〞 has no halt")
    bar = cmap[0x2015]
    upright = gsub_mapping(font, "vert")[bar]
    for code, count in ((0x2E3A, 2), (0x2E3B, 3)):
        name = cmap.get(code)
        if name is None:
            problems.append(f"{label}: U+{code:04X} is missing")
            continue
        a, b = outline(font, bar), outline(font, name)
        want = [(x + em * k, y) for k in range(count) for x, y in a[0]]
        check(list(map(tuple, b[0])) == want and font["hmtx"][name][0] == em * count,
              f"{label}: U+{code:04X} is not {count} ― in a row")
        for tag in ("vert", "vrt2"):
            vertical = gsub_mapping(font, tag).get(name)
            if vertical is None:
                problems.append(f"{label}: {tag} has no vertical form of U+{code:04X}")
                continue
            c = outline(font, vertical)
            want = [(x, y - em * k) for k in range(count) for x, y in outline(font, upright)[0]]
            check(list(map(tuple, c[0])) == want and font["vmtx"][vertical][0] == em * count,
                  f"{label}: the vertical form of U+{code:04X} is not {count} vertical ― in a column")


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


def check_proportional(label: str, font: TTFont, udp: TTFont) -> None:
    """palt で、仮名・約物・全角の字 (ccmp の半濁点の合字も) が BIZ UDP と同じ位置と字幅になること
    (インクの中心が 1 単位まで)。BIZ UDP と字幅が違い、インクの外形が 20 単位まで同じ字は、どれも palt を持つこと"""
    palt = gpos_values(font, "palt")
    cmap, cmap_udp = font.getBestCmap(), udp.getBestCmap()
    kana_ligs = semi_voiced_kana_ligatures(font, udp)
    check(len(kana_ligs) >= 14, f"{label}: expected at least 14 semi-voiced kana ligatures, found {len(kana_ligs)}")
    candidates = [(chr(code), cmap.get(code), cmap_udp.get(code))
                  for code in [*range(0x3000, 0x3100), *range(0x31F0, 0x3200), *range(0xFF01, 0xFF61)]] + kana_ligs
    wrong, missing = [], []
    for item, name, other in candidates:
        if name is None or other is None or font["glyf"][name].numberOfContours == 0:
            continue
        if font["hmtx"][name] == udp["hmtx"][other] and name not in palt:
            continue
        a, b = glyph_bounds(font, name), glyph_bounds(udp, other)
        alike = (abs((a[2] - a[0]) - (b[2] - b[0])) <= 20 and abs(a[1] - b[1]) <= 20 and abs(a[3] - b[3]) <= 20)
        if name not in palt:
            if alike and (font["hmtx"][name][0] != udp["hmtx"][other][0]
                          or abs((a[0] + a[2]) / 2 - (b[0] + b[2]) / 2) > 1):
                missing.append(item)
            continue
        x, y, x_advance, y_advance = palt[name]
        center = (a[0] + a[2]) / 2 + x - (b[0] + b[2]) / 2
        if y or y_advance or abs(center) > 1 or font["hmtx"][name][0] + x_advance != udp["hmtx"][other][0]:
            wrong.append(item)
    check(len(palt) > 200, f"{label}: palt has only {len(palt)} glyphs")
    check(not wrong, f"{label}: palt does not set {len(wrong)} characters as BIZ UDP, such as {wrong[:5]}")
    check(not missing, f"{label}: {len(missing)} characters lack palt, such as {missing[:5]}")
    for char in "漢字読書":
        check(cmap[ord(char)] not in palt, f"{label}: {char} has palt")


VERTICAL_PROPORTIONAL_CODES = [*range(0x3000, 0x3100), *range(0x31F0, 0x3200), 0xFE45, 0xFE46, *range(0xFF01, 0xFF61)]


def check_proportional_vertical(label: str, font: TTFont, udp: TTFont) -> None:
    """vpal で、仮名・約物・全角の字 (ccmp の半濁点の合字も) の縦組の字が BIZ UDP と同じ縦の位置
    (縦組の原点からのインクの中心が 1 単位まで) と縦の字送りになり、付けるべき字に漏れが無いこと。漢字や結合用の記号には付かないこと"""
    vpal = gpos_values(font, "vpal")
    cmap, cmap_udp = font.getBestCmap(), udp.getBestCmap()
    forms, forms_udp = gsub_mapping(font, "vert"), gsub_mapping(udp, "vert")
    candidates = [(chr(code), cmap.get(code), cmap_udp.get(code)) for code in VERTICAL_PROPORTIONAL_CODES
                  if unicodedata.category(chr(code)) not in ("Mn", "Me")]
    candidates += semi_voiced_kana_ligatures(font, udp)
    wrong, missing = [], []
    for item, name, other in candidates:
        if name is None or other is None:
            continue
        upright, upright_udp = forms.get(name, name), forms_udp.get(other, other)
        a, b = glyph_bounds(font, upright), glyph_bounds(udp, upright_udp)
        if a is None or b is None:
            continue
        origin_a = font["glyf"][upright].yMax + font["vmtx"][upright][1]
        origin_b = udp["glyf"][upright_udp].yMax + udp["vmtx"][upright_udp][1]
        center_a, center_b = (a[1] + a[3]) / 2 - origin_a, (b[1] + b[3]) / 2 - origin_b
        alike = (abs((a[3] - a[1]) - (b[3] - b[1])) <= spec.VERTICAL_SAME_INK
                 and abs((a[2] - a[0]) - (b[2] - b[0])) <= spec.VERTICAL_SAME_INK)
        if upright not in vpal:
            if alike and (font["vmtx"][upright][0] != udp["vmtx"][upright_udp][0] or abs(center_a - center_b) > 1):
                missing.append(item)
            continue
        x, y, xa, ya = vpal[upright]
        centered = abs(center_a + y - center_b) <= 1
        if x or xa or not centered or font["vmtx"][upright][0] + ya != udp["vmtx"][upright_udp][0]:
            wrong.append(item)
    check(len(vpal) > 200, f"{label}: vpal has only {len(vpal)} glyphs")
    check(not wrong, f"{label}: vpal does not set {len(wrong)} characters as BIZ UDP, such as {wrong[:5]}")
    check(not missing, f"{label}: {len(missing)} characters lack vpal, such as {missing[:5]}")
    for char in "漢字読書":
        check(cmap[ord(char)] not in vpal, f"{label}: {char} has vpal")
    for code in combining_codes(cmap):
        check(cmap[code] not in vpal, f"{label}: combining mark U+{code:04X} has vpal")


# --- 等幅の数字・結合用の記号・行からのはみ出し ------------------------------------------------

def combining_codes(cmap: dict) -> list[int]:
    return sorted(code for code in cmap if unicodedata.category(chr(code)) in ("Mn", "Me"))


def moved_by(font: TTFont, name: str, other: TTFont, other_name: str):
    """font の name の輪郭が、other の other_name の輪郭を平行に動かしたものなら、その (dx, dy)"""
    a, b = outline(font, name), outline(other, other_name)
    if a[1:] != b[1:] or not a[0]:
        return None
    dx, dy = a[0][0][0] - b[0][0][0], a[0][0][1] - b[0][0][1]
    return (dx, dy) if all((x - u, y - v) == (dx, dy) for (x, y), (u, v) in zip(a[0], b[0])) else None


def check_tabular(label: str, font: TTFont) -> None:
    """tnum で、数字 0〜9 が同じ字幅になり、狭い字 (1) は形を変えずに左右に同じだけ空きを足したもので
    あること。分数 (frac) と一緒にかけても、分数は変わらないこと"""
    cmap = font.getBestCmap()
    tnum = gsub_mapping(font, "tnum")
    digits = [cmap[0x30 + d] for d in range(10)]
    tabular = [tnum.get(g, g) for g in digits]
    widths = {font["hmtx"][g][0] for g in tabular}
    check(len(widths) == 1, f"{label}: tnum gives digits of the widths {sorted(widths)}")
    width = font["hmtx"][digits[0]][0]
    for g, t in zip(digits, tabular):
        if t == g:
            continue
        extra = width - font["hmtx"][g][0]
        check(moved_by(font, t, font, g) == (extra // 2, 0),
              f"{label}: tnum of {g} is not {g} with {extra // 2} more on each side")
    check(set(tnum) <= set(digits), f"{label}: tnum changes other glyphs than the digits")
    check(shape(font, "1/2", {"frac", "tnum"}) == shape(font, "1/2", {"frac"}),
          f"{label}: tnum changes the fraction 1/2")


def check_colon(label: str, family: dict, weight: str) -> None:
    """数字の間と和文の後のコロン (calt)。HarfBuzz で組んで、前後が数字のときと和文の後で、インクの上下の真ん中が数字の
    真ん中 (中央値) にあり、ヒンティングが無いこと。語の後 (Note:)・字の間 (a:b)・縦組では、元の
    コロン (BIZ UDP の字) のまま"""
    path = FONTS / spec.output_name(family, weight)
    font = TTFont(path)
    shaper = harfbuzz_shape.Shaper(path)
    order, cmap = font.getGlyphOrder(), font.getBestCmap()
    colon = cmap[0x3A]
    middles = sorted((glyph_bounds(font, cmap[0x30 + d])[1] + glyph_bounds(font, cmap[0x30 + d])[3]) / 2
                     for d in range(10))
    middle = (middles[4] + middles[5]) / 2

    def colon_of(text: str, language: str, vertical: bool = False, features=()) -> str:
        index = len(text[:text.index(":")].encode())  # クラスターは UTF-8 のバイトの位置
        return next(order[g] for g, c, *_ in shaper.shape(text, language, vertical, features) if c == index)

    for text, language, features in [("11:11", "ja", ()), ("0213:2004", "en", ()), ("1:2", "en", ("tnum",)),
                                     ("10:01", "en", ("zero",)), ("１１:１１", "ja", ()),
                                     ("１０:０１", "ja", ("zero",)), ("1:１", "ja", ()), ("時刻11:11", "ja", ()),
                                     ("時刻: 11", "ja", ()), ("時刻:", "en", ()), ("カナ:かな", "ja", ())]:
        name = colon_of(text, language, features=features)
        bounds = glyph_bounds(font, name)
        check(name != colon and abs((bounds[1] + bounds[3]) / 2 - middle) <= 1,
              f"{label}: the colon of {text} {list(features)} is not raised to the middle of the digits")
        program = getattr(font["glyf"][name], "program", None)
        check(program is None or not program.getBytecode(), f"{label}: the raised colon has hinting")
    for text, language, vertical in [("Note: 3", "en", False), ("a:b", "en", False), ("1:a", "en", False),
                                     ("1:2", "ja", True), ("１:２", "ja", True)]:
        check(colon_of(text, language, vertical) == colon,
              f"{label}: the colon of {text}{' (vertical)' if vertical else ''} is raised")
    shaper.close()


def mark_attachments(font: TTFont, kind: int) -> list:
    """mark (kind 4) か mkmk (kind 6) の lookup のサブテーブル"""
    gpos = font["GPOS"].table
    tag = "mark" if kind == 4 else "mkmk"
    result = []
    for record in gpos.FeatureList.FeatureRecord:
        if record.FeatureTag == tag:
            for index in record.Feature.LookupListIndex:
                lookup = gpos.LookupList.Lookup[index]
                if lookup.LookupType == kind:
                    result += [s for s in lookup.SubTable if s not in result]
    return result


def attach(font: TTFont, base: str, mark: str, kind: int = 4):
    """base の後の mark の、インクの外形 (base の原点からの位置)。付けられなければ None"""
    for subtable in mark_attachments(font, kind):
        if kind == 4:
            bases, marks = subtable.BaseCoverage.glyphs, subtable.MarkCoverage.glyphs
            records = subtable.BaseArray.BaseRecord
        else:
            bases, marks = subtable.Mark2Coverage.glyphs, subtable.Mark1Coverage.glyphs
            records = subtable.Mark2Array.Mark2Record
        if base not in bases or mark not in marks:
            continue
        mark_array = subtable.MarkArray if kind == 4 else subtable.Mark1Array
        mark_record = mark_array.MarkRecord[marks.index(mark)]
        record = records[bases.index(base)]
        base_anchor = (record.BaseAnchor if kind == 4 else record.Mark2Anchor)[mark_record.Class]
        if base_anchor is None:
            continue
        dx = base_anchor.XCoordinate - mark_record.MarkAnchor.XCoordinate
        dy = base_anchor.YCoordinate - mark_record.MarkAnchor.YCoordinate
        x0, y0, x1, y1 = glyph_bounds(font, mark)
        return x0 + dx, y0 + dy, x1 + dx, y1 + dy
    return None


def check_marks(label: str, font: TTFont, ud: TTFont) -> None:
    """結合用の記号 (アクセント U+0300〜036F と、濁点・半濁点 U+3099・U+309A)。
    - 字幅が 0 で、形は BIZ UD の字を横に動かしただけ。GDEF で記号の字
    - 上の記号は、欧字・ギリシャ文字・キリル文字の上の真ん中に、字に触れずに乗る。下の記号は、
      下の真ん中に付き、ディセンダーのある字では、その下に下がる
    - 上の記号を 2 つ続けると、後の記号は前の記号の上に乗る (mkmk)
    - 濁点・半濁点は、仮名の枠の中で、高さは BIZ UD の字のまま、右の端が合成済みの字 (が など) の
      濁点の右の端の範囲に入る
    - i の後に上の記号が続くと、点の無い ı になる (ccmp)
    - BIZ UD の半角の ´ ｀ ¨ (hwid) は、BIZ UD の字のまま"""
    cmap, cmap_ud = font.getBestCmap(), ud.getBestCmap()
    em = font["head"].unitsPerEm
    if "GDEF" not in font or font["GDEF"].table.GlyphClassDef is None:
        problems.append(f"{label}: no GDEF glyph classes")
        return
    classes = font["GDEF"].table.GlyphClassDef.classDefs
    codes = combining_codes(cmap)
    check(codes == combining_codes(cmap_ud), f"{label}: other combining marks than in BIZ UD")
    for code in codes:
        g = cmap[code]
        check(font["hmtx"][g][0] == 0 and font["vmtx"][g][0] == 0, f"{label}: U+{code:04X} is not of zero width")
        check(classes.get(g) == 3, f"{label}: U+{code:04X} is not a mark in GDEF")
        moved = moved_by(font, g, ud, cmap_ud[code])
        check(moved is not None and moved[1] == 0 and moved[0] < 0,
              f"{label}: U+{code:04X} is not BIZ UD's glyph moved to the left")

    x_height = glyph_bounds(font, cmap[0x78])[3]
    marks_set = {cmap[c] for c in codes}
    bases = [cmap[c] for c in cmap
             if (c in spec.LATIN or 0x0370 <= c <= 0x052F or 0xFF10 <= c <= 0xFF19
                 or 0xFF21 <= c <= 0xFF3A or 0xFF41 <= c <= 0xFF5A)
             and unicodedata.category(chr(c))[0] in "LN" and glyph_bounds(font, cmap[c]) is not None]
    base_set = set(bases)
    for tag in ("tnum", "zero", "hwid", "fwid"):
        for key, target in gsub_mapping(font, tag).items():
            if key in base_set and target not in marks_set and target not in base_set \
                    and glyph_bounds(font, target) is not None:
                bases.append(target)
                base_set.add(target)
    above = [c for c in codes if unicodedata.combining(chr(c)) == 230]
    below = [c for c in codes if unicodedata.combining(chr(c)) == 220]
    for base in bases:
        check(classes.get(base) == 1, f"{label}: {base} is not a base glyph in GDEF")
        bx0, by0, bx1, by1 = glyph_bounds(font, base)
        center = (bx0 + bx1) / 2
        for code in above + below:
            placed = attach(font, base, cmap[code])
            if placed is None:
                problems.append(f"{label}: U+{code:04X} does not attach to {base}")
                continue
            x0, y0, x1, y1 = placed
            check(abs((x0 + x1) / 2 - center) <= 1, f"{label}: U+{code:04X} is not centered on {base}")
            if code in above:
                check(y0 > by1, f"{label}: U+{code:04X} touches {base}")
            else:
                lowered = by0 if by0 < -em / 16 else 0  # ディセンダーのある字だけ、その下へ
                check(abs(y1 - (glyph_bounds(font, cmap[code])[3] + lowered)) <= 1,
                      f"{label}: U+{code:04X} is not under {base}")
    for code in above:
        first = attach(font, cmap[0x6F], cmap[code])
        second = attach(font, cmap[code], cmap[code], 6)
        check(first is not None and second is not None and second[1] + (first[1] - glyph_bounds(font, cmap[code])[1]) > first[3],
              f"{label}: U+{code:04X} does not stack on itself")

    for mark in (0x3099, 0x309A):
        ends = []
        for code in range(0x3041, 0x3100):
            parts = unicodedata.decomposition(chr(code)).split()
            if len(parts) == 2 and int(parts[1], 16) == mark:
                ends.append((int(parts[0], 16), glyph_bounds(font, cmap[code])[2]))
        low, high = min(e for _, e in ends), max(e for _, e in ends)
        design = glyph_bounds(ud, cmap_ud[mark])
        for base_code, _end in ends:
            placed = attach(font, cmap[base_code], cmap[mark])
            if placed is None:
                problems.append(f"{label}: U+{mark:04X} does not attach to U+{base_code:04X}")
                continue
            x0, y0, x1, y1 = placed
            check(0 <= x0 and x1 <= em and low <= x1 <= high and (y0, y1) == (design[1], design[3]),
                  f"{label}: U+{mark:04X} on U+{base_code:04X} is not where the precomposed kana have it")

    # i と上の記号 → ı (ccmp の文脈の置き換え。下の記号などを飛ばす MarkFilteringSet 付き)
    gsub = font["GSUB"].table
    mark_sets = getattr(font["GDEF"].table, "MarkGlyphSetsDef", None)
    i, dotless = cmap[0x69], cmap[0x131]
    want_above = {cmap[c] for c in codes if unicodedata.combining(chr(c)) in (230, 232, 234)}
    found = False
    for index in feature_lookup_indexes(font, {"ccmp"}):
        if lookup_type(gsub, index) != 6:
            continue
        lookup = gsub.LookupList.Lookup[index]
        for subtable in lookup_subtables(gsub, index):
            if (subtable.Format == 3 and i in subtable.InputCoverage[0].glyphs and subtable.LookAheadCoverage
                    and want_above <= set(subtable.LookAheadCoverage[0].glyphs)
                    and (lookup.LookupFlag & 0x0010) and mark_sets is not None
                    and mark_sets.Coverage[lookup.MarkFilteringSet].glyphs == subtable.LookAheadCoverage[0].glyphs):
                found = all(dict(next(iter(lookup_subtables(gsub, r.LookupListIndex))).mapping).get(i) == dotless
                            for r in subtable.SubstLookupRecord)
    check(found, f"{label}: i before marks above does not become dotless with mark filtering")

    # BIZ UD の hwid の置き換え先だった結合用の記号 (半角の ´ ｀ ¨) は、BIZ UD の字のまま
    hwid, hwid_ud = gsub_mapping(font, "hwid"), gsub_mapping(ud, "hwid")
    marks_ud = {cmap_ud[c] for c in codes}
    for key, value in hwid_ud.items():
        if value in marks_ud:
            ours = hwid.get(key)
            check(ours is not None and font["hmtx"][ours] == ud["hmtx"][value] and outline(font, ours) == outline(ud, value),
                  f"{label}: hwid of {key} is not BIZ UD's half-width {value}")


def overflow(font: TTFont, name: str) -> tuple[int, int]:
    """字のインクが、行の上 (usWinAscent) と下 (usWinDescent) から出る量"""
    bounds = glyph_bounds(font, name)
    if bounds is None:
        return 0, 0
    os2 = font["OS/2"]
    return max(0, bounds[3] - os2.usWinAscent), max(0, -os2.usWinDescent - bounds[1])


def check_overflow(label: str, font: TTFont, ud: TTFont, udp: TTFont) -> None:
    """行の上と下 (usWinAscent・usWinDescent。Windows はその外を描かない) からのはみ出しが、元の
    フォントより増えていないこと。BIZ UD の字は、同じ名前の BIZ UD か BIZ UDP の字 (欧字は BIZ UDP の
    字にした) より出ないこと。足した字は、出ないか、元のフォントのはみ出す字をそのまま写したもの。
    縦組の ⸺ ⸻ (下へ 2 em・3 em 伸びる、縦の字送りの向きの字) は除く"""
    order_ud = set(ud.getGlyphOrder())
    names_udp = set(udp.getGlyphOrder())
    cmap = font.getBestCmap()
    vertical_dashes = {gsub_mapping(font, "vert").get(cmap.get(code)) for code in (0x2E3A, 0x2E3B)}
    copies = {}
    for source in (ud, udp):
        for name in source.getGlyphOrder():
            out = overflow(source, name)
            if any(out):
                copies.setdefault(tuple(outline(source, name)[0]), out)
    found = []
    for name in font.getGlyphOrder():
        out = overflow(font, name)
        if not any(out) or name in vertical_dashes:
            continue
        if name in order_ud:
            allowed = [overflow(ud, name)] + ([overflow(udp, name)] if name in names_udp else [])
            ok = any(out[0] <= a[0] and out[1] <= a[1] for a in allowed)
        else:
            source = copies.get(tuple(outline(font, name)[0]))
            ok = source is not None and out[0] <= source[0] and out[1] <= source[1]
        if not ok:
            found.append(name)
    check(not found, f"{label}: {len(found)} glyphs reach farther out of the line than in the original fonts, "
                     f"such as {found[:5]}")


# --- 組んで確かめる (HarfBuzz) ----------------------------------------------------------------

# 組むときに前後に置く字。記号には用字系が無く、前後の字の用字系に入る
JAPANESE_CONTEXTS = [("あ{}あ", "ja"), ("漢{}漢", "ja"), ("{}", "ja")]
LATIN_CONTEXT = ("a{}a", "en")
UNICODE_DATA = Path("/usr/share/unicode")


def unicode_property(name: str, field: str | None = None) -> dict[int, str]:
    """Unicode の文字のデータ (DerivedCoreProperties.txt・VerticalOrientation.txt)。field が None なら、
    その名前の性質を持つ文字 → 名前"""
    path = UNICODE_DATA / name
    if not path.exists():
        raise SystemExit(f"{path} is needed to check the shaping (Debian / Ubuntu: unicode-data)")
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        fields = [f.strip() for f in line.split(";")]
        if field is not None and fields[1] != field:
            continue
        first, _, last = fields[0].partition("..")
        for code in range(int(first, 16), int(last or first, 16) + 1):
            result[code] = fields[1]
    return result


class Shaped:
    """組んだ字を、フォントをまたいで比べられる形にする (グリフの番号はフォントごとに違う)"""

    def __init__(self, path: Path):
        self.font = TTFont(path)
        self.shaper = harfbuzz_shape.Shaper(path)
        self.order = self.font.getGlyphOrder()
        self.outlines: dict[int, tuple] = {}

    def outline_of(self, glyph: int) -> tuple:
        if glyph not in self.outlines:
            coordinates, ends, _flags = outline(self.font, self.order[glyph])
            self.outlines[glyph] = (tuple(coordinates), tuple(ends))
        return self.outlines[glyph]

    def run(self, text: str, language: str, vertical: bool = False, features=(), cluster: int | None = None):
        """元フォントとの比較用。kern を切って (輪郭, 送り x, 送り y, ずれ x, ずれ y) を比べる。
        新しい kern の振る舞いは check_reading_features が、既定で有効なまま別に確かめる。"""
        return [(self.outline_of(g), xa, ya, xo, yo)
                for g, c, xa, ya, xo, yo in self.shaper.shape(text, language, vertical, ("kern=0", *features))
                if cluster is None or c == cluster]

    def run_script(self, text: str, script: str, language: str, vertical: bool) -> list:
        """用字系を指定して組む (ブラウザは、記号を前の字の用字系の組に入れる)"""
        return [(self.outline_of(g), xa, ya, xo, yo)
                for g, _c, xa, ya, xo, yo in self.shaper.shape(text, language, vertical, ("kern=0",), script)]

    def ink(self, text: str, language: str, vertical: bool = False, features=()) -> list:
        """組んだ字のインクの外形 (最初の字の原点から)。インクの無い字は None"""
        x = y = 0
        boxes = []
        for g, _c, xa, ya, xo, yo in self.shaper.shape(text, language, vertical, ("kern=0", *features)):
            bounds = glyph_bounds(self.font, self.order[g])
            boxes.append(None if bounds is None else
                         (bounds[0] + x + xo, bounds[1] + y + yo, bounds[2] + x + xo, bounds[3] + y + yo))
            x, y = x + xa, y + ya
        return boxes

    def close(self) -> None:
        self.shaper.close()


def same_glyph(font: TTFont, name: str, other: TTFont, other_name: str) -> bool:
    return (font["hmtx"][name] == other["hmtx"][other_name] and font["vmtx"][name] == other["vmtx"][other_name]
            and outline(font, name) == outline(other, other_name))


def check_shaping(label: str, family: dict, weight: str) -> None:
    """HarfBuzz で組んで、元のフォントと比べる。フォントの表を読むだけでは分からない、足した機能が元の
    振る舞いを変えてしまう不具合 (デグレ) を見つける。1.002 で GPOS を足して、結合用の記号が前の字に
    乗らなくなり (HarfBuzz の代わりの位置合わせは、GPOS の無いフォントでだけ働く)、1.003 の locl で、
    英語の文の中のソフトハイフンが隠れなくなった (HarfBuzz は、フォントが置き換えた字を隠さない)。

    - 和文の文脈 (横組と縦組): 字を変えていない文字 (欧字・結合用の記号・引用符のほかで、形と字幅が
      BIZ UD と同じ字) は、組んだ結果も BIZ UD と同じ。BIZ UD の GSUB の機能を 1 つずつかけても同じ (分数と
      上付き・下付きの機能は作り直したので除く。check_fractions が確かめる)
    - 引用符とアポストロフィ ‘ ’ “ ” は、和文の中でも日本語の文書でも、横組は BIZ UDP の字、縦組は
      BIZ UDP の縦組の字
    - 縦書き (Chromium のように、字の向きで正立か横倒しかを決めて組む) でも、横書きで BIZ UDP (または
      BIZ UD) と同じに組まれる欧字と記号は、その書体と同じに組まれる
    - BIZ UD の合字 (欧字から始まるものを除く) と異体字 (IVS) の並びは、BIZ UD と同じに組まれる
    - 英語の文脈 (横組): 欧字と欧文の中の記号は、BIZ UDP と同じに組まれる。1 字だけで組んでも (ブラウザ
      が行末に足すハイフンなど) 同じ。縦組で正立する記号
      (Unicode の縦書きの向きが U・Tu・Tr) は、縦組でもインクの位置が BIZ UDP と同じ (1 単位まで)
    - 見えない文字 (Default_Ignorable_Code_Point) は、どの文脈でも幅 0
    - 縦組の vpal で、仮名・約物・全角の字のインクの中心と縦の字送りが BIZ UDP と同じ (1 単位まで)
    - 結合用の記号は、前の字のインクの上か下の真ん中に、触れずに付く (欧字・ギリシャ文字・キリル文字。
      合成済みの字が無い組み合わせ)。濁点・半濁点は、横組でも縦組でも、前の仮名の枠の中に付き、vpal を
      かけても仮名との位置が変わらない"""
    paths = {"ours": FONTS / spec.output_name(family, weight), "ud": SOURCES / f"{family['ud']}-{weight}.ttf",
             "udp": SOURCES / f"{family['udp']}-{weight}.ttf"}
    shaped = {key: Shaped(path) for key, path in paths.items()}
    ours, ud, udp = shaped["ours"], shaped["ud"], shaped["udp"]
    font, font_ud, font_udp = ours.font, ud.font, udp.font
    cmap, cmap_ud, cmap_udp = font.getBestCmap(), font_ud.getBestCmap(), font_udp.getBestCmap()
    marks = set(combining_codes(cmap))
    ignorable = unicode_property("DerivedCoreProperties.txt", "Default_Ignorable_Code_Point")
    orientation = unicode_property("VerticalOrientation.txt")
    found: dict[str, list[str]] = {}

    def report(what: str, item: str) -> None:
        found.setdefault(what, []).append(item)

    # 和文の文脈で、字を変えていない文字
    kept = [code for code in sorted(cmap_ud) if code >= 0x20 and code not in spec.LATIN and code not in marks
            and code not in spec.ALWAYS_UDP and code in cmap and same_glyph(font, cmap[code], font_ud, cmap_ud[code])]
    tags = sorted({r.FeatureTag for r in font_ud["GSUB"].table.FeatureList.FeatureRecord}
                  - {"aalt", *spec.FRACTION_FEATURES})
    for code in kept:
        for context, language in JAPANESE_CONTEXTS:
            text = context.format(chr(code))
            for vertical in (False, True):
                if ours.run(text, language, vertical, cluster=1) != ud.run(text, language, vertical, cluster=1):
                    report(f"in Japanese {'vertical' if vertical else 'horizontal'} text differs from BIZ UD",
                           f"U+{code:04X}")
        text = JAPANESE_CONTEXTS[0][0].format(chr(code))
        for tag in tags:
            for vertical in (False, True):
                if ours.run(text, "ja", vertical, [tag], 1) != ud.run(text, "ja", vertical, [tag], 1):
                    report(f"with {tag} differs from BIZ UD", f"U+{code:04X}{' (vertical)' if vertical else ''}")

    # spec.ALWAYS_UDP は、和文の中でも日本語の文書でも BIZ UDP の字 (Chromium は、和文の後の “Hello の “
    # を和文の組に入れる)。縦組も BIZ UDP の縦組の字 (Chromium は、縦組の引用符を正立させる)
    for code in spec.ALWAYS_UDP:
        expected = udp.run(LATIN_CONTEXT[0].format(chr(code)), "en", cluster=1)
        for context, language in [*JAPANESE_CONTEXTS, (LATIN_CONTEXT[0], "ja"), ("{}", "ja"), ("あ{}", "ja")]:
            text = context.format(chr(code))
            index = context.index("{}")
            cluster = len(context[:index].encode())
            if ours.run(text, language, cluster=cluster) != expected:
                report("always-UDP symbols are not BIZ UDP's in horizontal text", f"U+{code:04X} in {context}")
            if ours.run(text, language, True, cluster=cluster) != udp.run(text, language, True, cluster=cluster):
                report("always-UDP symbols are not BIZ UDP's in vertical text", f"U+{code:04X} in {context}")

    # BIZ UD の合字と異体字
    first_codes = {name: code for code, name in sorted(cmap_ud.items(), reverse=True)}
    always_names = {cmap_ud[code] for code in spec.ALWAYS_UDP}  # dlig の ！！ → ‼ は、locl で BIZ UDP の字になる
    for tag, ligatures in sorted({tag: gsub_ligatures(font_ud, tag) for tag in ("ccmp", "liga", "dlig")}.items()):
        for first, entries in ligatures.items():
            for components, target in entries:
                sequence = [first, *components]
                if not all(g in first_codes for g in sequence) or first_codes[first] in spec.LATIN or target in always_names:
                    continue
                text = "あ" + "".join(chr(first_codes[g]) for g in sequence)
                for vertical in (False, True):
                    if ours.run(text, "ja", vertical, [tag]) != ud.run(text, "ja", vertical, [tag]):
                        report(f"{tag} ligatures differ from BIZ UD", " ".join(f"U+{ord(c):04X}" for c in text[1:]))
    for table in font_ud["cmap"].tables:
        if table.format != 14:
            continue
        for selector, pairs in table.uvsDict.items():
            for base, _glyph in pairs:
                text = chr(base) + chr(selector)
                for vertical in (False, True):
                    if ours.run(text, "ja", vertical) != ud.run(text, "ja", vertical):
                        report("variation sequences differ from BIZ UD", f"U+{base:04X} U+{selector:04X}")

    # 英語の文脈の欧字と記号
    context, language = LATIN_CONTEXT
    for code in sorted(set(spec.LATIN) | set(spec.LATIN_SYMBOLS)):
        if code not in cmap or code not in cmap_udp or code in marks or code in ignorable:
            continue
        text = context.format(chr(code))
        if ours.run(text, language, cluster=1) != udp.run(text, language, cluster=1):
            report("in Latin text differs from BIZ UDP", f"U+{code:04X}")
        # 1 字だけで組む (ブラウザが行末に足すハイフンなど)
        if ours.run(chr(code), language) != udp.run(chr(code), language):
            report("alone in Latin text differs from BIZ UDP", f"U+{code:04X}")
        if orientation.get(code, "R") != "R":
            a, b = ours.ink(text, language, True)[1], udp.ink(text, language, True)[1]
            if (a is None) != (b is None) or (a and any(abs(p - q) > 1 for p, q in zip(a, b))):
                report("upright in vertical Latin text is not placed as in BIZ UDP", f"U+{code:04X}")

    # 縦書き: 横書きで BIZ UDP (または BIZ UD) と同じに組まれる欧字・記号は、縦書きでも同じ書体と同じに
    # 組まれる。Chromium のように、縦書きの向きが R の字は横に倒して横組のまま、U・Tu は正立させて縦組の
    # 機能をかけ、Tr は縦組の字があれば正立させる。引用符 ‘ ’ “ ” は、Chromium が正立させる (Unicode では R)。
    # 用字系は、前の字のものを引き継ぐ
    upright = dict(orientation)
    for code in spec.LATIN_QUOTES:
        upright[code] = "Tu"

    def vertical_run(item: Shaped, char: str, script: str, language: str):
        horizontal = item.run_script(char, script, language, False)
        kind = upright.get(ord(char), "R")
        if kind == "R":
            return horizontal
        shaped_vertically = item.run_script(char, script, language, True)
        if kind == "Tr" and [x[0] for x in shaped_vertically] == [x[0] for x in horizontal]:
            return horizontal
        return shaped_vertically

    def near(a, b) -> bool:
        """同じ字で、位置の違いが丸めの 1 単位まで (字幅の半分で真ん中に置くので)"""
        return a == b or (len(a) == len(b) and all(
            x[0] == y[0] and all(abs(p - q) <= 1 for p, q in zip(x[1:], y[1:])) for x, y in zip(a, b)))

    for code in sorted(set(spec.LATIN) | set(spec.LATIN_SYMBOLS)):
        if code not in cmap or code not in cmap_udp or code not in cmap_ud or code in marks or code in ignorable \
                or unicodedata.category(chr(code)) in ("Cc", "Zs"):
            continue
        char = chr(code)
        for script, language in [("Latn", "en"), ("Latn", "ja"), ("Zyyy", "en"), ("Zyyy", "ja"), ("Hira", "ja"),
                                 ("Hira", "en"), ("Hani", "ja")]:
            if unicodedata.category(char)[0] in "LN" and script != "Latn":
                continue  # 欧字・数字は、いつも欧字の組
            horizontal = ours.run_script(char, script, language, False)
            follows = udp if horizontal == udp.run_script(char, script, language, False) else \
                ud if horizontal == ud.run_script(char, script, language, False) else None
            if follows is not None and not near(vertical_run(ours, char, script, language),
                                                vertical_run(follows, char, script, language)):
                report("in vertical text is not set as in the font it follows horizontally",
                       f"U+{code:04X} ({script} {language})")

    # 見えない文字
    contexts = [*JAPANESE_CONTEXTS, LATIN_CONTEXT]
    for code in sorted(c for c in cmap if c in ignorable):
        for context, language in contexts:
            for vertical in (False, True):
                if any(xa or ya for _o, xa, ya, _xo, _yo in ours.run(context.format(chr(code)), language, vertical, cluster=1)):
                    report("invisible characters are not of zero width", f"U+{code:04X}"
                           f"{' (vertical)' if vertical else ''} after {context[0]}")

    # 縦組の vpal と横組の palt: 仮名・約物・全角の字 (ccmp の半濁点の合字も) のインクの中心と字送り
    forms, forms_udp = gsub_mapping(font, "vert"), gsub_mapping(font_udp, "vert")
    prefix = len("あ".encode())
    vpal_items = [(f"U+{code:04X}", chr(code), forms.get(cmap[code], cmap[code]),
                   forms_udp.get(cmap_udp[code], cmap_udp[code]))
                  for code in VERTICAL_PROPORTIONAL_CODES
                  if code in cmap and code in cmap_udp and code not in marks and code not in ignorable]
    vpal_items += [(item, item, forms.get(name, name), forms_udp.get(other, other))
                   for item, name, other in semi_voiced_kana_ligatures(font, font_udp)]
    for tag_label, seq, up_a, up_b in vpal_items:
        a_box, b_box = glyph_bounds(font, up_a), glyph_bounds(font_udp, up_b)
        if a_box is None or b_box is None:
            continue
        if abs((a_box[3] - a_box[1]) - (b_box[3] - b_box[1])) > spec.VERTICAL_SAME_INK \
                or abs((a_box[2] - a_box[0]) - (b_box[2] - b_box[0])) > spec.VERTICAL_SAME_INK:
            continue
        text = f"あ{seq}あ"
        end = prefix + len(seq.encode())
        shaped_a = [x for x in ours.shaper.shape(text, "ja", True, ("vpal",)) if prefix <= x[1] < end]
        shaped_b = [x for x in udp.shaper.shape(text, "ja", True) if prefix <= x[1] < end]
        if len(shaped_a) != 1 or len(shaped_b) != 1:
            report("with vpal is not a single glyph in vertical text", tag_label)
            continue
        (ga, _ca, xa_a, ya_a, xo_a, yo_a), (gb, _cb, xa_b, ya_b, xo_b, yo_b) = shaped_a[0], shaped_b[0]
        ba, bb = glyph_bounds(font, ours.order[ga]), glyph_bounds(font_udp, udp.order[gb])
        cy = abs((ba[1] + ba[3]) / 2 + yo_a - ((bb[1] + bb[3]) / 2 + yo_b))
        if (xa_a, ya_a, xo_a) != (xa_b, ya_b, xo_b) or cy > 1:
            report("with vpal in vertical text is not placed as in BIZ UDP", tag_label)
    for item, _name, _other in semi_voiced_kana_ligatures(font, font_udp):
        text = f"あ{item}あ"
        end = prefix + len(item.encode())
        shaped_a = [x for x in ours.shaper.shape(text, "ja", False, ("palt",)) if prefix <= x[1] < end]
        shaped_b = [x for x in udp.shaper.shape(text, "ja", False) if prefix <= x[1] < end]
        if len(shaped_a) != 1 or len(shaped_b) != 1:
            report("semi-voiced kana ligature is not a single glyph", item)
            continue
        (ga, _ca, xa_a, ya_a, xo_a, yo_a), (gb, _cb, xa_b, ya_b, xo_b, yo_b) = shaped_a[0], shaped_b[0]
        ba, bb = glyph_bounds(font, ours.order[ga]), glyph_bounds(font_udp, udp.order[gb])
        cx = abs((ba[0] + ba[2]) / 2 + xo_a - ((bb[0] + bb[2]) / 2 + xo_b))
        if (xa_a, ya_a, yo_a) != (xa_b, ya_b, yo_b) or cx > 1:
            report("with palt in horizontal text is not placed as in BIZ UDP", item)

    # 斜線の 0 (zero) と分数・上付き・下付きの組み合わせ (HarfBuzz)
    for text, features, plain_features in [("10/20", ("zero", "frac"), ("frac",)), ("10⁄20", ("zero",), ()),
                                           ("１０／２０", ("zero", "frac"), ("frac",)), ("１０⁄２０", ("zero",), ()),
                                           ("0", ("zero", "sups"), ("sups",)), ("0", ("zero", "subs"), ("subs",)),
                                           ("０", ("zero", "sups"), ("sups",)), ("０", ("zero", "subs"), ("subs",))]:
        if ours.run(text, "en", False, features) != ours.run(text, "en", False, plain_features):
            report("zero breaks fractions or super/subscripts in HarfBuzz", f"{text} {features}")

    # 結合用の記号
    bases = [code for code in sorted(cmap)
             if (code in spec.LATIN or 0x0370 <= code <= 0x052F or 0xFF10 <= code <= 0xFF19
                 or 0xFF21 <= code <= 0xFF3A or 0xFF41 <= code <= 0xFF5A)
             and unicodedata.category(chr(code))[0] in "LN" and glyph_bounds(font, cmap[code]) is not None]
    for mark in sorted(marks):
        combining = unicodedata.combining(chr(mark))
        if combining not in (220, 230):
            continue
        for base in bases:
            text = chr(base) + chr(mark)
            boxes = ours.ink(text, "en")
            if len(boxes) != 2:
                continue  # 合成済みの字になった (é など)
            (bx0, by0, bx1, by1), (mx0, my0, mx1, my1) = boxes
            centered = abs((bx0 + bx1) / 2 - (mx0 + mx1) / 2) <= 1
            clear = my0 > by1 if combining == 230 else my1 < by1
            if not (centered and clear):
                report("combining marks do not sit on the letter", f"U+{base:04X} U+{mark:04X}")
    for base_char, feat in [("1", ("tnum",)), ("0", ("zero",)), ("０", ("zero",)), ("A", ("hwid",)), ("Ａ", ("hwid",))]:
        for mark, above_mark in [(0x030B, True), (0x0325, False)]:
            boxes = ours.ink(base_char + chr(mark), "en", False, feat)
            if len(boxes) != 2 or abs((boxes[0][0] + boxes[0][2]) / 2 - (boxes[1][0] + boxes[1][2]) / 2) > 1 \
                    or (boxes[1][1] <= boxes[0][3] if above_mark else boxes[1][3] >= boxes[0][3]):
                report("combining marks do not sit on substituted bases", f"{base_char} {feat} U+{mark:04X}")
    # i と上の記号 (下の記号を挟んだ i̥̋ や、2 つの字の上にかかる i͡a も) → 点の無い ı
    dotless_id, dotted_id = font.getGlyphID(cmap[0x131]), font.getGlyphID(cmap[0x69])
    for text, above_index in [("i\u030b", 1), ("i\u0325\u030b", 2), ("i\u0361a", 1)]:
        shaped_i = ours.shaper.shape(text, "en")
        boxes = ours.ink(text, "en")
        if shaped_i[0][0] != dotless_id or boxes[above_index][1] <= boxes[0][3]:
            report("i before a mark above does not become dotless cleanly", repr(text))
    # 全角の ｉ も、上の記号の前では点の無い字
    fullwidth_id = font.getGlyphID(cmap[0xFF49])
    if ours.shaper.shape("\uff49\u0301", "en")[0][0] == fullwidth_id:
        report("full-width i before a mark above keeps its dot", "U+FF49 U+0301")
    if ours.shaper.shape("\uff49", "en")[0][0] != fullwidth_id:
        report("full-width i without a mark loses its dot", "U+FF49")
    # 縦組の小書きの仮名は、間にほかの記号があっても濁点と同じ位置に戻る (GPOS の文脈が記号を飛ばす)
    for mark in (0x3099, 0x309A):
        plain, between = ours.shaper.shape(f"っ{chr(mark)}", "ja", True), ours.shaper.shape(f"っ\u0334{chr(mark)}", "ja", True)
        if (plain[0][4:], plain[1][4:]) != (between[0][4:], between[-1][4:]):
            report("small kana do not move for a kana mark after another mark", f"U+{mark:04X}")
    for text in ("i\u0325", "ia\u030b"):
        if ours.shaper.shape(text, "en")[0][0] != dotted_id:
            report("i without a mark above loses its dot", repr(text))

    em = font["head"].unitsPerEm
    for mark in (0x3099, 0x309A):
        for base in [c for c in [*range(0x3041, 0x3100), *range(0x31F0, 0x3200)]
                     if c in cmap and unicodedata.category(chr(c)) == "Lo"]:
            text = chr(base) + chr(mark)
            if unicodedata.normalize("NFC", text) != text:
                continue
            horizontal_boxes = ours.ink(text, "ja", False)
            if len(horizontal_boxes) != 2 or horizontal_boxes[1] is None:
                continue  # 合字になった (か゚ など)
            (hbx0, hby0, hbx1, hby1), (hmx0, hmy0, hmx1, hmy1) = horizontal_boxes
            h_rel = ((hmx0 + hmx1 - hbx0 - hbx1) / 2, (hmy0 + hmy1 - hby0 - hby1) / 2)
            for vertical in (False, True):
                boxes = horizontal_boxes if not vertical else ours.ink(text, "ja", True)
                if len(boxes) != 2 or boxes[1] is None:
                    report("kana marks are lost in vertical text", f"U+{base:04X} U+{mark:04X}")
                    continue
                (bx0, by0, bx1, by1), (mx0, my0, mx1, my1) = boxes
                # 仮名の枠: 横組は (0, -usWinDescent)〜(em, usWinAscent)、縦組は x が -em/2〜em/2、y が -em〜0
                # (HarfBuzz は、縦組の字の位置を、縦組の原点 (枠の上の真ん中) からのずれで返す)
                inside = (-em / 2 <= mx0 and mx1 <= em / 2 and -em <= my0 and my1 <= 0) if vertical else \
                    (0 <= mx0 and mx1 <= em and -font["OS/2"].usWinDescent <= my0 and my1 <= font["OS/2"].usWinAscent)
                if not inside:
                    report("kana marks are not in the box of the kana", f"U+{base:04X} U+{mark:04X}"
                           f"{' (vertical)' if vertical else ''}")
                if vertical:
                    rel = ((mx0 + mx1 - bx0 - bx1) / 2, (my0 + my1 - by0 - by1) / 2)
                    if abs(rel[0] - h_rel[0]) > 1.5 or abs(rel[1] - h_rel[1]) > 1.5:
                        report("kana marks shift on vertical kana", f"U+{base:04X} U+{mark:04X}")
                    vpal_boxes = ours.ink(text, "ja", True, ("vpal",))
                    if len(vpal_boxes) != 2 or vpal_boxes[1] is None \
                            or (vpal_boxes[1][0] - vpal_boxes[0][0], vpal_boxes[1][1] - vpal_boxes[0][1]) != (mx0 - bx0, my0 - by0):
                        report("kana marks do not follow the kana with vpal", f"U+{base:04X} U+{mark:04X}")
    # chws・vchw: 続いた約物だけが詰まり (既定ではかからない)、続いていない括弧は詰まらない
    em_half = font["head"].unitsPerEm // 2
    for tag, vertical in (("chws", False), ("vchw", True)):
        for text, index in (("「『あ", 1), ("あ。」い", 1), ("あ」「い", 1), ("あ、　い", 1), ("・「あ", 1)):
            on = ours.shaper.shape(text, "ja", vertical, (tag,))
            off = ours.shaper.shape(text, "ja", vertical)
            saved = abs(off[index][3 if vertical else 2]) - abs(on[index][3 if vertical else 2])
            if saved != em_half:
                report(f"{tag} does not trim adjacent punctuation by half an em", text)
        for text in ("「あ」", "あ。い"):
            if ours.shaper.shape(text, "ja", vertical, (tag,)) != ours.shaper.shape(text, "ja", vertical):
                report(f"{tag} trims punctuation that is not adjacent", text)
    for item in shaped.values():
        item.close()
    label = spec.output_name(family, weight)
    for what, items in found.items():
        problems.append(f"{label}: {len(items)} {what}, such as {', '.join(items[:5])}")


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
            check(sub.ValueFormat1 in (0, 4) and sub.ValueFormat2 == 0,
                  "kern collision check requires XAdvance-only pair positioning")
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
                check(False, f"unsupported kern pair format: {sub.Format}")
        for pair, amount in pairs.items():
            if amount:
                result[pair] = result.get(pair, 0) + amount
    return {pair: amount for pair, amount in result.items() if amount}


def check_kern_lookup_precedence() -> None:
    """ゼロ値による遮断、Format 1/2 の混在、別 lookup の加算を小さな表で検査する。"""
    from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

    cases = [
        # Format 2 のクラス0のゼロで、後ろの V-a は遮断される。
        ("pos [V] [A] -50; subtable; pos [V] [a] -40;", {("V", "A"): -50}),
        # Format 1 が先に一致するのは、その具体的なペアだけ。
        ("pos V A -50; subtable; pos [V] [a] -40;", {("V", "A"): -50, ("V", "a"): -40}),
        # Format 1 の明示的なゼロ値も後続を遮る。
        ("pos V a 0; subtable; pos [V] [a] -40;", {}),
    ]
    for body, expected in cases:
        font = TTFont()
        font.setGlyphOrder([".notdef", "V", "A", "a"])
        addOpenTypeFeaturesFromString(font, "feature kern { lookup Test { " + body + " } Test; } kern;", tables=["GPOS"])
        check(kerning_pairs(font) == expected, f"kern subtable precedence: {body}")
    font = TTFont()
    font.setGlyphOrder([".notdef", "V", "A", "a"])
    addOpenTypeFeaturesFromString(font, """feature kern {
        lookup First { pos [V] [A] -50; } First;
        lookup Second { pos [V] [a] -40; } Second;
    } kern;""", tables=["GPOS"])
    check(kerning_pairs(font) == {("V", "A"): -50, ("V", "a"): -40}, "kern precedence leaked across lookups")


def check_kern_shaping(label: str, font: TTFont, shaper, family: str, effective=None) -> int:
    """宣言した全ペアを、アクセント付き・除外字を含めて実際に組み、設定値と照合する。

    衝突検査とは別に行う。無効になったペアは衝突しなくても、この検査で不合格になる。
    GPOS の展開結果も HarfBuzz と突き合わせ、サブテーブルの解釈違いを検出する。
    """
    cmap, order = font.getBestCmap(), font.getGlyphOrder()
    variants = {}
    for code in spec.LATIN:
        if code in cmap and unicodedata.category(chr(code)).startswith("L"):
            base = unicodedata.normalize("NFD", chr(code))[0]
            variants.setdefault(base, set()).add(chr(code))
    if effective is None:
        effective = kerning_pairs(font)
    declared = {}
    em = font["head"].unitsPerEm
    for left, right, mincho, gothic in kerning.PAIRS:
        adjustment = kerning.adjustment(em, family, mincho, gothic)
        for a in left:
            for b in right:
                for first in sorted(variants.get(a, ())):
                    for second in sorted(variants.get(b, ())):
                        amount = 0 if first in kerning.EXCLUDED_LEFT else adjustment
                        text = first + second
                        check(text not in declared or declared[text] == amount, f"{label}: conflicting kern declarations for {text}")
                        declared[text] = amount
    wrong = []
    for text, expected in sorted(declared.items()):
        plain = shaper.shape(text, "en", features=("kern=0",))
        kerned = shaper.shape(text, "en")
        actual = sum(r[2] for r in kerned) - sum(r[2] for r in plain)
        if actual != expected:
            wrong.append((text, expected, actual))
        if len(kerned) == 2:
            pair = (order[kerned[0][0]], order[kerned[1][0]])
            check(effective.get(pair, 0) == actual, f"{label}: GPOS expansion disagrees with HarfBuzz on {text}")
    check(bool(declared), f"{label}: no declared kern pairs were shaped")
    check(not wrong, f"{label}: {len(wrong)} declared kern pairs have wrong advances (text, expected, actual): {wrong[:12]}")
    return len(declared)


def outline_distance(left, right, limit: float = math.inf) -> float:
    """折れ線にした２字の輪郭間の最短距離。limit より広い場合は limit を返す。

    同じ高さの水平断面だけでは、水平辺の端や斜めに近づいた角の間隔を見落とす。
    セグメントの包囲矩形で候補を絞り、交差と点・線分間の距離を確かめる。
    """
    def edges(polygons):
        return [(x, y, X, Y, min(x, X), min(y, Y), max(x, X), max(y, Y))
                for polygon in polygons for (x, y), (X, Y) in zip(polygon, polygon[1:] + polygon[:1])]

    def point_distance(x, y, line):
        dx, dy = line[2] - line[0], line[3] - line[1]
        length = dx * dx + dy * dy
        t = max(0, min(1, ((x - line[0]) * dx + (y - line[1]) * dy) / length)) if length else 0
        return (x - line[0] - t * dx) ** 2 + (y - line[1] - t * dy) ** 2

    best = limit * limit
    a, b = edges(left), edges(right)
    for p in a:
        for q in b:
            dx, dy = max(p[4] - q[6], q[4] - p[6], 0), max(p[5] - q[7], q[5] - p[7], 0)
            if dx * dx + dy * dy >= best:
                continue
            ax, ay, bx, by = p[2] - p[0], p[3] - p[1], q[2] - q[0], q[3] - q[1]
            determinant = ax * by - ay * bx
            if determinant:
                ox, oy = q[0] - p[0], q[1] - p[1]
                t, u = (ox * by - oy * bx) / determinant, (ox * ay - oy * ax) / determinant
                if 0 <= t <= 1 and 0 <= u <= 1:
                    return 0.0
            best = min(best, point_distance(p[0], p[1], q), point_distance(p[2], p[3], q),
                       point_distance(q[0], q[1], p), point_distance(q[2], q[3], p))
    return math.sqrt(best)


def check_outline_distance() -> None:
    a = [[(0, 0), (10, 0), (10, 10), (0, 10)]]
    diagonal = [[(20, 20), (30, 20), (30, 30), (20, 30)]]
    crossing = [[(5, 5), (15, 5), (15, 15), (5, 15)]]
    touching = [[(10, 0), (20, 0), (20, 10), (10, 10)]]
    check(abs(outline_distance(a, diagonal) - math.sqrt(200)) < 1e-6, "diagonal ink distance was not checked")
    check(outline_distance(a, diagonal, 5) == 5, "ink distance limit is not respected")
    check(outline_distance(a, crossing) == 0 and outline_distance(a, touching) == 0,
          "crossing or touching outlines were not detected")


def check_kern_contacts(label: str, font: TTFont, pairs=None) -> int:
    """全ペアの水平断面と輪郭間の最短距離を調べ、アクセントや角の近接も検査する。"""
    if pairs is None:
        pairs = kerning_pairs(font)
    minimum = font["head"].unitsPerEm / 100  # 1% em。接触していなくても極端に狭いペアは不合格。
    profiles, outlines = {}, {}
    for glyph in sorted({g for pair in pairs for g in pair}):
        polygons = flattened(font, glyph)
        outlines[glyph] = polygons
        ys = [y for polygon in polygons for _x, y in polygon]
        profile = {}
        for y in range(int(min(ys)) - 1, int(max(ys)) + 2):
            xs = row(polygons, y + 0.5)
            if xs:
                profile[y] = (xs[0], xs[-1])
        profiles[glyph] = profile
    bad = []
    for (first, second), amount in pairs.items():
        left, right = profiles[first], profiles[second]
        rows = left.keys() & right.keys()
        advance = font["hmtx"][first][0] + amount
        gap = min((advance + right[y][0] - left[y][1] for y in rows), default=math.inf)
        shifted = [[(x + advance, y) for x, y in polygon] for polygon in outlines[second]]
        gap = min(gap, outline_distance(outlines[first], shifted, minimum))
        if gap < minimum:
            bad.append((first, second, round(gap, 2)))
    check(bool(pairs), f"{label}: no kern pairs were checked")
    check(not bad, f"{label}: {len(bad)} of {len(pairs)} kern pairs have less than {minimum:.2f} units of ink space: {bad[:8]}")
    return len(pairs)


def check_small_digit_outlines(label: str, font: TTFont, glyphs: set[str], path: Path) -> None:
    """複数輪郭の内側も外側と同じ縦方向の変形かを、FreeType の適用後の点で確かめる。

    26.6 座標の丸め誤差は２単位 (1/32 px) まで許す。カウンターが動かない旧実装は、
    分母の0などで12〜24単位以上ずれるため、この検査で検出できる。
    """
    cases = []
    for name in sorted(glyphs):
        glyph = font["glyf"][name]
        if glyph.numberOfContours <= 1:
            continue
        coords = glyph.getCoordinates(font["glyf"])[0]
        bottom = min(range(len(coords)), key=lambda i: coords[i][1])
        top = max(range(len(coords)), key=lambda i: coords[i][1])
        cases.append((name, font.getGlyphID(name), bottom, top))
    check(bool(cases), f"{label}: no multi-contour small digits were checked")
    for mode, interpreter, flags in freetype_render.MODES:
        hinted = freetype_render.Renderer(path, interpreter, flags)
        plain = freetype_render.Renderer(path, interpreter, flags | freetype_render.NO_HINTING)
        bad = []
        for ppem in range(8, 25):
            for name, gid, bottom, top in cases:
                original, fitted = plain.outline(gid, ppem), hinted.outline(gid, ppem)
                y0, y1 = original[bottom][1], original[top][1]
                low, high = fitted[bottom][1], fitted[top][1]
                deviation = max(abs(y - (low + (original[i][1] - y0) * (high - low) / (y1 - y0)))
                                for i, (_x, y) in enumerate(fitted))
                if deviation > 2:
                    bad.append((name, ppem, round(deviation, 2)))
        check(not bad, f"{label}: {mode}: {len(bad)} small-digit outlines distort their counters: {bad[:5]}")
        hinted.close()
        plain.close()


def check_small_digit_alignment(label: str, font: TTFont, shaper, path: Path, source: Path) -> None:
    """各 ppem で同じ役割の数字の上下端が一致するか、輪郭とラスタの両方で確かめる。

    上付き¹²³⁴は元のヒントを保つ対照群として元フォントと画素比較し、追加６字とは分ける。
    """
    groups = {}
    for tag in ("dnom", "numr", "subs", "sups"):
        shaped = shaper.shape("0123456789", "en", features=(tag,))
        groups[tag] = {r[0] for d, r in enumerate(shaped) if tag != "sups" or d not in (1, 2, 3, 4)}
    # 分数の斜線に接する専用字形も、普通の分子・分母と同じ上下位置であること。
    for d in range(10):
        fraction = shaper.shape(f"{d}/{d}{d}", "en", features=("frac",))
        check(len(fraction) == 4, f"{label}: unexpected fraction glyphs for {d}/{d}{d}")
        if len(fraction) == 4:
            groups["numr"].add(fraction[0][0])
            groups["dnom"].update(r[0] for r in fraction[2:])
    for mode, interpreter, flags in freetype_render.MODES:
        ours = freetype_render.Renderer(path, interpreter, flags)
        original = freetype_render.Renderer(source, interpreter, flags)
        bad = []
        for ppem in range(8, 25):
            for tag, glyphs in groups.items():
                outlines, rasters = set(), set()
                for gid in glyphs:
                    ys = [y for _x, y in ours.outline(gid, ppem)]
                    outlines.add((min(ys), max(ys)))
                    bitmap = ours.render(gid, ppem)
                    rasters.add((bitmap[1] - bitmap[4], bitmap[1]))
                if len(outlines) != 1 or len(rasters) != 1 or (tag == "dnom" and next(iter(outlines))[0] != 0):
                    bad.append((tag, ppem, sorted(outlines), sorted(rasters)))
            for code in (0x00B9, 0x00B2, 0x00B3, 0x2074):
                check(ours.render(ours.char_index(code), ppem) == original.render(original.char_index(code), ppem),
                      f"{label}: original superscript U+{code:04X} changed at {ppem} ({mode})")
        check(not bad, f"{label}: {mode}: inconsistent small-digit baselines/heights: {bad[:8]}")
        ours.close()
        original.close()


STYLE_MODES = ((False, ()), (True, ()), (True, ("vert=0", "vrt2")))


def check_style_widths(label: str, font: TTFont, shaper) -> int:
    """記号の全対象字を実際に組み、ss02 が明示した幅・字形・縦組位置を変えないこと。"""
    cmap = font.getBestCmap()
    codes = [code for code in spec.LATIN_SYMBOLS if code in cmap and code not in spec.LATIN_QUOTES
             and unicodedata.category(chr(code)) != "Cf"]
    bad, count = [], 0
    for code in codes:
        for language in ("ja", "en"):
            for context in ("{}", "字{}字", "A{}A"):
                text = context.format(chr(code))
                for vertical, vertical_features in STYLE_MODES:
                    for tag in ("hwid", "fwid"):
                        plain = shaper.shape(text, language, vertical, (tag, *vertical_features))
                        styled = shaper.shape(text, language, vertical, (tag, "ss02", *vertical_features))
                        if plain != styled:
                            bad.append((f"U+{code:04X}", language, context, vertical, vertical_features, tag))
                        count += 1
    check(bool(count), f"{label}: no style/width combinations were checked")
    check(not bad, f"{label}: {len(bad)} ss02 combinations override explicit widths: {bad[:8]}")
    return count


def check_style_copies(label: str, ours: Shaped, udp: Shaped, path: Path, source_path: Path) -> None:
    """各複製を対応する文字・縦組経路の UDP 字形に照合し、未符号化の候補も描いて比べる。"""
    font = ours.font
    clones = vertical_closure(font, outputs(font, ("ss02",)))
    originals = vertical_closure(font, outputs(font, ("locl",)))
    check(bool(clones) and not clones & originals, f"{label}: ss02 copies are not isolated from locl")
    covered, pairs = set(), {}
    cmap, cmap_udp = font.getBestCmap(), udp.font.getBestCmap()
    unhinted = {cmap_udp[code] for code in spec.UNHINTED if code in cmap_udp}
    local = gsub_mapping(font, "locl")
    forms = {tag: gsub_mapping(font, tag) for tag in ("vert", "vrt2")}
    definitions = [getattr(font["GDEF"].table, field, None)
                   for field in ("GlyphClassDef", "MarkAttachClassDef")]

    def classes(name):
        return tuple(definition.classDefs.get(name, 0) if definition is not None else 0 for definition in definitions)

    for code in spec.LATIN_SYMBOLS:
        if code not in cmap or code not in cmap_udp or code in spec.LATIN_QUOTES or unicodedata.category(chr(code)) == "Cf":
            continue
        for vertical, features in STYLE_MODES:
            normal = cmap[code]
            if vertical:
                form = forms["vrt2" if features else "vert"]
                normal = form.get(normal, normal)
            normal = local.get(normal, normal)
            if vertical:
                normal = form.get(normal, normal)
            # 通常の locl が先に変える ALWAYS_UDP の専用複製も、直接選んで検査する。
            actual = ours.shaper.shape(chr(code), "ja", vertical, ("locl=0", "ss02", *features))
            wanted = udp.shaper.shape(chr(code), "ja", vertical, features)
            check(len(actual) == len(wanted), f"{label}: ss02 copy count differs for U+{code:04X} {features}")
            for a, b in zip(actual, wanted):
                name, source = ours.order[a[0]], udp.order[b[0]]
                if name not in clones:
                    continue
                covered.add(name)
                check(classes(name) == classes(normal),
                      f"{label}: ss02 changed GDEF classes for U+{code:04X} {features}")
                check(outline(font, name) == outline(udp.font, source)
                      and font["hmtx"][name] == udp.font["hmtx"][source]
                      and font["vmtx"][name] == udp.font["vmtx"][source],
                      f"{label}: ss02 copy of U+{code:04X} {features} is not the corresponding UDP glyph")
                if source not in unhinted:
                    pairs[(a[0], b[0])] = f"U+{code:04X} {features}"
    check(not clones - covered, f"{label}: ss02 copies have no character/path correspondence: {sorted(clones - covered)[:8]}")
    for mode, interpreter, flags in freetype_render.MODES:
        actual = freetype_render.Renderer(path, interpreter, flags)
        reference = freetype_render.Renderer(source_path, interpreter, flags)
        bad = [(description, ppem) for (gid, source), description in pairs.items() for ppem in HINTING_PPEMS
               if actual.render(gid, ppem) != reference.render(source, ppem)]
        check(not bad, f"{label}: {mode}: ss02 copies differ from corresponding UDP rasters: {bad[:6]}")
        actual.close()
        reference.close()


def check_kern_exclusions(label: str, font: TTFont, pairs: dict) -> None:
    """kern の入力字が、固定幅・縦組への置換先と重ならないことを表全体で検査する。"""
    inputs = {glyph for pair in pairs for glyph in pair}
    for tag in ("hwid", "fwid", "tnum", "vert", "vrt2"):
        overlap = inputs & outputs(font, (tag,))
        check(not overlap, f"{label}: kern includes {tag} output glyphs: {sorted(overlap)[:8]}")


def check_reading_features(label: str, family: dict, weight: str) -> None:
    """新しい組版機能は元との一致とは別に、実際の組み方と衝突・小サイズの画素で検査する。"""
    path = FONTS / label
    font = TTFont(path)
    shaper = harfbuzz_shape.Shaper(path)
    em, cmap = font["head"].unitsPerEm, font.getBestCmap()
    order = font.getGlyphOrder()

    def run(text, features=(), vertical=False):
        return shaper.shape(text, "ja", vertical, features)

    def width(text, features=()):
        return sum(r[2] for r in run(text, features))

    effective_kern = kerning_pairs(font)
    check_kern_shaping(label, font, shaper, family["key"], effective_kern)
    check_kern_contacts(label, font, effective_kern)
    check_kern_exclusions(label, font, effective_kern)
    problems.extend(width_reference.check_recorded(label, font, shaper))
    check_style_widths(label, font, shaper)
    for text in ("Ťu", "Ťü", "T\u030cu", "T\u0330\u030cu", "ĽT"):
        check(run(text) == run(text, ("kern=0",)), f"{label}: projecting caron is kerned in {text}")
    for text in ("AV", "WA", "To", "Te", "YA", "LT", "Tó", "ÁV"):
        plain, kerned = run(text, ("kern=0",)), run(text)
        check(width(text) < width(text, ("kern=0",)), f"{label}: kern does not tighten {text}")
        check(width(text, ("kern=0",)) - width(text) <= em / 8, f"{label}: excessive kern on {text}")
        if len(kerned) == 2:
            left, right = kerned
            gap = ink_gap(flattened(font, order[left[0]], left[4], left[5]),
                          flattened(font, order[right[0]], left[2] + right[4], right[5]))
            check(gap is not None and gap > em / 50, f"{label}: kern makes {text} touch ({gap})")
        check([r[0] for r in plain] == [r[0] for r in kerned], f"{label}: kern changes glyphs of {text}")
    for text, features in [("漢字かな", ()), ("AV To", ("hwid",)), ("ＡＶ", ()),
                            ("AV To", ("fwid",)), ("0123456789", ("tnum",))]:
        check(run(text, features) == run(text, (*features, "kern=0")), f"{label}: kern changes fixed widths of {text}")
    check(run("AV To", vertical=True) == run("AV To", ("kern=0",), True), f"{label}: kern affects vertical text")
    # IgnoreMarks: 合成済みの字と、結合記号が残る字の両方で、基底字間に同じ詰めを適用する。
    for text in ("To", "Tõ", "Tő", "T̃o"):
        check(width(text, ("kern=0",)) - width(text) == width("To", ("kern=0",)) - width("To"),
              f"{label}: accents change the kern amount in {text}")
    for features in [("pnum",), ("tnum", "pnum"), ("zero", "tnum", "pnum")]:
        plain = ("zero",) if "zero" in features else ()
        check(run("0123456789", features) == run("0123456789", plain), f"{label}: pnum does not restore proportional digits")
    for text in ("1/2", "10/25"):
        check(run(text, ("frac", "tnum", "pnum")) == run(text, ("frac",)), f"{label}: numeric widths alter {text}")
    ours = Shaped(path)
    ud = Shaped(SOURCES / f"{family['ud']}-{weight}.ttf")
    udp_path = SOURCES / f"{family['udp']}-{weight}.ttf"
    udp = Shaped(udp_path)
    check_style_copies(label, ours, udp, path, udp_path)
    cmap_udp = udp.font.getBestCmap()
    # chws/vchw と halt/vhal を明示的に有効にして二重詰めを再現し、安全な指定と区別する。
    text = "「春、（花）・風。」"
    for vertical, proportional, contextual, half in [(False, "palt", "chws", "halt"),
                                                     (True, "vpal", "vchw", "vhal")]:
        safe = (proportional, contextual + "=0", half + "=0")
        positioned, reference = ours.run(text, "ja", vertical, safe), udp.run(text, "ja", vertical)
        # BIZ UDP は輪郭そのものを移動した字を持つので、輪郭と placement の生値ではなく、
        # 実際の送りとインクの中心を比べる。縦組の括弧などの輪郭寸法の違いは許す。
        check([r[1:3] for r in positioned] == [r[1:3] for r in reference],
              f"{label}: safe {proportional} advances differ from BIZ UDP")
        ink, reference_ink = ours.ink(text, "ja", vertical, safe), udp.ink(text, "ja", vertical)
        check(len(ink) == len(reference_ink) and all(
            a is not None and b is not None and all(abs((a[k] + a[k+2] - b[k] - b[k+2]) / 2) <= 1 for k in (0, 1))
            for a, b in zip(ink, reference_ink)), f"{label}: safe {proportional} positions differ from BIZ UDP")
        a = run(text, safe, vertical)
        safe_advance = sum(abs(r[3]) if vertical else r[2] for r in a)
        check(all(abs(r[3]) > 0 if vertical else r[2] > 0 for r in a),
              f"{label}: safe proportional spacing has non-positive advances")
        for incompatible in (contextual, half):
            b = run(text, (proportional, incompatible), vertical)
            double_advance = sum(abs(r[3]) if vertical else r[2] for r in b)
            check(double_advance < safe_advance and a != b,
                  f"{label}: {proportional}+{incompatible} did not reproduce double trimming")
    for language in ("ja", "en"):
        for vertical, vertical_features in STYLE_MODES:
            for char in "‘’“”":
                check(ours.run(char, language, vertical, ("ss01", *vertical_features)) == ud.run(char, language, vertical, vertical_features),
                      f"{label}: ss01 {char} is not BIZ UD ({language}, vertical={vertical})")
                check(ours.run(char, language, vertical, ("ss01", "ss02", *vertical_features)) == ours.run(char, language, vertical, ("ss01", *vertical_features)),
                      f"{label}: ss02 overrides ss01 quotes")
            for code in spec.LATIN_SYMBOLS:
                if (code not in cmap or code not in cmap_udp or code in spec.LATIN_QUOTES
                        or unicodedata.category(chr(code)) == "Cf"):
                    continue
                char = chr(code)
                check(ours.run(char, language, vertical, ("ss02", *vertical_features)) == udp.run(char, language, vertical, vertical_features),
                      f"{label}: ss02 U+{code:04X} is not BIZ UDP ({language}, vertical={vertical}, {vertical_features})")
    for tag in ("ss01", "ss02", "ss03"):
        for record in font["GSUB"].table.FeatureList.FeatureRecord:
            if record.FeatureTag == tag:
                params = record.Feature.FeatureParams
                check(params is not None and font["name"].getDebugName(params.UINameID), f"{label}: {tag} has no label")
    for char in small_type.RUBY_KANA:
        for vertical in (False, True):
            a, b = run(char, (), vertical), run(char, ("ss03",), vertical)
            check(len(a) == len(b) == 1 and a[0][0] != b[0][0], f"{label}: ss03 lacks {char}")
            check(a[0][2:] == b[0][2:], f"{label}: trial ruby changes the frame of {char}")
            bounds = glyph_bounds(font, order[b[0][0]])
            check(bounds is not None and not any(overflow(font, order[b[0][0]])), f"{label}: trial ruby {char} clips")
    check(run("漢字さしすせそ", ("ss03",)) == run("漢字さしすせそ"), f"{label}: ss03 changes unselected characters")
    trial = gsub_mapping(font, "ss03")
    for tag, vertical in (("palt", False), ("vpal", True)):
        values = gpos_values(font, tag)
        for source, target in trial.items():
            check(values.get(source) == values.get(target), f"{label}: trial ruby does not inherit {tag} of {source}")
        for text in (small_type.RUBY_KANA, "漢あ字め"):
            a, b = run(text, (tag,), vertical), run(text, (tag, "ss03"), vertical)
            check([r[2:] for r in a] == [r[2:] for r in b], f"{label}: ss03 changes {tag} spacing of {text}")
    for tag in ("vert", "vrt2"):
        vertical = gsub_mapping(font, tag)
        for source, upright in vertical.items():
            if source in trial and upright in trial:
                check(vertical.get(trial[source]) == trial[upright], f"{label}: trial ruby lacks {tag} of {source}")
    # 元のフォントの数字は固有のヒントを持つので除き、生成した数字を分数の端用字形まで集める。
    generated = (outputs(font, spec.FRACTION_FEATURES) | {cmap[c] for c in (0x2070, *range(0x2075, 0x207A))})
    generated -= set(ud.font.getGlyphOrder())
    generated_digits = {name for name in generated if font["glyf"][name].numberOfContours > 1}
    check_small_digit_outlines(label, font, generated_digits, path)
    check_small_digit_alignment(label, font, shaper, path, SOURCES / f"{family['udp']}-{weight}.ttf")
    # 生成した数字のヒントは、8–24 ppem の全描画モードで、消失や上下の潰れを起こさない。
    digit_glyphs = {r[0] for tag in ("sups", "subs", "numr", "dnom") for r in run("0123456789", (tag,))}
    for mode, interpreter, flags in freetype_render.MODES:
        renderer = freetype_render.Renderer(path, interpreter, flags)
        for ppem in range(8, 25):
            for gid in digit_glyphs:
                bitmap = renderer.render(gid, ppem)
                check(bitmap[4] >= 2 and any(bitmap[5]), f"{label}: small digit {gid} collapses at {ppem} ({mode})")
        renderer.close()
    for item in (ours, ud, udp):
        item.close()
    shaper.close()


def check_woff2(family: dict, weight: str) -> None:
    """WOFF2 の中身が TTF と同じであること。glyf・loca は圧縮のときに形式が変わるので字ごとに比べ、
    head は圧縮の印 (flags の bit 11) とチェックサムのほかを比べる。ほかの表はバイト列で比べる"""
    ttf_path = FONTS / spec.output_name(family, weight)
    woff2_path = ttf_path.with_suffix(".woff2")
    label = woff2_path.name
    if not woff2_path.exists():
        problems.append(f"{label}: missing")
        return
    ttf, woff2 = TTFont(ttf_path), TTFont(woff2_path)
    check(woff2.flavor == "woff2", f"{label}: not WOFF2")
    tags, woff2_tags = set(ttf.reader.keys()), set(woff2.reader.keys())
    check(tags == woff2_tags, f"{label}: tables differ from the TTF: {sorted(tags ^ woff2_tags)}")
    for tag in sorted(tags & woff2_tags - {"glyf", "loca", "head"}):
        check(ttf.getTableData(tag) == woff2.getTableData(tag), f"{label}: {tag} differs from the TTF")

    def head_fields(font: TTFont) -> bytes:
        data = bytearray(font.getTableData("head"))
        data[8:12] = bytes(4)  # checkSumAdjustment
        data[16] &= ~0x08  # flags の bit 11
        return bytes(data)

    check(head_fields(ttf) == head_fields(woff2), f"{label}: head differs from the TTF")
    check(ttf.getGlyphOrder() == woff2.getGlyphOrder(), f"{label}: the glyph order differs from the TTF")

    def glyph_data(font: TTFont, name: str):
        table = font["glyf"]
        glyph = table[name]
        coordinates, ends, flags = glyph.getCoordinates(table)
        program = glyph.program.getBytecode() if hasattr(glyph, "program") else b""
        return list(coordinates), list(ends), [flag & 1 for flag in flags], bytes(program)

    differ = [name for name in ttf.getGlyphOrder() if glyph_data(ttf, name) != glyph_data(woff2, name)]
    check(not differ, f"{label}: {len(differ)} glyphs differ from the TTF, such as {', '.join(differ[:5])}")


def check_license() -> None:
    """OFL.txt の著作権表示が、元のフォントの中の著作権表示 (name ID 0) と同じであること。
    元の配布物の OFL.txt には、BIZ UDゴシックの行に BIZ UD明朝のリポジトリの URL を書いた
    誤りがある。フォントの中の表示を正しいものとして突き合わせる"""
    lines = (ROOT / "OFL.txt").read_text(encoding="utf-8").splitlines()
    for family in spec.FAMILIES:
        notice = TTFont(SOURCES / f"{family['ud']}-Regular.ttf")["name"].getDebugName(0)
        check(notice in lines, f"OFL.txt: the copyright line of {family['source_name']} is not {notice!r}")
    check(spec.COPYRIGHT in lines, "OFL.txt: our copyright line is missing")


def main() -> int:
    check_kern_lookup_precedence()
    check_outline_distance()
    check_license()
    for family in spec.FAMILIES:
        for weight in spec.WEIGHTS:
            check_font(family, weight)
            check_woff2(family, weight)
    if problems:
        print("\n".join(problems[:50]))
        print(f"{len(problems)} problem(s)")
        return 1
    print(f"ok: {len(spec.FAMILIES) * len(spec.WEIGHTS)} fonts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
