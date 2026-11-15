"""カーニング (kern): 宣言した値・実際に組んだ効果・輪郭の接触・除外。"""

import math
import unicodedata

from fontTools.ttLib import TTFont

import kerning
import spec

from .common import FontContext, check
from .fonttables import outputs
from .geometry import flattened, ink_gap, row


def kerning_pairs(font: TTFont) -> dict[tuple[str, str], int]:
    """できた GPOS の実効 kern ペアを展開する。生成用のクラス・文字範囲には依存しない。

    同じ lookup の先に一致したゼロ値も後のサブテーブルを遮る。Format 2 は Coverage に
    入った左の字について、クラス0を含むすべての右の字に一致する。返すのは実効値が非ゼロのペア。
    """
    table = font["GPOS"].table
    indexes = sorted({i for r in table.FeatureList.FeatureRecord if r.FeatureTag == "kern"
                      for i in r.Feature.LookupListIndex})
    result = {}
    for index in indexes:
        pairs = {}
        covered_left = set()
        for raw in table.LookupList.Lookup[index].SubTable:
            sub = getattr(raw, "ExtSubTable", raw)
            check(sub.ValueFormat1 in (0, 4) and sub.ValueFormat2 == 0,
                  "kern collision check requires XAdvance-only pair positioning")
            if sub.Format == 1:
                for first, pair_set in zip(sub.Coverage.glyphs, sub.PairSet):
                    if first in covered_left:
                        continue
                    for record in pair_set.PairValueRecord:
                        pairs.setdefault((first, record.SecondGlyph), getattr(record.Value1, "XAdvance", 0))
            elif sub.Format == 2:
                classes = {}
                for glyph in font.getGlyphOrder():
                    classes.setdefault(sub.ClassDef2.classDefs.get(glyph, 0), []).append(glyph)
                for first in sub.Coverage.glyphs:
                    if first in covered_left:
                        continue
                    row = sub.Class1Record[sub.ClassDef1.classDefs.get(first, 0)]
                    for cls, record in enumerate(row.Class2Record):
                        amount = getattr(record.Value1, "XAdvance", 0)
                        # クラス0の巨大なゼロ行は展開せず covered_left で表現する。
                        # 明示クラスのゼロ値と、先行する Format 1 のゼロ値は pairs に残す。
                        if amount or cls != 0:
                            for second in classes.get(cls, ()):
                                pairs.setdefault((first, second), amount)
                    covered_left.add(first)
            else:
                check(False, f"unsupported kern pair format: {sub.Format}")
        for pair, amount in pairs.items():
            if amount:
                result[pair] = result.get(pair, 0) + amount
    return {pair: amount for pair, amount in result.items() if amount}


def check_kern_lookup_precedence() -> None:
    """ゼロ値による遮断、Format 1/2 の混在、別 lookup の加算を小さな表で検査する。"""
    from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

    cases = [
        # Format 2 のクラス0のゼロで、後ろの V-a は遮断される。
        ("pos [V] [A] -50; subtable; pos [V] [a] -40;", {("V", "A"): -50}),
        # Format 1 が先に一致するのは、その具体的なペアだけ。
        ("pos V A -50; subtable; pos [V] [a] -40;", {("V", "A"): -50, ("V", "a"): -40}),
        # Format 1 の明示的なゼロ値も後続を遮る。
        ("pos V a 0; subtable; pos [V] [a] -40;", {}),
    ]
    for body, expected in cases:
        font = TTFont()
        font.setGlyphOrder([".notdef", "V", "A", "a"])
        addOpenTypeFeaturesFromString(font, "feature kern { lookup Test { " + body + " } Test; } kern;", tables=["GPOS"])
        check(kerning_pairs(font) == expected, f"kern subtable precedence: {body}")
    font = TTFont()
    font.setGlyphOrder([".notdef", "V", "A", "a"])
    addOpenTypeFeaturesFromString(font, """feature kern {
        lookup First { pos [V] [A] -50; } First;
        lookup Second { pos [V] [a] -40; } Second;
    } kern;""", tables=["GPOS"])
    check(kerning_pairs(font) == {("V", "A"): -50, ("V", "a"): -40}, "kern precedence leaked across lookups")


