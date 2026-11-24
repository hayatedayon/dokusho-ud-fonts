"""小さい字の調整。追加数字には縦方向だけのヒント、試作ルビ仮名には任意の ss03 を用意する。

ルビ仮名は全角の枠を保ち、原字のインクの中心を基準に細い線をわずかに補強する。小書き仮名の拡大率は
SMALL_SCALE (今は 1.0 = 拡大しない。1.12 にすると小書き仮名だけ 12% 大きくする)。全仮名 194 字を機械的に調整する試作。通常の ruby と
本文の字形は変えない。横組・縦組の字形を別々に作り、原字と同じ送りを使う。ヒントは原字の命令をそのまま付ける。
"""

from fontTools.ttLib.tables.ttProgram import Program

import fraction_digits
import latin_symbols

# U+30FB「・」も docs/RUBY.md の対象表に含む (範囲だけなら 193 字)。
RUBY_KANA = "".join(chr(c) for start, stop in ((0x3041, 0x3097), (0x30A0, 0x30FC), (0x31F0, 0x3200))
                    for c in range(start, stop))
SMALL_KANA = "ぁぃぅぇぉっゃゅょゎゕゖァィゥェォッャュョヮヵヶ" + "".join(map(chr, range(0x31F0, 0x3200)))
# 小書き仮名の拡大率。1.0 は拡大せず、補強と中心合わせだけを行う。1.12 は従来の ss03。
SMALL_SCALE = 1.0
RUBY_HINT_OPS = {"NPUSHB", "NPUSHW", "PUSHB", "PUSHW", "SVTCA", "MDAP", "SRP1", "SRP2", "IP", "SHP", "IUP"}


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


def hint_marks(font, names) -> int:
    """命令の無い約物の字に、縦方向だけのヒントを付ける。字の上下をグリッドに合わせ、各輪郭の極点を間で補間する。"""
    count = 0
    for name in names:
        glyph = font["glyf"][name]
        if glyph.isComposite() or glyph.numberOfContours <= 0 or len(glyph.program.getBytecode()):
            raise SystemExit(f"{name}: expected a simple glyph without instructions")
        coords = glyph.coordinates
        bottom = min(range(len(coords)), key=lambda i: coords[i][1])
        top = max(range(len(coords)), key=lambda i: coords[i][1])
        extrema, start = set(), 0
        for end in glyph.endPtsOfContours:
            points = range(start, end + 1)
            extrema.update((min(points, key=lambda i: coords[i][1]), max(points, key=lambda i: coords[i][1])))
            start = end + 1
        assembly = ["PUSHB[ ]", "1", "SZPS[ ]", "SVTCA[0]", "RTG[ ]",
                    "PUSHW[ ]", str(bottom), "MDAP[1]", "PUSHW[ ]", str(top), "MDAP[1]",
                    "PUSHW[ ]", str(bottom), "SRP1[ ]", "PUSHW[ ]", str(top), "SRP2[ ]"]
        for point in sorted(extrema - {bottom, top}):
            assembly.extend(["PUSHW[ ]", str(point), "IP[ ]"])
        program = Program()
        program.fromAssembly(assembly + ["IUP[0]"])
        glyph.program = program
        font["maxp"].maxSizeOfInstructions = max(font["maxp"].maxSizeOfInstructions, len(program.getBytecode()))
        font["maxp"].maxStackElements = max(font["maxp"].maxStackElements, 2)
        count += 1
    return count


def trial_glyph(font, source: str, scale: float, ex: float, ey: float):
    """試作ルビ仮名の輪郭。原字を scale 倍し、横に ex・縦に ey だけ太らせ、インクの中心を原字に合わせる。

    ruby_trial が配るフォントのために使い、見本 (scripts/ruby_proof.py) も補強量を変えて同じ処理を使う。
    """
    from spacing import ink

    em = font["head"].unitsPerEm
    outline = fraction_digits.transform(fraction_digits.contours(font, source), scale, scale)
    outline = fraction_digits.embolden(outline, ex, ey)
    a, b = ink(font, source), fraction_digits.bounds(outline)
    dx, dy = (a[0] + a[2] - b[0] - b[2]) / 2, (a[1] + a[3] - b[1] - b[3]) / 2
    # 右上に寄った縦組小書き仮名は、拡大 (scale > 1) や補強で輪郭が枠から出る場合だけ内側へ戻す。
    # 拡大しない (scale == 1) 今も、補強で枠に触れうるので、条件として残す。
    low, high = -font["OS/2"].usWinDescent, font["OS/2"].usWinAscent
    dx = max(-b[0], min(dx, em - b[2]))
    dy = max(low - b[1], min(dy, high - b[3]))
    return fraction_digits.make_glyph(fraction_digits.transform(outline, 1, 1, dx, dy))


