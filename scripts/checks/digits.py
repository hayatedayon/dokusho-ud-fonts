"""数字: 分数・上付き・下付き・tnum・pnum・斜線の 0・数字の間のコロン。"""

from statistics import median

from fontTools.ttLib import TTFont

import harfbuzz_shape
import spec

from .common import FONTS, FontContext, Report, check, problems
from .fonttables import apply_features, gsub_alternates, gsub_mapping, shape
from .geometry import flattened, glyph_bounds, ink_area, ink_gap, moved_by, offset_of


SUPERSCRIPT_CODES = {0: 0x2070, 1: 0x00B9, 2: 0x00B2, 3: 0x00B3, 4: 0x2074,
                     **{d: 0x2070 + d for d in range(5, 10)}}
# 元のフォントに無く、作った字 (⁰ ⁵〜⁹ ⁺ ⁻ ⁼ ⁽ ⁾ と、₀〜₉ ₊ ₋ ₌ ₍ ₎)
NEW_SUPERSCRIPTS = {0x2070, *range(0x2075, 0x207F), *range(0x2080, 0x208F)}
# 上付きの記号 → 元の字 (− は BIZ UDP の字) と、sups でそれになる字
SUPERSCRIPT_SYMBOLS = {0x207A: (0x002B, "+"), 0x207B: (0x2212, "−-"), 0x207C: (0x003D, "="),
                       0x207D: (0x0028, "("), 0x207E: (0x0029, ")")}


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


def check_fractions(ctx: FontContext) -> None:
    """上付きの数字 0〜9 (sups と ⁰ ¹ … ⁹)、分子 (numr)・分母 (dnom) の数字、frac の分数。
    - 上付きの数字: 1〜4 は BIZ UDP の ¹ ² ³ ⁴。作った 0・5〜9 は、普通の数字に対するインクの面積の比
      (縮めて太らせた度合い) と高さが、¹ ² ³ ⁴ と同じくらい
    - 分子・分母は上付きの数字と同じ形で、分母はそれを同じだけ下げたもの (下が数字の下にそろう)
    - frac は分数の数字だけを置き換え、数字と斜線のインクの距離が、BIZ UDP の合成済みの分数
      (¼ ½ ¾ ⅓ …) の中央値になる"""
    label = ctx.label
    font = ctx.font
    udp = ctx.udp
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


def check_tabular(ctx: FontContext) -> None:
    """tnum で、数字 0〜9 が同じ字幅になり、狭い字 (1) は形を変えずに左右に同じだけ空きを足したもので
    あること。分数 (frac) と一緒にかけても、分数は変わらないこと"""
    label = ctx.label
    font = ctx.font
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


def check_zero_fractions(ctx: FontContext) -> None:
    """斜線の 0 (zero) と分数・上付き・下付きの組み合わせ (HarfBuzz)。"""
    ours = ctx.ours
    report = Report(ctx.label)
    # 斜線の 0 (zero) と分数・上付き・下付きの組み合わせ (HarfBuzz)
    for text, features, plain_features in [("10/20", ("zero", "frac"), ("frac",)), ("10⁄20", ("zero",), ()),
                                           ("１０／２０", ("zero", "frac"), ("frac",)), ("１０⁄２０", ("zero",), ()),
                                           ("0", ("zero", "sups"), ("sups",)), ("0", ("zero", "subs"), ("subs",)),
                                           ("０", ("zero", "sups"), ("sups",)), ("０", ("zero", "subs"), ("subs",))]:
        if ours.run(text, "en", False, features) != ours.run(text, "en", False, plain_features):
            report("zero breaks fractions or super/subscripts in HarfBuzz", f"{text} {features}")
    report.flush()


def check_colon(ctx: FontContext) -> None:
    """数字の間と和文の後のコロン (calt)。HarfBuzz で組んで、前後が数字のときと和文の後で、インクの上下の真ん中が数字の
    真ん中 (中央値) にあり、ヒンティングが無いこと。語の後 (Note:)・字の間 (a:b)・縦組では、元の
    コロン (BIZ UDP の字) のまま"""
    label = ctx.label
    family = ctx.family
    weight = ctx.weight
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


def check_numeric_widths(ctx: FontContext) -> None:
    """pnum が比例幅の数字に戻し、分数を変えないこと。"""
    label = ctx.label
    run = ctx.run
    for features in [("pnum",), ("tnum", "pnum"), ("zero", "tnum", "pnum")]:
        plain = ("zero",) if "zero" in features else ()
        check(run("0123456789", features) == run("0123456789", plain), f"{label}: pnum does not restore proportional digits")
    for text in ("1/2", "10/25"):
        check(run(text, ("frac", "tnum", "pnum")) == run(text, ("frac",)), f"{label}: numeric widths alter {text}")
