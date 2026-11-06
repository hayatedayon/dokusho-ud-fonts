"""分数の数字 (分子と分母) を作る。build.py が使う。

元のフォントで小さい数字は、上付きの ¹ ² ³ ⁴ (BIZ UDP の字) だけで、分母の字は無い。BIZ UD・
BIZ UDP の frac は 1 2 3 を上付きにするだけで、1/2 は分母も上付きになり、4/5 は変わらない。

1. 上付きの数字 0〜9 をそろえる。1〜4 はデザインされた ¹ ² ³ ⁴。0・5〜9 は、普通の数字を、¹ ² ³ ⁴
   と同じ割合で縮め、同じだけ線を太らせて作る (割合と太さは、1〜4 と ¹ ² ³ ⁴ を測って求める。
   ただ縮めると、線が細くなって ¹ ² ³ ⁴ とそろわない)。⁰ ⁵ ⁶ ⁷ ⁸ ⁹ (U+2070・U+2075〜2079) の文字も
   割り当てる
2. 分子と分母の数字 0〜9 は、上付きの数字と同じ形で、左右の空きを、普通の数字の空きを同じ割合で
   縮めたものにする (上付きの数字は等幅で、¹ の右は大きく空く)。分母は、下が数字の下
   (ベースライン) にそろうまで下げる
3. 分数の斜線は、BIZ UDP の分数の斜線 (frac が / に使う字) を、幅 0 にして分子と分母に食い込ませた字。
   斜線の直前の分子と直後の分母は、字ごとに字送りを決めた別の字にし、数字と斜線のインクのいちばん
   近い所を、BIZ UDP の合成済みの分数 (¼ ½ ¾ ⅓ ⅔ ⅕) の中央値にそろえる (カーニングの代わり)
4. frac・numr・dnom・sups を作り直す。frac は分数の数字だけを置き換える: / ⁄ ／ の前に続く数字を
   分子に、分子の後の斜線を分数の斜線に、その後に続く数字を分母にする (1 1/2 の 1 はそのまま)

作った字にはヒンティングを付けない (BIZ UDP の命令は、上付きの高さに合わせて字を動かすので、
下げた字や作った字には使えない)。
"""

import math
from array import array
from statistics import median

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates
from fontTools.ttLib.tables.ttProgram import Program

import latin_symbols

DIGITS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
SUPERSCRIPTS = {1: 0x00B9, 2: 0x00B2, 3: 0x00B3, 4: 0x2074}  # 元のフォントにある上付きの数字
NEW_SUPERSCRIPTS = {0: 0x2070, 5: 0x2075, 6: 0x2076, 7: 0x2077, 8: 0x2078, 9: 0x2079}
FULLWIDTH_DIGIT = 0xFF10
SLASHES = [0x002F, 0x2044, 0xFF0F]  # 分数の斜線にする字 (/ ⁄ ／)


# --- 輪郭 -----------------------------------------------------------------------------------

def contours(font: TTFont, name: str) -> list[list[tuple[float, float, bool]]]:
    """グリフの輪郭。点 (x, y, 曲線の上の点か) の並び"""
    coordinates, ends, flags = font["glyf"][name].getCoordinates(font["glyf"])
    result, start = [], 0
    for end in ends:
        result.append([(x, y, bool(flags[i] & 1)) for i, (x, y) in enumerate(coordinates[start:end + 1], start)])
        start = end + 1
    return result


def segments(contour):
    """輪郭を、2 次の曲線 (始点, 制御点, 終点) と直線 (始点, None, 終点) に分ける"""
    points = list(contour)
    if not any(on for _x, _y, on in points):
        raise SystemExit("a contour without on-curve points")
    while not points[0][2]:
        points = points[1:] + points[:1]
    result, n = [], len(points)
    i = 0
    while i < n:
        start = points[i][:2]
        nxt = points[(i + 1) % n]
        if nxt[2]:
            result.append((start, None, nxt[:2]))
            i += 1
            continue
        # 曲線。制御点が続くときは、間に曲線の上の点があるとみなす
        j = i + 1
        control = nxt[:2]
        while True:
            after = points[(j + 1) % n]
            if after[2]:
                result.append((start, control, after[:2]))
                i = j + 1
                break
            middle = ((control[0] + after[0]) / 2, (control[1] + after[1]) / 2)
            result.append((start, control, middle))
            start, control, j = middle, after[:2], j + 1
    return result


