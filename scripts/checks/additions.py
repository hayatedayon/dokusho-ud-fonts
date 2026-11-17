"""足した文字 (見えない文字・空白・ダッシュ・和文 3 字)・行のメトリクス・行からのはみ出し。"""

import tempfile
from pathlib import Path

import freetype_render
import harfbuzz_shape
from fontTools.ttLib import TTFont

from .common import FONTS, FontContext, check, problems
from .fonttables import gpos_values, gsub_alternates, gsub_mapping, gsub_multiple, lookup_type, outline
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


# 縦組で 2 セル・3 セルになる字 → セルの数 (縦組の 1 段目は 2 em・3 em の 1 字、2 段目は輪郭のある字 1 つと空白の字)
VERTICAL_CELLS = {0x3031: 2, 0x3032: 2, 0x2E3A: 2, 0x2E3B: 3}
# 組み方を変える機能の組み合わせ。縦組の字の並びは、どれでも同じになる
VERTICAL_FEATURES = [(), ("ss01",), ("ss02",), ("ss03",), ("palt",), ("vpal",), ("halt",), ("vhal",), ("aalt",),
                     ("palt", "vpal", "halt", "vhal"), ("kern=0",), ("vert=0", "vrt2"), ("vert", "vrt2=0")]
SPACING_FEATURE = "curs"  # 空白と1段目の縦字形の横送りを足す GPOS の機能 (extra_glyphs.SPACING_FEATURE)


