"""小さい字の調整。追加数字には縦方向だけのヒント、試作ルビ仮名には任意の ss03 を用意する。

ルビ仮名は全角の枠を保ち、原字のインクの中心を基準に細い線をわずかに補強する。小書き仮名だけは
12% 大きくする。全面的なルビ書体ではなく、20 字を比較するための試作。通常の ruby と
本文の字形は変えない。横組・縦組の字形を別々に作り、原字と同じ送りを使う。
"""

from fontTools.ttLib.tables.ttProgram import Program

import fraction_digits
import latin_symbols

RUBY_KANA = "あめぬれゃゅょっがぱアメヌレャュョッガパ"
SMALL_KANA = "ゃゅょっャュョッ"


def hint_digits(font) -> int:
    """生成した数字を、役割ごとの共通の上下ゾーンに合わせる。元の cvt・fpgm は変更しない。

    細い横線の記号は丸めると消えるので対象外。元の ¹²³⁴ の命令は保つ。
    """
    count = 0
    # ¹ と同じ平らな上端を基準とし、分母の基準線は 0 にする。丸字のオーバーシュートや
    # 生成時の数単位の差を、本文サイズでは同じピクセル位置へ吸収する。別枠で cvt を追加する。
    cmap = font.getBestCmap()
    zones = {}
    shared = {}
    for role in ("sups", "numr", "dnom", "subs"):
        reference = cmap[0x00B9] if role == "sups" else "one." + role
        glyph = font["glyf"][reference]
        glyph.recalcBounds(font["glyf"])
        bounds = (0 if role == "dnom" else glyph.yMin, glyph.yMax)
        if bounds not in shared:
            start = len(font["cvt "].values)
            font["cvt "].values.extend(bounds)
            shared[bounds] = (start, start + 1)
        zones[role] = shared[bounds]
    prefixes = tuple(d + "." for d in fraction_digits.DIGITS)
    for name in font.getGlyphOrder():
        if not name.startswith(prefixes) or not any(s in name for s in (".sups", ".subs", ".numr", ".dnom")):
            continue
        glyph = font["glyf"][name]
        if glyph.isComposite() or glyph.numberOfContours <= 0:
            raise SystemExit(f"{name}: expected a simple generated digit")
        coords = glyph.coordinates
        bottom = min(range(len(coords)), key=lambda i: coords[i][1])
        top = max(range(len(coords)), key=lambda i: coords[i][1])
        role = next(role for role in zones if "." + role in name)
        lower_zone, upper_zone = zones[role]
        # IUP は輪郭をまたがない。内側の輪郭も同じ Y 方向の変換になるように、各輪郭の
        # 上下の極点を、グリッドに合わせた字全体の上下の間で補間して touch する。
        extrema, start = set(), 0
        for end in glyph.endPtsOfContours:
            points = range(start, end + 1)
            extrema.update((min(points, key=lambda i: coords[i][1]), max(points, key=lambda i: coords[i][1])))
            start = end + 1
        program = Program()
        assembly = [
            "PUSHB[ ]", "1", "SZPS[ ]", "SVTCA[0]", "RTG[ ]",
            # cut-in は１px。小サイズは共通ゾーンにそろえ、大きなサイズでは元の細部を保つ。
            "PUSHB[ ]", "64", "SCVTCI[ ]",
            "PUSHW[ ]", str(bottom), str(lower_zone), "MIAP[1]",
            "PUSHW[ ]", str(top), str(upper_zone), "MIAP[1]",
            "PUSHW[ ]", str(bottom), "SRP1[ ]", "PUSHW[ ]", str(top), "SRP2[ ]",
        ]
        for point in sorted(extrema - {bottom, top}):
            assembly.extend(["PUSHW[ ]", str(point), "IP[ ]"])
        program.fromAssembly(assembly + ["IUP[0]"])
        glyph.program = program
        font["maxp"].maxSizeOfInstructions = max(font["maxp"].maxSizeOfInstructions, len(program.getBytecode()))
        font["maxp"].maxStackElements = max(font["maxp"].maxStackElements, 2)
        count += 1
    return count


def ruby_trial(font) -> dict[str, str]:
    import build
    from spacing import ink

    cmap, gsub = font.getBestCmap(), font["GSUB"].table
    mapping = {}
    em = font["head"].unitsPerEm
    strength = round(em * (0.002 if font["OS/2"].usWeightClass >= 700 else 0.004))
    for char in RUBY_KANA:
        base = cmap[ord(char)]
        forms = {base}
        for tag in ("vert", "vrt2"):
            forms.update(build.single_mapping(gsub, tag, {base}).values())
        scale = 1.12 if char in SMALL_KANA else 1.0
        for source in sorted(forms):
            if source in mapping:
                continue
            outline = fraction_digits.transform(fraction_digits.contours(font, source), scale, scale)
            outline = fraction_digits.embolden(outline, strength, strength)
            a, b = ink(font, source), fraction_digits.bounds(outline)
            dx, dy = (a[0] + a[2] - b[0] - b[2]) / 2, (a[1] + a[3] - b[1] - b[3]) / 2
            # 右上に寄った縦組小書き仮名は、拡大した輪郭が枠から出る場合だけ内側へ戻す。
            low, high = -font["OS/2"].usWinDescent, font["OS/2"].usWinAscent
            dx = max(-b[0], min(dx, em - b[2]))
            dy = max(low - b[1], min(dy, high - b[3]))
            glyph = fraction_digits.make_glyph(fraction_digits.transform(outline, 1, 1, dx, dy))
            name = source + ".rubytrial"
            fraction_digits._add_glyph(font, name, glyph, font["hmtx"][source][0], font["vmtx"][source])
            # 輪郭の yMax を変えた分だけ上サイドベアリングを補正し、縦組の原点も保つ。
            original = font["glyf"][source]
            original.recalcBounds(font["glyf"])
            advance, side = font["vmtx"][source]
            font["vmtx"][name] = (advance, side + original.yMax - glyph.yMax)
            mapping[source] = name
    fraction_digits._new_feature(gsub, "ss03", latin_symbols.single(gsub, mapping))
    # 字形パネルで試作字形を選んだ場合や、vert を後の段階で適用する組版環境にも対応する。
    for tag in ("vert", "vrt2"):
        original_forms = build.single_mapping(gsub, tag, set(mapping))
        forms = {mapping[source]: mapping[target] for source, target in original_forms.items() if target in mapping}
        latin_symbols.append_feature_mapping(gsub, tag, forms)
    latin_symbols.sort_features(gsub)
    return mapping