def crossings(outline, axis: int, value: float) -> list[float]:
    """輪郭と、axis (0 は x、1 は y) が value の直線が交わる所の、もう一方の座標 (小さい順)"""
    other = 1 - axis
    found = []
    for contour in outline:
        for p0, c, p1 in segments(contour):
            if c is None:
                a, b = p0[axis], p1[axis]
                if (a <= value < b) or (b <= value < a):
                    t = (value - a) / (b - a)
                    found.append(p0[other] + t * (p1[other] - p0[other]))
                continue
            # (1-t)^2 p0 + 2t(1-t) c + t^2 p1 = value
            a = p0[axis] - 2 * c[axis] + p1[axis]
            b = 2 * (c[axis] - p0[axis])
            k = p0[axis] - value
            roots = []
            if abs(a) < 1e-9:
                if abs(b) > 1e-9:
                    roots = [-k / b]
            else:
                disc = b * b - 4 * a * k
                if disc >= 0:
                    r = math.sqrt(disc)
                    roots = [(-b - r) / (2 * a), (-b + r) / (2 * a)]
            for t in roots:
                if 0 <= t < 1:
                    found.append((1 - t) ** 2 * p0[other] + 2 * t * (1 - t) * c[other] + t * t * p1[other])
    return sorted(found)


def runs(outline, axis: int, value: float) -> list[tuple[float, float]]:
    """直線の上の、インクのある区間"""
    points = crossings(outline, axis, value)
    return list(zip(points[0::2], points[1::2]))


def bounds(outline) -> tuple[float, float, float, float]:
    xs = [x for contour in outline for x, _y, _on in contour]
    ys = [y for contour in outline for _x, y, _on in contour]
    return min(xs), min(ys), max(xs), max(ys)


# --- 測る -----------------------------------------------------------------------------------

def measure(outline) -> dict[str, float]:
    """インクの幅と高さ、縦の線 (1 の幹) と横の線 (2 の下の線) の太さを測るための値"""
    x0, y0, x1, y1 = bounds(outline)
    return {"width": x1 - x0, "height": y1 - y0, "x0": x0, "y0": y0, "x1": x1, "y1": y1}


def vertical_stem(outline) -> float:
    """縦の線の太さ (高さの真ん中を横に切った、いちばん太いインク)"""
    b = measure(outline)
    return max(end - start for start, end in runs(outline, 1, (b["y0"] + b["y1"]) / 2))


def horizontal_stroke(outline, which: str) -> float:
    """横の線の太さ (幅の真ん中を縦に切った、いちばん下か上のインク)"""
    b = measure(outline)
    pieces = runs(outline, 0, (b["x0"] + b["x1"]) / 2)
    start, end = pieces[0] if which == "bottom" else pieces[-1]
    return end - start


def fit(font: TTFont) -> dict[str, float]:
    """普通の数字 1〜4 を ¹ ² ³ ⁴ にする、縮める割合 (sx・sy) と太らせる太さ (ex・ey)。

    上付きの字 = 普通の字を sx・sy 倍に縮め、線を横に ex、縦に ey だけ太らせたもの、とみなす。
    太らせると、インクの幅も線の太さも ex だけ増えるので、幅から線の太さを引いた値は sx 倍になる:
      幅 (上付き) - 線 (上付き) = sx × (幅 - 線)、 線 (上付き) = sx × 線 + ex  (縦も同じ)
    """
    cmap = font.getBestCmap()
    digit = {d: contours(font, cmap[0x30 + d]) for d in range(10)}
    sup = {d: contours(font, cmap[code]) for d, code in SUPERSCRIPTS.items()}
    v, v_sup = vertical_stem(digit[1]), vertical_stem(sup[1])
    h = (horizontal_stroke(digit[2], "bottom") + horizontal_stroke(digit[3], "top")) / 2
    h_sup = (horizontal_stroke(sup[2], "bottom") + horizontal_stroke(sup[3], "top")) / 2
    width = sum(measure(digit[d])["width"] for d in (2, 3, 4)) / 3
    width_sup = sum(measure(sup[d])["width"] for d in (2, 3, 4)) / 3
    height = sum(measure(digit[d])["height"] for d in (1, 2, 3, 4)) / 4
    height_sup = sum(measure(sup[d])["height"] for d in (1, 2, 3, 4)) / 4
    sx = (width_sup - v_sup) / (width - v)
    sy = (height_sup - h_sup) / (height - h)
    return {"sx": sx, "sy": sy, "ex": v_sup - sx * v, "ey": h_sup - sy * h,
            "stem": v, "stem_sup": v_sup, "stroke": h, "stroke_sup": h_sup}


