"""欧字・欧文の中の記号が BIZ UDP と同じであること (形・字幅・置き換え・合字・aalt・hwid)。"""

import unicodedata

import spec

from .common import FontContext, check, problems
from .fonttables import combining_codes, gsub_alternates, gsub_ligatures, gsub_mapping, lang_system, latin_codes, latin_symbol_mapping, latin_targets, outline, outputs, vertical_closure
from .geometry import drawing


def check_latin_letters(ctx: FontContext) -> None:
    """欧字の字幅・輪郭が BIZ UDP と同じであること。"""
    label = ctx.label
    font = ctx.font
    udp = ctx.udp
    cmap = ctx.cmap
    cmap_udp = ctx.cmap_udp
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


def check_latin_substitutions(ctx: FontContext) -> None:
    """欧字の置き換え (GSUB)・合字・aalt と、hwid・fwid (BIZ UD と同じ半角・全角の字) が合っていること。"""
    label = ctx.label
    font = ctx.font
    ud = ctx.ud
    udp = ctx.udp
    cmap = ctx.cmap
    cmap_ud = ctx.cmap_ud
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


def check_latin_symbols(ctx: FontContext) -> None:
    """欧文の中の記号。できたフォントと BIZ UDP で違う記号は、欧字の用字系 (latn) の既定でだけ BIZ UDP の
    字 (形と字幅) に置き換わり、日本語 (latn の JAN) と和文などの用字系では、spec.ALWAYS_UDP だけが
    置き換わること。書式の文字
    (ソフトハイフンなど) は、どこでも置き換わらないこと"""
    label = ctx.label
    font = ctx.font
    ud = ctx.ud
    udp = ctx.udp
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
