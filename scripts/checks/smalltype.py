"""小さい字: ルビ用の仮名 (ss03) と小さい数字のヒント。"""

from pathlib import Path

from fontTools.ttLib import TTFont

import freetype_render
import small_type
import spec

from .common import FontContext, SOURCES, check
from .fonttables import gpos_values, gsub_mapping, outputs
from .geometry import glyph_bounds, overflow


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


def check_ruby(ctx: FontContext) -> None:
    """ss03 のルビ用の仮名が、枠・字送り・縦組の置き換えを変えないこと。"""
    label = ctx.label
    font = ctx.font
    order = ctx.order
    run = ctx.run
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


def check_small_digits(ctx: FontContext) -> None:
    """作った小さい数字のヒントが、8–24 ppem で消えたり潰れたりしないこと。"""
    label = ctx.label
    family = ctx.family
    weight = ctx.weight
    path = ctx.path
    font = ctx.font
    ud = ctx.ud_shaped
    cmap = ctx.cmap
    shaper = ctx.shaper
    run = ctx.run
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
