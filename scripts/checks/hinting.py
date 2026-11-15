"""ヒンティング。FreeType でヒンティングを動かして描き、画素を元のフォントと比べる。"""

from fontTools.ttLib import TTFont

import freetype_render
import spec

from .charset import JAPANESE
from .common import FONTS, FontContext, SOURCES, check
from .fonttables import gsub_mapping, latin_codes, latin_symbol_mapping, latin_targets


HINTING_PPEMS = range(8, 25)


def check_hinting(ctx: FontContext) -> None:
    """BIZ UDP から持ってきた字のヒンティングが BIZ UDP と同じで、和文のヒンティングが BIZ UD と
    同じこと。FreeType でヒンティングを動かして描き、画素を比べる (hinting.py が cvt の番号を
    ずらし損ねていれば、字の形がずれる)"""
    label = ctx.label
    family = ctx.family
    weight = ctx.weight
    font = ctx.font
    targets = latin_targets(ctx.udp, ctx.latin_glyphs)
    udp_font = ctx.udp
    ud_font = ctx.ud
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


def check_generated_mark_hints(ctx: FontContext) -> None:
    """作った約物のヒントが効いていて、8–24 ppem の全描画モードで消えず、〝 〟 と高さがそろうこと。"""
    label = ctx.label
    path = ctx.path
    font = ctx.font
    shaper = ctx.shaper
    cmap, order = font.getBestCmap(), font.getGlyphOrder()
    vertical = lambda char, script: shaper.shape(char, "ja", True, (), script)[0][0]
    names = [(cmap[0x301E], cmap[0x301D])]
    for char, source, script in (("‘", "〝", "Hani"), ("’", "〟", "Hani"), ("‘", "〝", "Latn"), ("’", "〟", "Latn")):
        names.append((order[vertical(char, script)], order[vertical(source, "Hani")] if script == "Hani" else None))
    for name, reference in names:
        check(len(font["glyf"][name].program.getBytecode()) > 0, f"{label}: {name} has no hinting")
    for mode, interpreter, flags in freetype_render.MODES:
        renderer = freetype_render.Renderer(path, interpreter, flags)
        for ppem in range(8, 25):
            for name, reference in names:
                index = font.getGlyphID(name)
                bitmap = renderer.render(index, ppem)
                check(bitmap[4] >= 1 and any(bitmap[5]), f"{label}: {name} vanishes at {ppem} ppem ({mode})")
                if reference is not None:
                    ys = [y for _x, y in renderer.outline(index, ppem)]
                    reference_ys = [y for _x, y in renderer.outline(font.getGlyphID(reference), ppem)]
                    check(abs(min(ys) - min(reference_ys)) <= 64 and abs(max(ys) - max(reference_ys)) <= 64,
                          f"{label}: {name} is more than 1 px off {reference} at {ppem} ppem ({mode})")
        renderer.close()


def check_ruby_hint_rendering(ctx: FontContext) -> None:
    """ss03 の試作字形のヒントが、FreeType の全描画モードで効いていて、形を崩さないこと。

    6・7 ppem は prep が命令を止めるので、グレースケールではヒントなしと同じ画素。8–24 ppem は、点が縦にだけ 1 px 以内で動き
    (横は動かない)、消えず、濃さがヒントなしから大きく変わらず、横線の端が画素の境目にそろう (通常の仮名と同じくらい)。
    """
    label = ctx.label
    font = ctx.font
    trial = gsub_mapping(font, "ss03")
    pairs = [(font.getGlyphID(source), font.getGlyphID(target)) for source, target in trial.items()]
    for mode, interpreter, flags in freetype_render.MODES:
        hinted = freetype_render.Renderer(ctx.path, interpreter, flags)
        plain = freetype_render.Renderer(ctx.path, interpreter, flags | freetype_render.NO_HINTING)
        for ppem in range(6, 25):
            aligned = {"source": 0, "trial": 0, "plain": 0}
            ink = [0, 0]
            for source, target in pairs:
                shown, unhinted = hinted.render(target, ppem), plain.render(target, ppem)
                if ppem < 8:
                    # モノクロでは、命令の無い字も NO_HINTING と同じにならない (通常の仮名も同じ) ので比べない
                    check(flags or shown == unhinted, f"{label}: {mode}: trial ruby {target} is hinted at {ppem} ppem")
                    continue
                check(any(shown[5]), f"{label}: {mode}: trial ruby {target} vanishes at {ppem} ppem")
                fitted, original = hinted.outline(target, ppem), plain.outline(target, ppem)
                check(all(a[0] == b[0] and abs(a[1] - b[1]) <= 64 for a, b in zip(fitted, original)),
                      f"{label}: {mode}: trial ruby {target} is distorted at {ppem} ppem")
                for key, renderer, index in (("source", hinted, source), ("trial", hinted, target), ("plain", plain, target)):
                    ys = [y for _x, y in renderer.outline(index, ppem)]
                    aligned[key] += sum(1 for y in set(ys) if ys.count(y) >= 3 and y % 64 == 0)
                if not flags:
                    ratio = sum(shown[5]) / max(1, sum(unhinted[5]))
                    check(0.75 <= ratio <= 1.4, f"{label}: {mode}: trial ruby {target} changes its ink by {ratio:.2f} at {ppem} ppem")
                ink[0] += sum(shown[5]) if not flags else sum(bin(b).count("1") for b in shown[5])
                ink[1] += sum(unhinted[5]) if not flags else sum(bin(b).count("1") for b in unhinted[5])
            if ppem >= 8:
                check(0.9 <= ink[0] / ink[1] <= 1.1, f"{label}: {mode}: hinting changes the ink of the trial ruby by {ink[0] / ink[1]:.2f} at {ppem} ppem")
                check(aligned["trial"] >= 0.8 * aligned["source"] and aligned["trial"] >= 5 * max(1, aligned["plain"]),
                      f"{label}: {mode}: trial ruby lines are not on pixel boundaries at {ppem} ppem {aligned}")
        hinted.close()
        plain.close()
