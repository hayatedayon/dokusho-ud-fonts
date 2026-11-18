"""小さい字: ルビ用の仮名 (ss03) と小さい数字のヒント。"""

from pathlib import Path
import unicodedata

from fontTools.ttLib import TTFont

import freetype_render
import small_type
import spec

from .common import FontContext, SOURCES, check
from .fonttables import gpos_values, gsub_mapping, gsub_alternates, outputs
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
    excluded = "漢字ーゝゞヽヾゟヿ゛゜\u3099\u309a"
    for vertical in (False, True):
        check(run(excluded, ("ss03",), vertical) == run(excluded, (), vertical), f"{label}: ss03 changes unselected characters")
    trial = gsub_mapping(font, "ss03")
    codes = {*range(0x3041, 0x3097), *range(0x30A0, 0x30FC), *range(0x31F0, 0x3200)}
    check(set(map(ord, small_type.RUBY_KANA)) == codes and len(small_type.RUBY_KANA) == 194,
          f"{label}: ss03 must cover exactly the documented 194 kana")
    check(set(trial) == set(small_type.trial_sources(font)) and len(trial) == 235,
          f"{label}: ss03 must have 194 horizontal and 41 vertical forms")
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


# 試作字形が持つ命令。原字のヒントは、点の番号を指す y 方向の命令だけ (cvt・関数・IF を使わない)
RUBY_HINT_OPS = {"NPUSHB", "NPUSHW", "PUSHB", "PUSHW", "SVTCA", "MDAP", "SRP1", "SRP2", "IP", "SHP", "IUP"}


def check_ruby_hint_programs(ctx: FontContext) -> None:
    """ss03 の試作字形 (横組・縦組の 235 グリフ) の命令と、原字 (BIZ UD) との点の対応を確かめる。

    命令は点の番号だけを指すので、原字と輪郭の構成 (輪郭の数・終点・点の数と順序・on/off) が同じで、
    点が原字の点を拡大・補強・平行移動した位置にあることを確かめる。ヒントを付けない字を作らないよう、
    条件を満たさない字には命令がないことも確かめる。
    """
    label = ctx.label
    font = ctx.font
    ud = ctx.ud
    glyf, ud_glyf = font["glyf"], ud["glyf"]
    trial = gsub_mapping(font, "ss03")
    check(len(trial) == 235, f"{label}: expected 235 trial ruby glyphs, found {len(trial)}")
    strength = small_type.trial_strength(font)
    hinted_count = 0
    scales = small_type.trial_sources(font)
    for source, target in trial.items():
        gid = font.getGlyphID(source)
        original, shipped, plain = glyf[source], glyf[target], ud_glyf[ud.getGlyphOrder()[gid]]
        bytecode = shipped.program.getBytecode()
        issues = small_type.trial_hint_issues(font, source, target, scales[source])
        if issues:
            check(not bytecode, f"{label}: unsafe instructions on {target}: {issues}")
            continue
        hinted_count += bool(bytecode)
        check(len(bytecode) > 0, f"{label}: trial ruby {target} (of {source}) has no hinting")
        check(bytecode == plain.program.getBytecode() == original.program.getBytecode(),
              f"{label}: trial ruby {target} does not have the instructions of {source} in BIZ UD")
        ops = {line.split("[")[0].split()[0] for line in shipped.program.getAssembly() if not line[0].isdigit() and line[0] != "-"}
        check(ops <= RUBY_HINT_OPS and "SVTCA" in ops, f"{label}: trial ruby {target} uses unexpected instructions {sorted(ops - RUBY_HINT_OPS)}")
        instructions = shipped.program.getAssembly()
        instructions = [line.split()[0] for line in instructions]
        check("SVTCA[0]" in instructions and "SVTCA[1]" not in instructions,
              f"{label}: trial ruby {target} changes the x direction")
        check(shipped.numberOfContours == original.numberOfContours and list(shipped.endPtsOfContours) == list(original.endPtsOfContours)
              and [f & 1 for f in shipped.flags] == [f & 1 for f in original.flags],
              f"{label}: trial ruby {target} has a different contour structure from {source}")
        # 独立した上限: embolden は d=1+cosθ>1/16 の角を動かす。
        # 法線和の長さは sqrt(2d) なので、補強による偏位は strength/2*sqrt(2/d)
        # < sqrt(8)*strength。重心を引くと2倍以下、整数丸めの残差は1以下。
        # この粗い上限だけで点番号の一致を認めず、上の再計算による完全一致も必須とする。
        scale = scales[source]
        o, t = original.coordinates, shipped.coordinates
        mo = [sum(c[i] for c in o) / len(o) for i in (0, 1)]
        mt = [sum(c[i] for c in t) / len(t) for i in (0, 1)]
        worst = max(abs((t[k][i] - mt[i]) - scale * (o[k][i] - mo[i])) for k in range(len(o)) for i in (0, 1))
        check(worst <= (32 ** 0.5) * strength + 1,
              f"{label}: trial ruby {target} exceeds the emboldening bound ({worst:.1f} units)")
    check(hinted_count == 235, f"{label}: expected 235 hinted trial ruby glyphs, found {hinted_count}")


