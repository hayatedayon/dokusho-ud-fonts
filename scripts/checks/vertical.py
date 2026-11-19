"""縦組 (vert・vrt2・vpal・縦組の引用符・縦組で正立する記号)。"""

import unicodedata

import spec

from .common import FontContext, Report, Shaped, check
from .fonttables import combining_codes, gpos_values, gsub_mapping, outline, semi_voiced_kana_ligatures
from .geometry import glyph_bounds


VERTICAL_PROPORTIONAL_CODES = [*range(0x3000, 0x3100), *range(0x31F0, 0x3200), 0xFE45, 0xFE46, *range(0xFF01, 0xFF61)]


def check_vertical_tables(ctx: FontContext) -> None:
    """縦組の機能 (vert・vrt2・fwid) と縦組のメトリクスがあること。"""
    label = ctx.label
    font = ctx.font
    features = {r.FeatureTag for r in font["GSUB"].table.FeatureList.FeatureRecord}
    check({"vert", "vrt2", "fwid"} <= features, f"{label}: vertical or full-width features are missing")
    check("vhea" in font and "vmtx" in font, f"{label}: vertical metrics are missing")


def check_white_parentheses(ctx: FontContext) -> None:
    """二重括弧を横・縦に組み、全角の二重括弧と同じ字形・送り・位置になること。"""
    font, cmap = ctx.font, ctx.cmap
    horizontal = tuple(cmap.get(code) for code in spec.WHITE_PARENTHESIS_ALIASES.values())
    if not all(horizontal):
        check(False, f"{ctx.label}: fullwidth white parentheses are missing")
        return

    for vertical, tag, features in ((False, None, ()), (True, "vert", ()), (True, "vrt2", ("vert=0", "vrt2"))):
        forms = gsub_mapping(font, tag) if tag else {}
        expected_names = tuple(forms.get(name, name) for name in horizontal)
        check(not vertical or all(a != b for a, b in zip(expected_names, horizontal)),
              f"{ctx.label}: {tag} lacks vertical forms for white parentheses")
        expected_ids = [font.getGlyphID(name) for name in expected_names]
        fullwidth = ctx.run("｟あ｠", features, vertical)
        aliases = ctx.run("⦅あ⦆", features, vertical)
        check(len(fullwidth) == 3 and fullwidth == aliases and [g[0] for g in fullwidth[::2]] == expected_ids,
              f"{ctx.label}: white parentheses shape differently ({tag or 'horizontal'})")


def check_proportional_vertical(ctx: FontContext) -> None:
    """vpal で、仮名・約物・全角の字 (ccmp の半濁点の合字も) の縦組の字が BIZ UDP と同じ縦の位置
    (縦組の原点からのインクの中心が 1 単位まで) と縦の字送りになり、付けるべき字に漏れが無いこと。漢字や結合用の記号には付かないこと"""
    label = ctx.label
    font = ctx.font
    udp = ctx.udp
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


def check_vertical_latin(ctx: FontContext) -> None:
    """縦書きでも、横書きと同じ書体で欧字・記号が組まれること。"""
    ours = ctx.ours
    ud = ctx.ud_shaped
    udp = ctx.udp_shaped
    cmap = ctx.cmap
    cmap_ud = ctx.cmap_ud
    cmap_udp = ctx.cmap_udp
    marks = ctx.marks
    ignorable = ctx.ignorable
    orientation = ctx.orientation
    report = Report(ctx.label)
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
            if code in spec.VERTICAL_MINUTES:  # 縦組はミニュートの形。check_vertical_minutes が検査する
                continue
            if follows is not None and not near(vertical_run(ours, char, script, language),
                                                vertical_run(follows, char, script, language)):
                report("in vertical text is not set as in the font it follows horizontally",
                       f"U+{code:04X} ({script} {language})")
    report.flush()


def check_vertical_minutes(ctx: FontContext) -> None:
    """縦組の “ ” は 〝 〟 と同じ形、‘ ’ は同じ位置の 1 画で、送りは全角。既定と vrt2、ja と en の両方を調べる。"""
    label = ctx.label
    font = ctx.font
    shaper = ctx.shaper
    glyf, order, em = font["glyf"], font.getGlyphOrder(), font["head"].unitsPerEm
    for language in ("ja", "en"):
        for features in ((), ("vert=0", "vrt2")):
            def shaped(char):
                records = shaper.shape(char, language, True, features, "Hani")
                check(len(records) == 1, f"{label}: {char} is not one glyph in vertical text")
                return order[records[0][0]], records[0][3]
            for code, source_code in spec.VERTICAL_MINUTES.items():
                name, advance = shaped(chr(code))
                source, _ = shaped(chr(source_code))
                check(advance == -em, f"{label}: vertical U+{code:04X} is not one em high ({advance})")
                check(name != source, f"{label}: vertical U+{code:04X} shares the glyph of U+{source_code:04X}")
                if code in spec.VERTICAL_SWAPPED_QUOTES:
                    check(glyf[name].numberOfContours == 1, f"{label}: vertical U+{code:04X} is not one stroke")
                    middle = lambda g: glyf[g].xMin + glyf[g].xMax
                    check(abs(middle(name) - middle(source)) <= 2 and glyf[name].yMin >= glyf[source].yMin
                          and glyf[name].yMax <= glyf[source].yMax,
                          f"{label}: vertical U+{code:04X} is not placed where U+{source_code:04X} is")
                else:
                    check(outline(font, name) == outline(font, source), f"{label}: vertical U+{code:04X} is not U+{source_code:04X}")
            minutes = {shaped(chr(code))[0] for code in spec.VERTICAL_MINUTES}
            for char in "“”‘’":
                horizontal = shaper.shape(char, language, False, ())
                check(order[horizontal[0][0]] not in minutes, f"{label}: {char} takes a minute form in horizontal text")
            for char in "“”":
                # “ ” は英語の中でもミニュートのまま (日本語に続く “Hello” の開きと閉じをそろえる)
                latin = shaper.shape(char, language, True, features, "Latn")
                check(len(latin) == 1 and order[latin[0][0]] in minutes, f"{label}: {char} in Latin text is not the minute form in vertical text")
            for char in "‘’":
                # 英語の中 (用字系が欧字) の ‘ ’ はミニュートではなく、全角より短い横倒しの字
                latin = shaper.shape(char, language, True, features, "Latn")
                check(len(latin) == 1 and -em < latin[0][3] < 0 and order[latin[0][0]] not in minutes,
                      f"{label}: {char} in Latin text is not the sideways form in vertical text")