def check_kern_shaping(label: str, font: TTFont, shaper, family: str, effective=None) -> int:
    """宣言した全ペアを、アクセント付き・除外字を含めて実際に組み、設定値と照合する。

    衝突検査とは別に行う。無効になったペアは衝突しなくても、この検査で不合格になる。
    GPOS の展開結果も HarfBuzz と突き合わせ、サブテーブルの解釈違いを検出する。
    """
    cmap, order = font.getBestCmap(), font.getGlyphOrder()
    variants = {}
    for code in spec.LATIN:
        if code in cmap and unicodedata.category(chr(code)).startswith("L"):
            base = unicodedata.normalize("NFD", chr(code))[0]
            variants.setdefault(base, set()).add(chr(code))
    for char in ".,":
        variants[char] = {char}
    if effective is None:
        effective = kerning_pairs(font)
    declared = {}
    em = font["head"].unitsPerEm
    for left, right, mincho, gothic in kerning.PAIRS:
        adjustment = kerning.adjustment(em, family, mincho, gothic)
        for a in left:
            for b in right:
                for first in sorted(variants.get(a, ())):
                    for second in sorted(variants.get(b, ())):
                        amount = 0 if first in kerning.EXCLUDED_LEFT else adjustment
                        text = first + second
                        check(text not in declared or declared[text] == amount, f"{label}: conflicting kern declarations for {text}")
                        declared[text] = amount
    wrong = []
    for text, expected in sorted(declared.items()):
        plain = shaper.shape(text, "en", features=("kern=0",))
        kerned = shaper.shape(text, "en")
        actual = sum(r[2] for r in kerned) - sum(r[2] for r in plain)
        if actual != expected:
            wrong.append((text, expected, actual))
        if len(kerned) == 2:
            pair = (order[kerned[0][0]], order[kerned[1][0]])
            check(effective.get(pair, 0) == actual, f"{label}: GPOS expansion disagrees with HarfBuzz on {text}")
    check(bool(declared), f"{label}: no declared kern pairs were shaped")
    check(not wrong, f"{label}: {len(wrong)} declared kern pairs have wrong advances (text, expected, actual): {wrong[:12]}")
    return len(declared)


def outline_distance(left, right, limit: float = math.inf) -> float:
    """折れ線にした２字の輪郭間の最短距離。limit より広い場合は limit を返す。

    同じ高さの水平断面だけでは、水平辺の端や斜めに近づいた角の間隔を見落とす。
    セグメントの包囲矩形で候補を絞り、交差と点・線分間の距離を確かめる。
    """
    def edges(polygons):
        return [(x, y, X, Y, min(x, X), min(y, Y), max(x, X), max(y, Y))
                for polygon in polygons for (x, y), (X, Y) in zip(polygon, polygon[1:] + polygon[:1])]

    def point_distance(x, y, line):
        dx, dy = line[2] - line[0], line[3] - line[1]
        length = dx * dx + dy * dy
        t = max(0, min(1, ((x - line[0]) * dx + (y - line[1]) * dy) / length)) if length else 0
        return (x - line[0] - t * dx) ** 2 + (y - line[1] - t * dy) ** 2

    best = limit * limit
    a, b = edges(left), edges(right)
    for p in a:
        for q in b:
            dx, dy = max(p[4] - q[6], q[4] - p[6], 0), max(p[5] - q[7], q[5] - p[7], 0)
            if dx * dx + dy * dy >= best:
                continue
            ax, ay, bx, by = p[2] - p[0], p[3] - p[1], q[2] - q[0], q[3] - q[1]
            determinant = ax * by - ay * bx
            if determinant:
                ox, oy = q[0] - p[0], q[1] - p[1]
                t, u = (ox * by - oy * bx) / determinant, (ox * ay - oy * ax) / determinant
                if 0 <= t <= 1 and 0 <= u <= 1:
                    return 0.0
            best = min(best, point_distance(p[0], p[1], q), point_distance(p[2], p[3], q),
                       point_distance(q[0], q[1], p), point_distance(q[2], q[3], p))
    return math.sqrt(best)


def check_outline_distance() -> None:
    a = [[(0, 0), (10, 0), (10, 10), (0, 10)]]
    diagonal = [[(20, 20), (30, 20), (30, 30), (20, 30)]]
    crossing = [[(5, 5), (15, 5), (15, 15), (5, 15)]]
    touching = [[(10, 0), (20, 0), (20, 10), (10, 10)]]
    check(abs(outline_distance(a, diagonal) - math.sqrt(200)) < 1e-6, "diagonal ink distance was not checked")
    check(outline_distance(a, diagonal, 5) == 5, "ink distance limit is not respected")
    check(outline_distance(a, crossing) == 0 and outline_distance(a, touching) == 0,
          "crossing or touching outlines were not detected")