def gap(left, right, step: float = 4.0) -> float | None:
    """left の輪郭の右から、right の輪郭の左までの、横の距離のいちばん小さいもの (同じ高さどうし)"""
    _a, a0, _a1, a1 = bounds(left)
    _b, b0, _b1, b1 = bounds(right)
    low, high = max(a0, b0), min(a1, b1)
    best = None
    y = low + step / 2
    while y < high:
        a, b = crossings(left, 1, y), crossings(right, 1, y)
        if a and b:
            distance = b[0] - a[-1]
            best = distance if best is None else min(best, distance)
        y += step
    return best


def fraction_gaps(font: TTFont) -> tuple[list[float], list[float]]:
    """合成済みの分数 (¼ ½ ¾ ⅓ … ⅞) の、分子から斜線、斜線から分母までのインクの距離"""
    cmap = font.getBestCmap()
    before, after = [], []
    for code in [0x00BC, 0x00BD, 0x00BE, *range(0x2153, 0x215F)]:
        if code not in cmap:
            continue
        outline = contours(font, cmap[code])
        slash = max(outline, key=lambda c: bounds([c])[3] - bounds([c])[1])
        rest = [c for c in outline if c is not slash]
        middle = (bounds([slash])[1] + bounds([slash])[3]) / 2  # 4 の内側の輪郭も、中心で分子と分母に分ける
        numerator = [c for c in rest if (bounds([c])[1] + bounds([c])[3]) / 2 > middle]
        denominator = [c for c in rest if (bounds([c])[1] + bounds([c])[3]) / 2 <= middle]
        if numerator and denominator:
            before.append(gap(numerator, [slash]))
            after.append(gap([slash], denominator))
    return before, after


# --- 太らせる (FreeType の FT_Outline_EmboldenXY と同じやり方) ----------------------------------

def _orientation(contour) -> float:
    """面積の符号 (TrueType の外側の輪郭は時計回りで、負)"""
    area = 0.0
    for i, (x0, y0, _on) in enumerate(contour):
        x1, y1, _ = contour[(i + 1) % len(contour)]
        area += x0 * y1 - x1 * y0
    return area


def embolden(outline, ex: float, ey: float):
    """輪郭を、横に ex、縦に ey だけ太らせる (インクの幅・高さも ex・ey 増える)。点 (制御点も)
    ごとに、前後の辺の外向きの法線の間の向きへ動かす。とがった角では動かす量を抑える"""
    total = sum(_orientation(c) for c in outline)
    truetype = total < 0  # 時計回りが外側
    xs, ys = ex / 2, ey / 2
    result = []
    for contour in outline:
        n = len(contour)
        moved = []
        for i in range(n):
            px, py, on = contour[i]

            def unit(dx, dy):
                length = math.hypot(dx, dy)
                return (dx / length, dy / length, length) if length else None

            # 前と後の、位置の違う点
            k = 1
            incoming = None
            while k < n and incoming is None:
                qx, qy, _ = contour[(i - k) % n]
                incoming = unit(px - qx, py - qy)
                k += 1
            k = 1
            outgoing = None
            while k < n and outgoing is None:
                qx, qy, _ = contour[(i + k) % n]
                outgoing = unit(qx - px, qy - py)
                k += 1
            if incoming is None or outgoing is None:
                moved.append((px, py, on))
                continue
            ix, iy, li = incoming
            ox, oy, lo = outgoing
            d = ix * ox + iy * oy + 1  # 1 + cos (0 に近いほど、とがった角)
            shift_x, shift_y = 0.0, 0.0
            if d > 1 / 16:  # FreeType は -0.9375 より鈍い角だけ動かす
                shift_x, shift_y = iy + oy, ix + ox
                if truetype:
                    shift_x = -shift_x
                else:
                    shift_y = -shift_y
                q = ox * iy - oy * ix
                if truetype:
                    q = -q
                limit = min(li, lo)
                shift_x = shift_x * xs / d if xs * q <= limit * d else shift_x * limit / q
                shift_y = shift_y * ys / d if ys * q <= limit * d else shift_y * limit / q
            moved.append((px + xs + shift_x, py + ys + shift_y, on))
        result.append(moved)
    return result


