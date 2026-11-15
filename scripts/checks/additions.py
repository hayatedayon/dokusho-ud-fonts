"""足した文字 (見えない文字・空白・ダッシュ・和文 3 字)・行のメトリクス・行からのはみ出し。"""

import freetype_render
import harfbuzz_shape

from .common import FONTS, FontContext, check, problems
from .fonttables import gpos_values, gsub_alternates, gsub_mapping, outline
from .geometry import glyph_bounds, overflow


INVISIBLE_CODES = [0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF]
SPACE_WIDTHS = {0x2000: 1 / 2, 0x2001: 1, 0x2002: 1 / 2, 0x2003: 1, 0x2004: 1 / 3, 0x2005: 1 / 4, 0x2006: 1 / 6,
                0x2007: "0", 0x2008: ".", 0x2009: 1 / 5, 0x200A: 1 / 10, 0x202F: 1 / 5, 0x205F: 4 / 18}
EXTRA_CODES = [*INVISIBLE_CODES, *SPACE_WIDTHS, 0x2011, 0x2E3A, 0x2E3B]


def check_extra(ctx: FontContext) -> None:
    """見えない文字は幅 0、空白は決まった幅で、どちらもインクが無い。‑ は - と同じ字。⸺ ⸻ は ― を
    2 つ・3 つ横に並べた字で、縦組では縦組の ― を縦に並べた字になる"""
    label = ctx.label
    font = ctx.font
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
    # 〞 は 〝 を em の中心で左右反転した字で、縦組は 〟 の縦組の字
    name, low, high = cmap.get(0x301E), cmap[0x301F], cmap[0x301D]
    if name is None:
        problems.append(f"{label}: U+301E is missing")
    else:
        em = font["head"].unitsPerEm
        check(sorted(map(tuple, outline(font, name)[0])) == sorted((em - x, y) for x, y in outline(font, high)[0]),
              f"{label}: 〞 is not 〝 mirrored about the center of the em")
        check(font["hmtx"][name][0] == font["hmtx"][high][0] and font["vmtx"][name] == font["vmtx"][high],
              f"{label}: 〞 does not have the metrics of 〝")
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


def check_line_metrics(ctx: FontContext) -> None:
    label = ctx.label
    font = ctx.font
    ud = ctx.ud
    check(font["hhea"].lineGap == font["OS/2"].sTypoLineGap == 1024,
          f"{label}: hhea/typo line gaps are not 1024")
    for table, attrs in (("hhea", ("ascent", "descent")),
                         ("OS/2", ("sTypoAscender", "sTypoDescender", "usWinAscent", "usWinDescent", "fsSelection"))):
        check(all(getattr(font[table], a) == getattr(ud[table], a) for a in attrs),
              f"{label}: line metrics other than lineGap changed in {table}")
    for ascent, descent in ((font["hhea"].ascent, font["hhea"].descent),
                            (font["OS/2"].sTypoAscender, font["OS/2"].sTypoDescender)):
        check(ascent - descent + 1024 == font["head"].unitsPerEm * 1.5,
              f"{label}: normal line height is not 1.5 em")