def trial_strength(font) -> int:
    """試作ルビ仮名の補強量 (フォント単位)。Regular は em の 0.4%、Bold は 0.2%。"""
    return round(font["head"].unitsPerEm * (0.002 if font["OS/2"].usWeightClass >= 700 else 0.004))


def trial_sources(font, small_scale: float | None = None) -> dict[str, float]:
    """試作字形の元になる字 (横組と縦組の字形) と、その拡大率。小書き仮名の拡大率は SMALL_SCALE (指定すれば small_scale)。"""
    small_scale = SMALL_SCALE if small_scale is None else small_scale
    import build

    cmap, gsub = font.getBestCmap(), font["GSUB"].table
    sources = {}
    for char in RUBY_KANA:
        base = cmap[ord(char)]
        forms = {base}
        for tag in ("vert", "vrt2"):
            forms.update(build.single_mapping(gsub, tag, {base}).values())
        for source in sorted(forms):
            sources.setdefault(source, small_scale if char in SMALL_KANA else 1.0)
    return sources


def trial_hint_issues(font, source: str, name: str, scale: float) -> list[str]:
    """原字の点番号を安全に流用できる条件を検査する。満たさないときは理由を返す。"""
    original, trial = font["glyf"][source], font["glyf"][name]
    if original.isComposite() or trial.isComposite() or original.numberOfContours <= 0:
        return ["not a simple outline"]
    if (original.numberOfContours != trial.numberOfContours
            or list(original.endPtsOfContours) != list(trial.endPtsOfContours)
            or len(original.coordinates) != len(trial.coordinates)
            or [f & 1 for f in original.flags] != [f & 1 for f in trial.flags]):
        return ["contour structure differs"]
    assembly = original.program.getAssembly()
    instructions = [line.split()[0] for line in assembly if line and not line.lstrip("-").isdigit()]
    ops = {line.split("[")[0] for line in instructions}
    issues = []
    if not instructions:
        issues.append("source has no instructions")
    # IUP[1] も原字にあるが、x の点を touch する命令がないので動かない。
    if ops - RUBY_HINT_OPS or "SVTCA[0]" not in instructions or "SVTCA[1]" in instructions:
        issues.append("instructions are not point-relative y-only operations")
    # 距離だけでは、鋭い角の補強を拒否する一方、近い点の入れ替えを許しうる。
    # 同じ原字から変換を再計算し、丸めた後の座標を番号ごとに完全一致で照合する。
    # transform/embolden/make_glyph は点を増減・並べ替えせず、各点を同じ順に出す。
    strength = trial_strength(font)
    expected = trial_glyph(font, source, scale, strength, strength)
    if list(trial.coordinates) != list(expected.coordinates):
        issues.append("point correspondence differs from the transformed source")
    return issues


def hint_trial(font, source: str, name: str, scale: float) -> bool:
    """試作字形 name に、原字 source の命令をそのまま付ける。付けたら True。

    原字の命令は y 方向だけで、点の番号を指す MDAP・SHP・IP・SRP・IUP だけでできており、cvt も関数も使わない
    (docs/RUBY.md)。試作字形は原字の輪郭を拡大・補強・平行移動したもので、輪郭の数・終点・点の数と順序・
    on/off が同じなので、同じ命令が点に当たる。構成が違う字には付けない (ヒントなしのまま)。
    """
    glyf = font["glyf"]
    original, trial = glyf[source], glyf[name]
    if trial_hint_issues(font, source, name, scale):
        return False
    bytecode = original.program.getBytecode()
    if not bytecode:
        return False
    program = Program()
    program.fromBytecode(bytecode)
    trial.program = program
    return True


def ruby_trial(font) -> dict[str, str]:
    import build

    gsub = font["GSUB"].table
    mapping = {}
    strength = trial_strength(font)
    for source, scale in trial_sources(font).items():
            glyph = trial_glyph(font, source, scale, strength, strength)
            name = source + ".rubytrial"
            fraction_digits._add_glyph(font, name, glyph, font["hmtx"][source][0], font["vmtx"][source])
            # 輪郭の yMax を変えた分だけ上サイドベアリングを補正し、縦組の原点も保つ。
            original = font["glyf"][source]
            original.recalcBounds(font["glyf"])
            advance, side = font["vmtx"][source]
            font["vmtx"][name] = (advance, side + original.yMax - glyph.yMax)
            mapping[source] = name
            hint_trial(font, source, name, scale)
    fraction_digits._new_feature(gsub, "ss03", latin_symbols.single(gsub, mapping))
    # 字形パネルで試作字形を選んだ場合や、vert を後の段階で適用する組版環境にも対応する。
    for tag in ("vert", "vrt2"):
        original_forms = build.single_mapping(gsub, tag, set(mapping))
        forms = {mapping[source]: mapping[target] for source, target in original_forms.items() if target in mapping}
        latin_symbols.append_feature_mapping(gsub, tag, forms)
    latin_symbols.sort_features(gsub)
    return mapping
