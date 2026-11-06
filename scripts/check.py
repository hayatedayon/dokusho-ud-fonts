"""fonts/ の読書 UD を、元の BIZ UD・BIZ UDP と突き合わせて確かめる。

build.py とは別の書き方で、できたものだけを見る。1 つでも合わなければ 1 で終わる。
"""

import sys
import unicodedata
from pathlib import Path
from statistics import median

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont

import freetype_render
import spec

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
    check(remapped <= shared_marks and set(added) == set(NEW_SUPERSCRIPTS) | set(EXTRA_CODES),
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
    fraction_glyphs |= outputs(font, ["tnum"]) | {cmap[code] for code in remapped}
    check(extra == set(latin_symbol_mapping(font, "latn", None).values()) | half_widths | fraction_glyphs,
          f"{label}: glyphs other than the symbols for Latin text, the half widths for hwid and the fraction "
          "digits were added")

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
    check(ours_hwid.keys() == expected.keys(), f"{label}: hwid covers {len(ours_hwid)} glyphs, not {len(expected)}")
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
    check_latin_symbols(label, font, ud, udp)
    check_hinting(label, font, family, weight, latin_targets(udp, latin_glyphs), udp, ud)
    check_spacing(label, font)
    check_fractions(label, font, udp)
    check_extra(label, font)
    check_proportional(label, font, udp)
    check_tabular(label, font)
    check_marks(label, font, ud)
    check_overflow(label, font, ud, udp)


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


def latin_symbol_mapping(font: TTFont, script: str, language: str | None) -> dict:
    """その用字系・言語体系で働く locl の置き換え"""
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
    return mapping


def drawing(font: TTFont, name: str) -> list:
    pen = DecomposingRecordingPen(font.getGlyphSet())
    font.getGlyphSet()[name].draw(pen)
    return pen.value


def check_latin_symbols(label: str, font: TTFont, ud: TTFont, udp: TTFont) -> None:
    """欧文の中の記号。できたフォントと BIZ UDP で違う記号は、欧字の用字系 (latn) の既定でだけ BIZ UDP の
    字 (形と字幅) に置き換わり、日本語 (latn の JAN) と和文の用字系では置き換わらないこと"""
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
    for script, language in [("latn", "JAN "), ("hani", None), ("kana", None), ("DFLT", None)]:
        check(not latin_symbol_mapping(font, script, language),
              f"{label}: symbols are substituted in {script} {language or 'dflt'}")


# 描いて比べる大きさ (1 em の画素の数)。ヒンティングが効くのは小さな大きさ
HINTING_PPEMS = range(8, 25)


def check_hinting(label: str, font: TTFont, family: dict, weight: str, targets: dict[str, str],
                  udp_font: TTFont, ud_font: TTFont) -> None:
    """BIZ UDP から持ってきた字のヒンティングが BIZ UDP と同じで、和文のヒンティングが BIZ UD と
    同じこと。FreeType でヒンティングを動かして描き、画素を比べる (hinting.py が cvt の番号を
    ずらし損ねていれば、字の形がずれる)"""
    paths = {"ours": FONTS / label, "ud": SOURCES / f"{family['ud']}-{weight}.ttf",
             "udp": SOURCES / f"{family['udp']}-{weight}.ttf"}
    cmap = font.getBestCmap()
    symbols = latin_symbol_mapping(font, "latn", None)
    by_name = {name: code for code, name in cmap.items()}
    for mode, interpreter, flags in freetype_render.MODES:
        renderers = {key: freetype_render.Renderer(path, interpreter, flags) for key, path in paths.items()}
        ours, ud, udp = renderers["ours"], renderers["ud"], renderers["udp"]
        # (何を, 読書 UD のグリフの番号, 比べる相手, 相手のグリフの番号)
        # BIZ UDP のヒンティングを付けない字 (spec.UNHINTED) は、BIZ UDP と同じには描かれない
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
        order_ud = set(ud_font.getGlyphOrder())
        ud_hwid = gsub_mapping(ud_font, "hwid")
        half_widths = {half: ud_hwid.get(key, key) for key, half in gsub_mapping(font, "hwid").items()
                       if half not in order_ud}
        check(half_widths, f"{label}: no half widths for hwid to draw")
        cases += [(f"{name} (hwid of {source})", font.getGlyphID(name), ud, ud_font.getGlyphID(source))
                  for name, source in sorted(half_widths.items())]
        differ = []
        for what, ours_index, other, other_index in cases:
            for ppem in HINTING_PPEMS:
                if ours.render(ours_index, ppem) != other.render(other_index, ppem):
                    differ.append(f"{what} at {ppem} ppem")
        check(not differ, f"{label}: {mode}: {len(differ)} glyphs are not drawn as in BIZ UD / BIZ UDP, "
                          f"such as {differ[:3]}")
        for renderer in renderers.values():
            renderer.close()
        check_nothing_vanishes(label, font, mode, interpreter, flags, symbols, by_name, targets)
    # BIZ UDP から持ってきた字だけを見る。欧字 (spec.LATIN) は文字が指す字、欧文の中の記号は置き換え先の
    # 字 (文字が指すのは BIZ UD の字で、BIZ UD のヒンティングを持ったまま和文で使う)
    for code in spec.UNHINTED:
        names = [cmap[code]] if code in spec.LATIN and code in cmap else []
        names += [target for source, target in symbols.items() if by_name[source] == code]
        for name in names:
            program = getattr(font["glyf"][name], "program", None)
            check(program is None or not program.getBytecode(), f"{label}: U+{code:04X} ({name}) still has hinting")


def check_nothing_vanishes(label: str, font: TTFont, mode: str, interpreter: int, flags: int,
                           symbols: dict, by_name: dict, targets: dict[str, str]) -> None:
    """ヒンティングを動かすと何も描かれなくなる欧字・記号が無いこと (動かさなければ描ける字)。
    BIZ UDP のヒンティングは、細い横線の字を、ある大きさで消す (spec.UNHINTED)"""
    hinted = freetype_render.Renderer(FONTS / label, interpreter, flags)
    plain = freetype_render.Renderer(FONTS / label, interpreter, flags | freetype_render.NO_HINTING)
    glyphs = [(f"U+{code:04X}", hinted.char_index(code)) for code in latin_codes(font.getBestCmap())]
    glyphs += [(f"U+{by_name[source]:04X} in Latin text", font.getGlyphID(target)) for source, target in symbols.items()]
    glyphs += [(f"{target} ({tag})", font.getGlyphID(target)) for target, tag in sorted(targets.items())]
    gone = [f"{what} at {ppem} ppem" for what, index in glyphs for ppem in HINTING_PPEMS
            if not any(hinted.render(index, ppem)[5]) and any(plain.render(index, ppem)[5])]
    check(not gone, f"{label}: {mode}: hinting erases {len(gone)} glyphs, such as {gone[:3]}")
    hinted.close()
    plain.close()


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
        check(program is None or not program.getBytecode(), f"{label}: superscript {d} has hinting")
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


# --- 足した文字と palt ----------------------------------------------------------------------

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


def check_proportional(label: str, font: TTFont, udp: TTFont) -> None:
    """palt で、仮名・約物・全角の字が BIZ UDP と同じ位置と字幅になること (インクの中心が 1 単位まで)。
    BIZ UDP と字幅が違い、インクの外形が 20 単位まで同じ字は、どれも palt を持つこと"""
    palt = gpos_values(font, "palt")
    cmap, cmap_udp = font.getBestCmap(), udp.getBestCmap()
    wrong, missing = [], []
    for code in [*range(0x3000, 0x3100), *range(0xFF01, 0xFF61)]:
        name, other = cmap.get(code), cmap_udp.get(code)
        if name is None or other is None or font["glyf"][name].numberOfContours == 0:
            continue
        if font["hmtx"][name][0] == udp["hmtx"][other][0] and name not in palt:
            continue
        a, b = glyph_bounds(font, name), glyph_bounds(udp, other)
        alike = (abs((a[2] - a[0]) - (b[2] - b[0])) <= 20 and abs(a[1] - b[1]) <= 20 and abs(a[3] - b[3]) <= 20)
        if name not in palt:
            if alike:
                missing.append(chr(code))
            continue
        x, y, x_advance, y_advance = palt[name]
        center = (a[0] + a[2]) / 2 + x - (b[0] + b[2]) / 2
        if y or y_advance or abs(center) > 1 or font["hmtx"][name][0] + x_advance != udp["hmtx"][other][0]:
            wrong.append(chr(code))
    check(len(palt) > 200, f"{label}: palt has only {len(palt)} glyphs")
    check(not wrong, f"{label}: palt does not set {len(wrong)} characters as BIZ UDP, such as {wrong[:5]}")
    check(not missing, f"{label}: {len(missing)} characters lack palt, such as {missing[:5]}")
    for char in "漢字読書":
        check(cmap[ord(char)] not in palt, f"{label}: {char} has palt")


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
    bases = [cmap[c] for c in cmap
             if (c in spec.LATIN or 0x0370 <= c <= 0x052F) and unicodedata.category(chr(c))[0] in "LN"
             and glyph_bounds(font, cmap[c]) is not None]
    above = [c for c in codes if unicodedata.combining(chr(c)) == 230]
    below = [c for c in codes if unicodedata.combining(chr(c)) == 220]
    for base in bases:
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

    # i と上の記号 → ı (ccmp の文脈の置き換え)
    gsub = font["GSUB"].table
    i, dotless = cmap[0x69], cmap[0x131]
    found = False
    for index in feature_lookup_indexes(font, {"ccmp"}):
        if lookup_type(gsub, index) != 6:
            continue
        for subtable in lookup_subtables(gsub, index):
            if (subtable.Format == 3 and i in subtable.InputCoverage[0].glyphs and subtable.LookAheadCoverage
                    and {cmap[c] for c in above} <= set(subtable.LookAheadCoverage[0].glyphs)):
                found = all(dict(next(iter(lookup_subtables(gsub, r.LookupListIndex))).mapping).get(i) == dotless
                            for r in subtable.SubstLookupRecord)
    check(found, f"{label}: i before marks above does not become dotless")

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
    check_license()
    for family in spec.FAMILIES:
        for weight in spec.WEIGHTS:
            check_font(family, weight)
    if problems:
        print("\n".join(problems[:50]))
        print(f"{len(problems)} problem(s)")
        return 1
    print(f"ok: {len(spec.FAMILIES) * len(spec.WEIGHTS)} fonts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