def check_japanese_additions(ctx: FontContext) -> None:
    label = ctx.label
    font = ctx.font
    ud = ctx.ud
    cmap, source, em = font.getBestCmap(), ud.getBestCmap(), font["head"].unitsPerEm
    new = {cmap.get(c) for c in (0x20BB7, 0x3031, 0x3032)}
    check(None not in new and len(new) == 3, f"{label}: new Japanese glyphs missing or aliased")
    if None in new:
        return
    for table in font["cmap"].tables:
        if not table.isUnicode() or table.format == 14:
            continue
        for code in (0x20BB7, 0x3031, 0x3032):
            check(table.cmap.get(code) == (cmap[code] if code <= 0xFFFF or table.format in (12, 13) else None),
                  f"{label}: U+{code:04X} inconsistent in cmap {table.platformID}/{table.platEncID}")
    check(any(t.format == 12 and t.platformID == 3 and t.platEncID == 10 for t in font["cmap"].tables),
          f"{label}: no Windows supplementary cmap")
    # 生成側の関数は使わず、元フォントの輪郭と保存済みフォントを照合する。
    def contours(f, name):
        pts, ends, flags = outline(f, name)
        starts = [0] + [e + 1 for e in ends[:-1]]
        return [(pts[s:e + 1], flags[s:e + 1]) for s, e in zip(starts, ends)]
    kichi = contours(ud, source[0x5409])
    upper = max(kichi, key=lambda c: min(y for x, y in c[0]))
    earth = max(contours(ud, source[0x572D]), key=lambda c: min(y for x, y in c[0]))
    ours = contours(font, cmap[0x20BB7])
    check(ours[:-1] == [c for c in kichi if c is not upper], f"{label}: 𠮷 changed 吉's mouth")
    dx = ours[-1][0][0][0] - earth[0][0][0]
    dy = ours[-1][0][0][1] - earth[0][0][1]
    check(ours[-1] == ([(x + dx, y + dy) for x, y in earth[0]], earth[1]),
          f"{label}: 𠮷's 土 is not a translated copy of 圭's upper part")
    check(outline(font, cmap[0x20BB7]) != outline(ud, source[0x5409]), f"{label}: 𠮷 is still 吉")
    check(font["vmtx"][cmap[0x20BB7]] == ud["vmtx"][source[0x5409]], f"{label}: 𠮷 vertical metrics differ from 吉")
    for code in (0x20BB7, 0x3031, 0x3032):
        name = cmap[code]
        box = glyph_bounds(font, name)
        check(box is not None and box[0] >= 0 and box[2] <= em
              and box[1] >= -font["OS/2"].usWinDescent and box[3] <= font["OS/2"].usWinAscent,
              f"{label}: U+{code:04X} is empty or outside its horizontal line frame: {box}")
        check(font["hmtx"][name][0] == em, f"{label}: U+{code:04X} is not full width")
        check(not font["glyf"][name].program.getBytecode(), f"{label}: generated Japanese glyph has unexpected hinting")
        check(name not in gsub_alternates(font, "aalt"), f"{label}: new glyph has unintended aalt alternatives")
    shaper = harfbuzz_shape.Shaper(FONTS / label)
    for code, top_code in ((0x3031, 0x3033), (0x3032, 0x3034)):
        name = cmap[code]
        for tag, features in (("vert", ()), ("vrt2", ("vert=0", "vrt2"))):
            vertical = gsub_mapping(font, tag).get(name)
            check(vertical is not None, f"{label}: {tag} is missing for U+{code:04X}")
            if vertical is None:
                continue
            box = glyph_bounds(font, vertical)
            origin = font["glyf"][vertical].yMax + font["vmtx"][vertical][1]
            check(font["hmtx"][vertical][0] == em and font["vmtx"][vertical][0] == 2 * em,
                  f"{label}: repeat mark must occupy one horizontal / two vertical cells")
            check(box and 0 <= box[0] < box[2] <= em and origin - 2 * em <= box[1] < box[3] <= origin,
                  f"{label}: repeat mark exceeds its two-cell vertical frame")
            top = outline(ud, source[top_code])[0]
            lower = outline(ud, source[0x3035])[0]
            offset = min(y for x, y in top) - max(y for x, y in lower)
            expected = set(top) | {(x, y + offset) for x, y in lower}
            check(set(outline(font, vertical)[0]) == expected,
                  f"{label}: repeat mark does not retain the source halves' points")
            check(len(outline(font, vertical)[1]) == len(outline(ud, source[top_code])[1]),
                  f"{label}: repeat halves have an unjoined seam")
            shaped = shaper.shape(chr(code), "ja", True, features)
            check(len(shaped) == 1 and shaped[0][0] == font.getGlyphID(vertical) and shaped[0][3] == -2 * em,
                  f"{label}: {tag} does not shape one two-cell repeat glyph")
        check(outline(font, name) != outline(ud, source[top_code]), f"{label}: repeat mark is only its upper half")
    check(outline(font, cmap[0x3031]) != outline(font, cmap[0x3032]), f"{label}: voiced repeat mark lacks dakuten")
    for features in ((), ("vert=0", "vrt2")):
        shaped = shaper.shape("𠮷", "ja", True, features)
        check(len(shaped) == 1 and shaped[0][0] == font.getGlyphID(cmap[0x20BB7]) and shaped[0][3] == -em,
              f"{label}: 𠮷 vertical shaping is not a full cell")
    shaper.close()
    renderer = freetype_render.Renderer(FONTS / label, 40, 0)
    for code in (0x20BB7, 0x3031, 0x3032):
        for ppem in (12, 14, 16):
            rendered = renderer.render(font.getGlyphID(cmap[code]), ppem)
            check(any(rendered[-1]), f"{label}: U+{code:04X} disappears at {ppem}px")
    renderer.close()


def check_overflow(ctx: FontContext) -> None:
    """行の上と下 (usWinAscent・usWinDescent。Windows はその外を描かない) からのはみ出しが、元の
    フォントより増えていないこと。BIZ UD の字は、同じ名前の BIZ UD か BIZ UDP の字 (欧字は BIZ UDP の
    字にした) より出ないこと。足した字は、出ないか、元のフォントのはみ出す字をそのまま写したもの。
    縦組の ⸺ ⸻ と 〱 〲 (2 em・3 em の縦の字送りの向きに伸びる字) は専用枠で検査する"""
    label = ctx.label
    font = ctx.font
    ud = ctx.ud
    udp = ctx.udp
    order_ud = set(ud.getGlyphOrder())
    names_udp = set(udp.getGlyphOrder())
    cmap = font.getBestCmap()
    # ２セルのくの字点も専用の縦組枠で check_japanese_additions が上下を検査する。
    vertical_dashes = {gsub_mapping(font, "vert").get(cmap.get(code)) for code in (0x2E3A, 0x2E3B, 0x3031, 0x3032)}
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
