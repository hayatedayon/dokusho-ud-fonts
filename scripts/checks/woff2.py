"""WOFF2 の中身が TTF と同じであること。"""

from fontTools.ttLib import TTFont

import spec

from .common import FONTS, FontContext, check, problems


def check_woff2(ctx: FontContext) -> None:
    """WOFF2 の中身が TTF と同じであること。glyf・loca は圧縮のときに形式が変わるので字ごとに比べ、
    head は圧縮の印 (flags の bit 11) とチェックサムのほかを比べる。ほかの表はバイト列で比べる"""
    family = ctx.family
    weight = ctx.weight
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
