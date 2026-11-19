"""文字の割り当て・グリフの並び・和文の字が BIZ UD のままであること。"""

import harfbuzz_shape
import spec

from .additions import EXTRA_CODES
from .common import FONTS, FontContext, check
from .digits import NEW_SUPERSCRIPTS
from .fonttables import combining_codes, gsub_mapping, latin_symbol_mapping, lookup_subtables, outline, outputs


# 和文の字。BIZ UD のままで、全角 (横も縦も 1 em) であること
JAPANESE = "あいうえおっゃー漢字読書。、・「」（）：！？　"


def check_cmap(ctx: FontContext) -> None:
    """文字の割り当てと足したグリフが、BIZ UD に加えた分だけであること。"""
    label = ctx.label
    font = ctx.font
    ud = ctx.ud
    cmap = ctx.cmap
    cmap_ud = ctx.cmap_ud
    # 文字の割り当ては BIZ UD のまま。作った数字・空白・記号、和文３字、二重括弧を加える。変えるのは、
    # ほかの文字と字を分け合っていた結合用の記号 (˜ U+02DC と同じ字の U+0303) だけ
    # post は形式 3 で、グリフの名前はファイルに残らない。fontTools は cmap から名前を組み立てるので、
    # ｟ ｠ と同じグリフに ⦅ ⦆ を割り当てると、名前が小さい方のコード (uni2985) に変わって見える。
    # グリフの番号は同じなので、元のグリフの名前を新しい名前に対応させて比べる
    aliases = spec.WHITE_PARENTHESIS_ALIASES
    renamed = {cmap_ud[fullwidth]: cmap.get(fullwidth) for fullwidth in aliases.values()}
    added = {code: cmap[code] for code in cmap.keys() - cmap_ud.keys()}
    remapped = {code for code in cmap_ud if cmap.get(code) != renamed.get(cmap_ud[code], cmap_ud[code])}
    shared_marks = {code for code in combining_codes(cmap_ud)
                    if any(c != code and g == cmap_ud[code] for c, g in cmap_ud.items())}
    expected = set(NEW_SUPERSCRIPTS) | set(EXTRA_CODES) | {0x301E, 0x20BB7, 0x3031, 0x3032} | aliases.keys()
    check(remapped <= shared_marks and set(added) == expected, f"{label}: unexpected cmap changes from BIZ UD")
    for table in font["cmap"].tables:
        for code, fullwidth in aliases.items():
            check(table.cmap.get(code) == table.cmap.get(fullwidth),
                  f"{label}: U+{code:04X} differs from U+{fullwidth:04X} in cmap "
                  f"({table.platformID}, {table.platEncID}, format {table.format})")
    # BIZ UD のグリフの後に、欧文の中の記号 (BIZ UDP の字) だけが足してあること
    order, order_ud = font.getGlyphOrder(), ud.getGlyphOrder()
    order_ud = [renamed.get(name, name) for name in order_ud]
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
    # 縦組の “ ” ‘ ’ の字 (ミニュートの形と、欧字の用字系の ‘ ’ の横倒しの字)
    sideways_shaper = harfbuzz_shape.Shaper(FONTS / label)
    fraction_glyphs |= {order[record[0]] for char in "“”‘’" for script in ("Latn", "Hani")
                        for features in ((), ("vert=0", "vrt2"))
                        for record in sideways_shaper.shape(char, "en", True, features, script)}
    sideways_shaper.close()
    check(extra == set(latin_symbol_mapping(font, "latn", None).values()) | half_widths | fraction_glyphs,
          f"{label}: glyphs other than the symbols for Latin text, the half widths for hwid and the fraction "
          "digits and stylistic sets were added")


def check_japanese_kept(ctx: FontContext) -> None:
    """代表の和文の字と × ÷ が BIZ UD の形と字幅のままであること。"""
    label = ctx.label
    font = ctx.font
    ud = ctx.ud
    cmap = ctx.cmap
    cmap_ud = ctx.cmap_ud
    em = ctx.em
    for char in JAPANESE:
        g = cmap[ord(char)]
        check(font["hmtx"][g][0] == em, f"{label}: {char} is not full width")
        check(font["vmtx"][g][0] == em, f"{label}: {char} does not advance 1 em in vertical text")
        check(outline(font, g) == outline(ud, cmap_ud[ord(char)]), f"{label}: {char} outline is not BIZ UD's")
    for char in "×÷":
        g = cmap[ord(char)]
        check(font["hmtx"][g] == ud["hmtx"][cmap_ud[ord(char)]], f"{label}: {char} is not BIZ UD's")