def check_ruby_combinations(ctx: FontContext) -> None:
    """ss03 が、仮名の濁音・半濁点の分解形、結合濁点・半濁点、か゚ などの合字と組み合わさっても動きが変わらないこと。

    調べた範囲は HarfBuzz の横組・縦組。aalt・hwid・fwid の順序と候補も検査する。
    """
    label = ctx.label
    run = ctx.run
    trial_mapping = gsub_mapping(ctx.font, "ss03")
    ligature_kana = "かきくけこカキクケコセツトㇷ"
    for vertical in (False, True):
        where = "vertical" if vertical else "horizontal"
        # 濁音・半濁音は、分解した形 (か + U+3099) でも、ccmp で合成してから ss03 の字形になる
        for composed in small_type.RUBY_KANA:
            decomposed = unicodedata.normalize("NFD", composed)
            if composed == decomposed:
                continue
            plain, trial = run(decomposed, (), vertical), run(decomposed, ("ss03",), vertical)
            check(trial == run(composed, ("ss03",), vertical), f"{label}: ss03 of decomposed {composed} differs ({where})")
            check(len(trial) == 1 and trial[0][0] != plain[0][0], f"{label}: ss03 is lost on decomposed {composed} ({where})")
        # 194 字 + 結合濁点・半濁点。ccmp の合字になる組は次で別に検査する
        for char in small_type.RUBY_KANA:
            for mark in ("\u3099", "\u309a"):
                text = char + mark
                if unicodedata.normalize("NFC", text) != text:
                    continue
                if mark == "\u309a" and char in ligature_kana:
                    continue
                plain, trial = run(text, (), vertical), run(text, ("ss03",), vertical)
                check(len(plain) == len(trial) == 2 and trial[0][0] != plain[0][0] and trial[1:] == plain[1:]
                      and trial[0][2:] == plain[0][2:], f"{label}: ss03 changes the mark or advance of {text!r} ({where})")
        # か゚ などの合字自体は対象外。構成する仮名には ss03 があっても合字は変わらない
        for char in ligature_kana:
            text = char + "\u309a"
            check(run(text, ("ss03",), vertical) == run(text, (), vertical), f"{label}: ss03 changes the ligature {text!r} ({where})")
        mixed_plain, mixed_trial = run("か\u309aが", (), vertical), run("か\u309aが", ("ss03",), vertical)
        check(mixed_trial[:-1] == mixed_plain[:-1] and mixed_trial[-1][0] != mixed_plain[-1][0],
              f"{label}: ss03 misses the kana after か゚ ({where})")
        for tag in ("aalt", "hwid", "fwid"):
            for char in small_type.RUBY_KANA:
                plain = run(char, (tag,), vertical)
                expected = [(ctx.font.getGlyphID(trial_mapping.get(ctx.order[r[0]], ctx.order[r[0]])), *r[1:]) for r in plain]
                check(run(char, (tag, "ss03"), vertical) == expected,
                      f"{label}: ss03 changes the order/advance of {tag} for {char} ({where})")
    alternates, original_alternates = gsub_alternates(ctx.font, "aalt"), gsub_alternates(ctx.ud, "aalt")
    for char in small_type.RUBY_KANA:
        name = ctx.cmap[ord(char)]
        check(alternates.get(name, []) == original_alternates.get(name, []), f"{label}: ss03 changes aalt candidates of {char}")
    check(not set(trial_mapping.values()) & {g for values in alternates.values() for g in values},
          f"{label}: aalt offers trial ruby glyphs")


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