def check_kern_contacts(label: str, font: TTFont, pairs=None) -> int:
    """全ペアの水平断面と輪郭間の最短距離を調べ、アクセントや角の近接も検査する。"""
    if pairs is None:
        pairs = kerning_pairs(font)
    minimum = font["head"].unitsPerEm / 100  # 1% em。接触していなくても極端に狭いペアは不合格。
    profiles, outlines = {}, {}
    for glyph in sorted({g for pair in pairs for g in pair}):
        polygons = flattened(font, glyph)
        outlines[glyph] = polygons
        ys = [y for polygon in polygons for _x, y in polygon]
        profile = {}
        for y in range(int(min(ys)) - 1, int(max(ys)) + 2):
            xs = row(polygons, y + 0.5)
            if xs:
                profile[y] = (xs[0], xs[-1])
        profiles[glyph] = profile
    bad = []
    for (first, second), amount in pairs.items():
        left, right = profiles[first], profiles[second]
        rows = left.keys() & right.keys()
        advance = font["hmtx"][first][0] + amount
        gap = min((advance + right[y][0] - left[y][1] for y in rows), default=math.inf)
        shifted = [[(x + advance, y) for x, y in polygon] for polygon in outlines[second]]
        gap = min(gap, outline_distance(outlines[first], shifted, minimum))
        if gap < minimum:
            bad.append((first, second, round(gap, 2)))
    check(bool(pairs), f"{label}: no kern pairs were checked")
    check(not bad, f"{label}: {len(bad)} of {len(pairs)} kern pairs have less than {minimum:.2f} units of ink space: {bad[:8]}")
    return len(pairs)


def check_kern_exclusions(label: str, font: TTFont, pairs: dict) -> None:
    """kern の入力字が、固定幅・縦組への置換先と重ならないことを表全体で検査する。"""
    inputs = {glyph for pair in pairs for glyph in pair}
    for tag in ("hwid", "fwid", "tnum", "vert", "vrt2"):
        overlap = inputs & outputs(font, (tag,))
        check(not overlap, f"{label}: kern includes {tag} output glyphs: {sorted(overlap)[:8]}")


def check_kern_pairs(ctx: FontContext) -> None:
    """宣言した全ペアの値・実際に組んだ効果・輪郭の接触・除外字。"""
    label = ctx.label
    family = ctx.family
    font = ctx.font
    shaper = ctx.shaper
    effective_kern = kerning_pairs(font)
    check_kern_shaping(label, font, shaper, family["key"], effective_kern)
    check_kern_contacts(label, font, effective_kern)
    check_kern_exclusions(label, font, effective_kern)


def check_kern_behavior(ctx: FontContext) -> None:
    """kern が当たる字・当たらない字 (固定幅・縦組・結合記号)。"""
    label = ctx.label
    font = ctx.font
    em = ctx.em
    order = ctx.order
    run = ctx.run
    width = ctx.width
    for text in ("Ťu", "Ťü", "T\u030cu", "T\u0330\u030cu", "ĽT"):
        check(run(text) == run(text, ("kern=0",)), f"{label}: projecting caron is kerned in {text}")
    for text in ("AV", "WA", "To", "Te", "YA", "LT", "Tó", "ÁV"):
        plain, kerned = run(text, ("kern=0",)), run(text)
        check(width(text) < width(text, ("kern=0",)), f"{label}: kern does not tighten {text}")
        check(width(text, ("kern=0",)) - width(text) <= em / 8, f"{label}: excessive kern on {text}")
        if len(kerned) == 2:
            left, right = kerned
            gap = ink_gap(flattened(font, order[left[0]], left[4], left[5]),
                          flattened(font, order[right[0]], left[2] + right[4], right[5]))
            check(gap is not None and gap > em / 50, f"{label}: kern makes {text} touch ({gap})")
        check([r[0] for r in plain] == [r[0] for r in kerned], f"{label}: kern changes glyphs of {text}")
    for text, features in [("漢字かな", ()), ("AV To", ("hwid",)), ("ＡＶ", ()),
                            ("AV To", ("fwid",)), ("0123456789", ("tnum",))]:
        check(run(text, features) == run(text, (*features, "kern=0")), f"{label}: kern changes fixed widths of {text}")
    check(run("AV To", vertical=True) == run("AV To", ("kern=0",), True), f"{label}: kern affects vertical text")
    # IgnoreMarks: 合成済みの字と、結合記号が残る字の両方で、基底字間に同じ詰めを適用する。
    for text in ("To", "Tõ", "Tő", "T̃o"):
        check(width(text, ("kern=0",)) - width(text) == width("To", ("kern=0",)) - width("To"),
              f"{label}: accents change the kern amount in {text}")