def transform(outline, sx: float, sy: float, dx: float = 0.0, dy: float = 0.0):
    return [[(x * sx + dx, y * sy + dy, on) for x, y, on in contour] for contour in outline]


def make_glyph(outline) -> Glyph:
    """輪郭から、ヒンティングの無いグリフを作る (座標は整数に丸める)"""
    glyph = Glyph()
    points, flags, ends = [], [], []
    for contour in outline:
        for x, y, on in contour:
            points.append((round(x), round(y)))
            flags.append(1 if on else 0)
        ends.append(len(points) - 1)
    glyph.coordinates = GlyphCoordinates(points)
    glyph.flags = array("B", flags)
    glyph.endPtsOfContours = ends
    glyph.numberOfContours = len(ends)
    glyph.program = Program()
    glyph.program.fromBytecode(b"")
    return glyph


# --- 組み込む -------------------------------------------------------------------------------

SUPS_SUFFIX = ".sups"
NUMR_SUFFIX = ".numr"
DNOM_SUFFIX = ".dnom"
FRAC_SUFFIX = ".frac"


def _add_glyph(font: TTFont, name: str, glyph: Glyph, advance: int, vertical: tuple[int, int]) -> None:
    if name in font["hmtx"].metrics:
        raise SystemExit(f"{name} is already in the font")
    order = font.getGlyphOrder() + [name]
    font.setGlyphOrder(order)
    font["glyf"].glyphOrder = order
    font["glyf"][name] = glyph
    glyph.recalcBounds(font["glyf"])
    font["hmtx"][name] = (advance, glyph.xMin)
    font["vmtx"][name] = vertical


def _single(subtables) -> dict:
    if len(subtables) != 1:
        raise SystemExit(f"expected one single substitution, found {len(subtables)}")
    return subtables[0].mapping


def _lookup(gsub, kind: int, subtable) -> int:
    lookup = otTables.Lookup()
    lookup.LookupType, lookup.LookupFlag, lookup.SubTable, lookup.SubTableCount = kind, 0, [subtable], 1
    gsub.LookupList.Lookup.append(lookup)
    gsub.LookupList.LookupCount = len(gsub.LookupList.Lookup)
    return len(gsub.LookupList.Lookup) - 1


def _coverage(font: TTFont, glyphs) -> otTables.Coverage:
    coverage = otTables.Coverage()
    coverage.glyphs = sorted(set(glyphs), key=font.getGlyphID)
    return coverage