def check_vertical_cells(ctx: FontContext) -> None:
    """縦組の 2 セル・3 セルの字 (〱 〲 ⸺ ⸻) の、2 段の置き換え。1 段目は今までどおり cmap の字 → 縦の送りが
    セルの数 × 1 em の 1 字。2 段目 (vert と vrt2 に 1 つずつの、最後の 2 つの lookup) は、その字 → [輪郭が同じ字,
    空白の字 …] (縦の送りに vmtx を使わない環境のため)。環境ごとの送りの決め方 (HarfBuzz・DirectWrite は縦の送り、
    CoreText は横の送りの合計、WebKitGTK は横の送りと GPOS curs の横の送りの合計) のどれでも、合計がセルの数 ×
    1 em になること。DirectWrite は、1 つの文字から出た字の横の送り (hmtx と GPOS の送り) の合計で字を左右に
    ずらして置くので、vert の並びで横の送りを持つのは輪郭のある字だけ (空白は 0。足りない分は curs の GPOS)。
    2 段目を処理できない環境 (最後の 2 つの lookup を除いた機能) は、1 段目だけを適用して、1 字・セルの数 × 1 em
    になること。"""
    label = ctx.label
    font = ctx.font
    shaper = ctx.shaper
    cmap, em, order = font.getBestCmap(), font["head"].unitsPerEm, font.getGlyphOrder()
    gsub = font["GSUB"].table
    lookups = gsub.LookupList.Lookup
    last = len(lookups) - 1
    check([i for i in range(len(lookups)) if lookup_type(gsub, i) == 2] == [last - 1, last],
          f"{label}: the only multiple substitutions must be the last two GSUB lookups")
    # 並び (vert は横の送りが 0 の空白、vrt2 は横の送りが 1 em の空白)。後の lookup が先に適用されないよう、番号の
    # 順 (適用の順) でも最後であること
    blanks = {}  # 機能 → 空白の字 (読み直したフォントには字の名前が残らないので、並びから読む)
    own = {"vert": last - 1, "vrt2": last}
    stage_one = {}
    for tag in ("vert", "vrt2"):
        records = [r for r in gsub.FeatureList.FeatureRecord if r.FeatureTag == tag]
        check(all(r.Feature.LookupListIndex.count(own[tag]) == 1 and r.Feature.LookupListIndex[-1] == own[tag]
                  and max(r.Feature.LookupListIndex) == own[tag] and r.Feature.LookupListIndex.count(own[{"vert": "vrt2", "vrt2": "vert"}[tag]]) == 0
                  for r in records), f"{label}: {tag} does not end with its own lookup that splits the cells")
        multiple = gsub_multiple(font, tag)
        wide = {code: gsub_mapping(font, tag).get(cmap[code]) for code in VERTICAL_CELLS}
        check(None not in wide.values() and set(multiple) == set(wide.values()),
              f"{label}: {tag} splits glyphs other than the vertical forms of 〱 〲 ⸺ ⸻")
        stage_one[tag] = wide
        for code, cells in VERTICAL_CELLS.items():
            name = f"U+{code:04X}"
            if wide[code] is None:
                continue
            form, sequence = wide[code], multiple.get(wide[code], [])
            check(font["vmtx"][form][0] == cells * em and font["hmtx"][form][0] == em,
                  f"{label}: {tag} first stage of {name} is not one glyph of {cells} cells")
            check(len(sequence) == cells and len(set(sequence[1:])) == 1 and sequence[0] not in (form, sequence[-1]),
                  f"{label}: {tag} second stage of {name} is not one glyph and {cells - 1} blank(s)")
            if len(sequence) != cells:
                continue
            head, blank = sequence[0], sequence[-1]
            check(blanks.setdefault(tag, blank) == blank, f"{label}: {tag} uses more than one blank glyph")
            check(outline(font, head) == outline(font, form) and font["hmtx"][head] == font["hmtx"][form],
                  f"{label}: {tag} first glyph of {name} does not keep the outline of the {cells}-cell glyph")
            check(font["vmtx"][head] == font["vmtx"][form] and font["glyf"][head].yMax == font["glyf"][form].yMax,
                  f"{label}: {tag} first glyph of {name} does not keep the vertical advance and origin of the {cells}-cell glyph")
            check(font["glyf"][blank].numberOfContours == 0 and font["vmtx"][blank] == (0, 0)
                  and font["hmtx"][blank][0] == (em if tag == "vrt2" else 0),
                  f"{label}: {tag} blank of {name} has ink, advances vertically or has a wrong horizontal advance")
            box = glyph_bounds(font, head)
            origin = font["glyf"][head].yMax + font["vmtx"][head][1]
            check(box and 0 <= box[0] < box[2] <= em and origin - cells * em <= box[1] < box[3] <= origin,
                  f"{label}: {tag} first glyph of {name} exceeds its {cells}-cell frame")
            # 環境ごとの送りの決め方。縦の送り (HarfBuzz) と最大 (DirectWrite) は 2 セルの字のもの、横の送りの合計 (CoreText は
            # vrt2、WebKitGTK は vert の GPOS の送りも足す) もセルの数 × 1 em
            extra = gpos_values(font, SPACING_FEATURE).get(blank, (0, 0, 0, 0))[2] if tag == "vert" else 0
            check(sum(font["vmtx"][g][0] for g in sequence) == cells * em
                  and max(font["vmtx"][g][0] for g in sequence) == cells * em
                  and sum(font["hmtx"][g][0] for g in sequence) + extra * (cells - 1) == cells * em,
                  f"{label}: {tag} advances of the glyphs of {name} do not add up to {cells} cells (vertical, or horizontal as CoreText and WebKitGTK use)")
            if tag == "vert":
                check(sum(font["hmtx"][g][0] for g in sequence) == em,
                      f"{label}: only the first glyph of {name} has a horizontal advance in vert (DirectWrite would shift it sideways)")
    check(stage_one["vert"] == stage_one["vrt2"], f"{label}: vert and vrt2 have different vertical forms of 〱 〲 ⸺ ⸻")
    # 空白と1段目の縦字形を調整するのは curs だけ。ほかの機能 (kern・vert・vkrn など) には入れない
    # (DirectWrite は kern・dist・vert の GPOS の横の送りも使って字を左右にずらす)
    gpos = font["GPOS"].table
    adds = gpos_values(font, SPACING_FEATURE)
    blank_zero = blanks.get("vert")
    want_adds = {blank_zero: (0, 0, em, 0)}
    want_adds.update({form: (0, 0, (VERTICAL_CELLS[code] - 1) * em, 0)
                      for code, form in stage_one["vert"].items() if form is not None})
    check(blank_zero != blanks.get("vrt2") and adds == want_adds,
          f"{label}: {SPACING_FEATURE} does not hold the blank and first-stage horizontal advances")
    others = {i for r in gpos.FeatureList.FeatureRecord if r.FeatureTag != SPACING_FEATURE for i in r.Feature.LookupListIndex}
    check(not any(any(glyph in getattr(getattr(st, "ExtSubTable", st), "Coverage", None).glyphs
                          for glyph in want_adds)
                  for i in others for st in gpos.LookupList.Lookup[i].SubTable
                  if getattr(getattr(st, "ExtSubTable", st), "Coverage", None) is not None),
          f"{label}: a vertical-cell spacing glyph is adjusted by a feature other than {SPACING_FEATURE}")
    multiple = gsub_multiple(font, "vert")
    # 組んだ結果 (HarfBuzz は縦の送りを使う)。どの機能でも、あ〱い・〱〲 のように前後の字や並びがあっても同じ
    for code, cells in VERTICAL_CELLS.items():
        char = chr(code)
        form = stage_one["vert"][code]
        if form is None or form not in multiple:
            continue
        for features in VERTICAL_FEATURES:
            # vert=0 だけは vrt2 の並び (どちらも輪郭のある字 1 つと空白の字。空白は横の送りだけ違う)
            sequence = gsub_multiple(font, "vrt2" if "vert=0" in features else "vert")[form]
            for text in (char, f"あ{char}い", char + char, f"あ{char}い{char}"):
                shaped = shaper.shape(text, "ja", True, features)
                # その字から出た字 (クラスターは UTF-8 のバイトの位置。前後の仮名は、機能で変わってもよい)
                clusters = [len(text[:i].encode()) for i, c in enumerate(text) if c == char]
                for cluster in clusters:
                    part = [g for g in shaped if g[1] == cluster]
                    check([order[g[0]] for g in part] == sequence and [-g[3] for g in part] == [cells * em] + [0] * (cells - 1),
                          f"{label}: {text} does not shape one {cells}-cell glyph and {cells - 1} blank(s) for U+{code:04X} in vertical text with {features}")
                    check(sum(-g[3] for g in part) == cells * em,
                          f"{label}: {text} is not {cells} em for U+{code:04X} in vertical text with {features}")
                check(len(shaped) == len(text) - len(clusters) + cells * len(clusters),
                      f"{label}: {text} has a different number of glyphs in vertical text with {features}")
        # 横組は変わらない (cmap の字 1 つ。送りは 〱 〲 が 1 em、⸺ ⸻ が 2 em・3 em)
        for features in ((), ("ss01",), ("palt",), ("halt",), ("kern=0",), (SPACING_FEATURE,)):
            shaped = shaper.shape(char, "ja", False, features)
            check(len(shaped) == 1 and order[shaped[0][0]] == cmap[code] and shaped[0][2] == font["hmtx"][cmap[code]][0],
                  f"{label}: U+{code:04X} horizontal shaping changed with {features}")
    # 2 段目を処理できない環境。最後の 2 つの lookup を vert・vrt2 から外した複製で、今までどおり 1 字・セルの数 × 1 em
    with tempfile.TemporaryDirectory() as folder:
        stripped = TTFont(FONTS / label, lazy=False)
        for record in stripped["GSUB"].table.FeatureList.FeatureRecord:
            if record.FeatureTag in ("vert", "vrt2"):
                record.Feature.LookupListIndex = [i for i in record.Feature.LookupListIndex if i not in (last - 1, last)]
                record.Feature.LookupCount = len(record.Feature.LookupListIndex)
        path = Path(folder) / label
        stripped.save(path)
        first_stage = harfbuzz_shape.Shaper(path)
        for code, cells in VERTICAL_CELLS.items():
            for features in ((), ("vert=0", "vrt2")):
                shaped = first_stage.shape(f"あ{chr(code)}い", "ja", True, features)
                check([g[0] for g in shaped] == [font.getGlyphID(cmap[0x3042]), font.getGlyphID(stage_one["vert"][code]),
                                                 font.getGlyphID(cmap[0x3044])]
                      and shaped[1][3] == -cells * em,
                      f"{label}: U+{code:04X} does not keep the {cells}-cell vertical form when the cells are not split")
        first_stage.close()


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
            # 縦組の組み方 (1 セルずつの字に分ける 2 段目) は check_vertical_cells が検査する。ここは 1 段目まで
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
    # 2 段目の、1 つ目の字 (輪郭は 2 セル・3 セルの字のまま)。check_vertical_cells が枠を検査する
    vertical_dashes |= {values[0] for values in gsub_multiple(font, "vert").values()}
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
