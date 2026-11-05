"""fonts/ の読書 UD を、元の BIZ UD・BIZ UDP と突き合わせて確かめる。

build.py とは別の書き方で、できたものだけを見る。1 つでも合わなければ 1 で終わる。
"""

import sys
from pathlib import Path

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

    check(cmap == cmap_ud, f"{label}: the character map differs from BIZ UD")
    # BIZ UD のグリフの後に、欧文の中の記号 (BIZ UDP の字) だけが足してあること
    order, order_ud = font.getGlyphOrder(), ud.getGlyphOrder()
    check(order[: len(order_ud)] == order_ud, f"{label}: the glyph order of BIZ UD is not kept")
    extra = set(order[len(order_ud):])
    check(extra == set(latin_symbol_mapping(font, "latn", None).values()),
          f"{label}: glyphs other than the symbols for Latin text were added")

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
    check_hinting(label, font, family, weight, latin_targets(udp, latin_glyphs), udp)
    check_spacing(label, font)


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
                  udp_font: TTFont) -> None:
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