def add(font: TTFont, udp: TTFont) -> dict:
    """上付き・分子・分母の数字と分数の斜線を足し、frac・numr・dnom・sups を作り直す。udp は
    BIZ UDP (¾ の組み方を測る。読書 UD の ¾ は BIZ UD の半角の字)"""
    import build  # feature_lookups など (build.py がこのモジュールを読み込むので、ここで読み込む)

    gsub = font["GSUB"].table
    cmap = font.getBestCmap()
    digits = [cmap[0x30 + d] for d in range(10)]
    fullwidth = [cmap[FULLWIDTH_DIGIT + d] for d in range(10)]
    reference = cmap[SUPERSCRIPTS[1]]
    # 作る字の幅は ¹ と同じにする (BIZ UDP の ⁴ は、太字では ¹ ² ³ と幅が少し違う。⁴ はそのまま)
    advance = font["hmtx"][reference][0]
    ref_bounds = bounds(contours(font, reference))
    origin_y = font["vmtx"][reference][1] + ref_bounds[3]  # 縦組の字の枠の上 (y)
    v_advance = font["vmtx"][reference][0]

    # 1. 上付きの数字。0・5〜9 は、普通の数字を ¹ ² ³ ⁴ と同じ割合で縮めて太らせる。高さは、
    #    同じやり方で 1〜4 から作った字の下を ¹ ² ³ ⁴ の下にそろえる量で決める
    params = fit(font)

    def shrink(d: int):
        return embolden(transform(contours(font, digits[d]), params["sx"], params["sy"]),
                        params["ex"], params["ey"])

    rise = sum(bounds(contours(font, cmap[code]))[1] - bounds(shrink(d))[1]
               for d, code in SUPERSCRIPTS.items()) / len(SUPERSCRIPTS)
    superscripts: dict[int, str] = {d: cmap[code] for d, code in SUPERSCRIPTS.items()}
    outlines: dict[int, list] = {d: contours(font, name) for d, name in superscripts.items()}
    for d in NEW_SUPERSCRIPTS:
        outline = shrink(d)
        x0, _y0, x1, _y1 = bounds(outline)
        outline = transform(outline, 1, 1, (advance - (x1 - x0)) / 2 - x0, rise)
        name = DIGITS[d] + SUPS_SUFFIX
        glyph = make_glyph(outline)
        _add_glyph(font, name, glyph, advance, (v_advance, round(origin_y - max(y for c in outline for _x, y, _o in c))))
        superscripts[d], outlines[d] = name, contours(font, name)
    for d, code in NEW_SUPERSCRIPTS.items():
        if code in cmap:
            raise SystemExit(f"U+{code:04X} is already in the font")
        for table in font["cmap"].tables:
            if table.isUnicode():  # 同じ表を分け合う subtable もある
                table.cmap[code] = superscripts[d]

    # 2. 分子と分母の数字。上付きの数字と同じ形で、左右の空き (side) は、普通の数字 (幅の狭い 1 を
    #    除く) の空きの平均を、上付きと同じ割合で縮めたもの。分母は、上付きの下 (rise) から
    #    ベースラインまで下げる
    sides = []
    for d in range(10):
        if d != 1:
            x0, _y0, x1, _y1 = bounds(contours(font, digits[d]))
            sides.append((font["hmtx"][digits[d]][0] - (x1 - x0)) / 2)
    side = params["sx"] * sum(sides) / len(sides)

    # 3. 分数の斜線と、斜線の前後の数字。BIZ UDP の frac が / に使う字を、幅 0 にして (インクの真ん中が
    #    原点)、分子と分母に食い込ませる。斜線の直前の分子 (.numr.last) と直後の分母 (.dnom.first) は、
    #    字送りと左の空きを字ごとに決め、数字と斜線のインクの (同じ高さどうしの) いちばん近い所を、
    #    BIZ UDP の合成済みの分数 (¼ ½ ¾ ⅓ …) の中央値にする (1 は狭く、4 は斜線と平行で、
    #    外形の箱で決めると空き方がばらつく)
    frac_mapping = _single(build.feature_subtables(gsub, "frac", "mapping"))
    wide_slash = frac_mapping.get(cmap[0x2F])
    if wide_slash is None:
        raise SystemExit("frac has no fraction slash for /")
    slash_outline = contours(font, wide_slash)
    sx0, _sy0, sx1, _sy1 = bounds(slash_outline)
    slash_outline = transform(slash_outline, 1, 1, -(sx0 + sx1) / 2, 0)
    gaps_before, gaps_after = fraction_gaps(udp)
    if not gaps_before:
        raise SystemExit("BIZ UDP has no fractions to measure")
    target_before, target_after = median(gaps_before), median(gaps_after)
    numerators: dict[int, str] = {}
    denominators: dict[int, str] = {}
    lasts: dict[int, str] = {}
    firsts: dict[int, str] = {}

    def put(name: str, outline, advance: float) -> str:
        if advance < 0:
            raise SystemExit(f"{name} would have a negative width")
        _add_glyph(font, name, make_glyph(outline), round(advance),
                   (v_advance, round(origin_y - max(y for c in outline for _x, y, _o in c))))
        return name

    for d in range(10):
        x0, _y0, x1, _y1 = bounds(outlines[d])
        width = x1 - x0 + 2 * side
        numerator = transform(outlines[d], 1, 1, side - x0, 0)
        denominator = transform(outlines[d], 1, 1, side - x0, -rise)
        numerators[d] = put(DIGITS[d] + NUMR_SUFFIX, numerator, width)
        denominators[d] = put(DIGITS[d] + DNOM_SUFFIX, denominator, width)
        # 最後の分子: 字送りの終わりが斜線の原点。字送りを増やすと、斜線までの距離も同じだけ増える
        distance = gap(numerator, slash_outline)
        lasts[d] = put(DIGITS[d] + NUMR_SUFFIX + ".last", numerator, target_before - distance)
        # 最初の分母: 原点が斜線の原点 (斜線の幅は 0)。インクの左端を dx にする
        at_zero = transform(outlines[d], 1, 1, -x0, -rise)
        dx = target_after - gap(slash_outline, at_zero)
        firsts[d] = put(DIGITS[d] + DNOM_SUFFIX + ".first", transform(at_zero, 1, 1, dx, 0), dx + (x1 - x0) + side)
    fraction_slash = "fraction" + FRAC_SUFFIX
    _add_glyph(font, fraction_slash, make_glyph(slash_outline), 0, font["vmtx"][wide_slash])
    for tag in ("frac", "numr", "sups"):
        build.ensure_own_lookups(gsub, tag, "mapping")
    numr_mapping = _single(build.feature_subtables(gsub, "numr", "mapping"))
    sups_mapping = _single(build.feature_subtables(gsub, "sups", "mapping"))
    for d in range(10):
        for source in (digits[d], fullwidth[d]):
            numr_mapping[source] = numerators[d]
            sups_mapping[source] = superscripts[d]
    slashes = [cmap[code] for code in SLASHES]
    # frac は、下の文脈の lookup で作り直す (BIZ UD の frac の lookup は、数字と / を無条件に置き換える)
    frac_lookups = build.feature_lookups(gsub, "frac")

    # dnom (新しい機能): 数字を分母に、/ を分数の斜線に (BIZ UDP の dnom は / だけ)
    dnom = otTables.SingleSubst()
    dnom.mapping = {source: denominators[d] for d in range(10) for source in (digits[d], fullwidth[d])}
    dnom.mapping[cmap[0x2F]] = wide_slash  # BIZ UDP の dnom と同じ
    dnom_index = _lookup(gsub, 1, dnom)
    feature = otTables.Feature()
    feature.FeatureParams, feature.LookupListIndex, feature.LookupCount = None, [dnom_index], 1
    record = otTables.FeatureRecord()
    record.FeatureTag, record.Feature = "dnom", feature
    gsub.FeatureList.FeatureRecord.append(record)
    gsub.FeatureList.FeatureCount = len(gsub.FeatureList.FeatureRecord)
    new_feature = len(gsub.FeatureList.FeatureRecord) - 1
    for script in gsub.ScriptList.ScriptRecord:
        for system in [script.Script.DefaultLangSys] + [r.LangSys for r in script.Script.LangSysRecord]:
            if system is not None:
                system.FeatureIndex = system.FeatureIndex + [new_feature]
                system.FeatureCount = len(system.FeatureIndex)

    # frac: 分数の数字だけを置き換える。1 1/2 の 1 や、and/or の / はそのまま
    # 1. 右から左へ (reverse chaining): / の直前の数字を最後の分子に、分子の直前の数字を分子に
    #    (1 1/2 の、空白の前の 1 は分子にならない)
    # 2. 左から右へ: 最後の分子の後の / を分数の斜線に、分数の斜線の直後の数字を最初の分母に、
    #    分母の後の数字を分母に (1/25 は、1 が最後の分子、/ が分数の斜線、2 が最初の分母、5 が分母)
    # ⁄ (U+2044) では、文字を並べる仕組みが分子に numr、分母に dnom も掛けるので、すでに分子・
    # 分母になった字も、同じように置き換える
    def numbers(d: int) -> list[str]:
        return [digits[d], fullwidth[d]]

    def reverse(lookahead: list[str], targets: dict[int, str], also: dict[int, str]) -> otTables.ReverseChainSingleSubst:
        mapping = {source: targets[d] for d in range(10) for source in numbers(d)}
        mapping.update({also[d]: targets[d] for d in range(10)})
        subtable = otTables.ReverseChainSingleSubst()
        subtable.Format = 1
        subtable.Coverage = _coverage(font, mapping)
        subtable.Substitute = [mapping[name] for name in subtable.Coverage.glyphs]
        subtable.GlyphCount = len(subtable.Substitute)
        subtable.BacktrackGlyphCount, subtable.BacktrackCoverage = 0, []
        subtable.LookAheadGlyphCount, subtable.LookAheadCoverage = 1, [_coverage(font, lookahead)]
        return subtable

    backwards = [reverse(slashes, lasts, numerators),
                 reverse([*numerators.values(), *lasts.values()], numerators, numerators)]
    lookup = otTables.Lookup()
    lookup.LookupType, lookup.LookupFlag, lookup.SubTable, lookup.SubTableCount = 8, 0, backwards, len(backwards)
    gsub.LookupList.Lookup.append(lookup)
    gsub.LookupList.LookupCount = len(gsub.LookupList.Lookup)
    reverse_index = len(gsub.LookupList.Lookup) - 1

    def single(mapping: dict) -> int:
        subtable = otTables.SingleSubst()
        subtable.mapping = mapping
        return _lookup(gsub, 1, subtable)

    def to(targets: dict[int, str]) -> dict[str, str]:
        mapping = {source: targets[d] for d in range(10) for source in numbers(d)}
        mapping.update({denominators[d]: targets[d] for d in range(10)})  # dnom で分母になった字
        return mapping

    rules = [  # (前の字, 字, 置き換え)。字ごとに、最初に合うもの
        ([*lasts.values()], slashes, single({slash: fraction_slash for slash in slashes})),
        ([fraction_slash], [*to(firsts)], single(to(firsts))),
        ([*firsts.values(), *denominators.values()], [*to(denominators)], single(to(denominators))),
    ]
    chains = []
    for backtrack, inputs, nested in rules:
        chain = otTables.ChainContextSubst()
        chain.Format = 3
        chain.BacktrackGlyphCount, chain.BacktrackCoverage = 1, [_coverage(font, backtrack)]
        chain.InputGlyphCount, chain.InputCoverage = 1, [_coverage(font, inputs)]
        chain.LookAheadGlyphCount, chain.LookAheadCoverage = 0, []
        substitution = otTables.SubstLookupRecord()
        substitution.SequenceIndex, substitution.LookupListIndex = 0, nested
        chain.SubstCount, chain.SubstLookupRecord = 1, [substitution]
        chains.append(chain)
    lookup = otTables.Lookup()
    lookup.LookupType, lookup.LookupFlag, lookup.SubTable, lookup.SubTableCount = 6, 0, chains, len(chains)
    gsub.LookupList.Lookup.append(lookup)
    gsub.LookupList.LookupCount = len(gsub.LookupList.Lookup)
    forward_index = len(gsub.LookupList.Lookup) - 1
    for record in gsub.FeatureList.FeatureRecord:
        if record.FeatureTag == "frac":
            record.Feature.LookupListIndex = [reverse_index, forward_index]
            record.Feature.LookupCount = 2
    # BIZ UD の frac の lookup は、ほかの機能からは使われない (ensure_own_lookups)。中身を空にする
    for index in frac_lookups:
        for subtable in build.subtables(gsub, index, "mapping"):
            subtable.mapping = {}

    # 字形の候補 (aalt): 数字に、上付きの数字を出す (BIZ UD は 1〜3 だけ)
    singles = build.feature_subtables(gsub, "aalt", "mapping")
    multiples = build.feature_subtables(gsub, "aalt", "alternates")
    current = build.alternates(gsub, "aalt", set(digits) | set(fullwidth))
    for d in range(10):
        for source in (digits[d], fullwidth[d]):
            values = list(current.get(source, []))
            if superscripts[d] not in values:
                build.put_alternates(singles, multiples, source, values + [superscripts[d]])

    latin_symbols.sort_features(gsub)
    return {"superscripts": len(NEW_SUPERSCRIPTS), "denominators": len(denominators), "side": side,
            "params": params, "rise": rise, "gaps": (target_before, target_after)}
