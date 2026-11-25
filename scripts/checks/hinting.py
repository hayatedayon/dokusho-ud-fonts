"""ヒンティング。FreeType でヒンティングを動かして描き、画素を元のフォントと比べる。"""

import tempfile
from contextlib import contextmanager
from pathlib import Path

from fontTools.ttLib import TTFont

import diagonal_hints
import freetype_render
import hinting as hinting_tools
import spec

from .charset import JAPANESE
from .common import FONTS, FontContext, SOURCES, check
from .fonttables import gsub_mapping, latin_codes, latin_symbol_mapping, latin_targets, outline


HINTING_PPEMS = range(8, 25)


def check_hinting(ctx: FontContext) -> None:
    """BIZ UDP から持ってきた字のヒンティングが BIZ UDP と同じで、和文のヒンティングが BIZ UD と
    同じこと。FreeType でヒンティングを動かして描き、画素を比べる (hinting.py が cvt の番号を
    ずらし損ねていれば、字の形がずれる)"""
    label = ctx.label
    family = ctx.family
    weight = ctx.weight
    font = ctx.font
    targets = latin_targets(ctx.udp, ctx.latin_glyphs)
    udp_font = ctx.udp
    ud_font = ctx.ud
    paths = {"ours": FONTS / label, "ud": SOURCES / f"{family['ud']}-{weight}.ttf",
             "udp": SOURCES / f"{family['udp']}-{weight}.ttf"}
    cmap, cmap_ud = font.getBestCmap(), ud_font.getBestCmap()
    unhinted_ud = {cmap_ud[code] for code in spec.UNHINTED if code in cmap_ud}
    symbols = latin_symbol_mapping(font, "latn", None)
    by_name = {name: code for code, name in cmap.items()}
    order_ud = set(ud_font.getGlyphOrder())
    ud_hwid = gsub_mapping(ud_font, "hwid")
    # 後段の ss02 用入力は追加グリフなので、元フォントにある入力からだけ控えの由来を引く。
    half_widths = {half: ud_hwid.get(key, key) for key, half in gsub_mapping(font, "hwid").items()
                   if half not in order_ud and key in order_ud}
    check(half_widths, f"{label}: no half widths for hwid to draw")
    # 斜線を書き直した字 (spec.DIAGONAL_GLYPHS) は、BIZ UD・BIZ UDP の命令に決まった末尾を足したもので、画素が元と違う。
    # 元と同じ画素の比較から外す代わりに、末尾を外した字 (元の命令だけ) を元と比べる。足した末尾が何を変えるかは
    # check_diagonal_hints が縛る (命令の形・横線のそろい・x が動かないこと・斜線の縦の幅)
    listed = diagonal_listed(ctx)
    stripped_dir = tempfile.TemporaryDirectory()
    paths["stripped"] = Path(stripped_dir.name) / label
    write_stripped(ctx, paths["stripped"], listed)
    order = font.getGlyphOrder()
    plain_gray = freetype_render.Renderer(paths["ours"], freetype_render.MODES[0][1], freetype_render.NO_HINTING)
    # 字全体が消えうるのは、インクの幅か高さが細い字だけ (漢字などは、線が 1 本消えても字は残る)
    glyf = font["glyf"]
    thin = [(name, index) for index, name in enumerate(font.getGlyphOrder()) if glyf[name].numberOfContours
            and min(glyf[name].xMax - glyf[name].xMin, glyf[name].yMax - glyf[name].yMin) <= font["head"].unitsPerEm // 8]
    has_ink_gray = [(name, index, ppem) for name, index in thin for ppem in HINTING_PPEMS
                    if any(plain_gray.render(index, ppem)[5])]
    plain_gray.close()
    for mode, interpreter, flags in freetype_render.MODES:
        renderers = {key: freetype_render.Renderer(path, interpreter, flags) for key, path in paths.items()}
        ours, ud, udp = renderers["ours"], renderers["ud"], renderers["udp"]
        stripped = renderers["stripped"]
        # (何を, 読書 UD のグリフの番号, 比べる相手, 相手のグリフの番号)
        # ヒンティングを付けない字 (spec.UNHINTED) は、元のフォントと同じには描かれない
        cases = [(f"U+{code:04X}", ours.char_index(code), udp, udp.char_index(code)) for code in latin_codes(cmap)
                 if code not in spec.UNHINTED]
        cases += [(f"U+{by_name[source]:04X} in Latin text", font.getGlyphID(target), udp, udp.char_index(by_name[source]))
                  for source, target in symbols.items() if by_name[source] not in spec.UNHINTED]
        # 欧字からの置き換え先と合字 (² ・斜線の 0・縦組で横に倒した欧字・ﬁ など)。グリフの番号は
        # BIZ UD と BIZ UDP で違うので、名前で引く
        cases += [(f"{target} ({tag})", font.getGlyphID(target), udp, udp_font.getGlyphID(target))
                  for target, tag in sorted(targets.items())]
        cases += [(char, ours.char_index(ord(char)), ud, ud.char_index(ord(char))) for char in JAPANESE]
        # hwid の置き換え先として残した、BIZ UD の半角の字 (足した字。post は形式 3 で、名前は番号から
        # 付くので、hwid の置き換えから BIZ UD の字を引く。欧字 A からの置き換えなら、BIZ UD の A)
        cases += [(f"{name} (hwid of {source})", font.getGlyphID(name), ud, ud_font.getGlyphID(source))
                  for name, source in sorted(half_widths.items()) if source not in unhinted_ud]
        differ = []
        for what, ours_index, other, other_index in cases:
            mine = stripped if order[ours_index] in listed else ours
            for ppem in HINTING_PPEMS:
                if mine.render(ours_index, ppem) != other.render(other_index, ppem):
                    differ.append(f"{what} at {ppem} ppem")
        check(not differ, f"{label}: {mode}: {len(differ)} glyphs are not drawn as in BIZ UD / BIZ UDP, "
                          f"such as {differ[:3]}")
        for renderer in renderers.values():
            renderer.close()
        check_nothing_vanishes(label, font, mode, interpreter, flags, symbols, by_name, targets, half_widths,
                               unhinted_ud, has_ink_gray)
    stripped_dir.cleanup()
    # 細い横線だけの字 (spec.UNHINTED) は、文字が指す字・欧文の中の置き換え先・hwid の半角の字・2 倍と 3 倍の
    # ダッシュのどれもヒンティングを持たないこと
    for code in [*spec.UNHINTED, 0x2E3A, 0x2E3B]:
        names = [cmap[code]] if code in cmap else []
        names += [target for source, target in symbols.items() if by_name[source] == code]
        names += [half for half, source in half_widths.items() if source == cmap_ud.get(code)]
        for name in names:
            program = getattr(font["glyf"][name], "program", None)
            check(program is None or not program.getBytecode(), f"{label}: U+{code:04X} ({name}) still has hinting")


def check_nothing_vanishes(label: str, font: TTFont, mode: str, interpreter: int, flags: int,
                           symbols: dict, by_name: dict, targets: dict[str, str], half_widths: dict,
                           unhinted_ud: set[str], has_ink_gray: list) -> None:
    """ヒンティングを動かすと何も描かれなくなる字が無いこと (動かさなければ描ける字)。グレースケールでは
    フォントの全てのグリフを、モノクロでは欧字・記号・細い横線の字を確かめる"""
    hinted = freetype_render.Renderer(FONTS / label, interpreter, flags)
    if not flags:
        gone = [f"{name} at {ppem} ppem" for name, index, ppem in has_ink_gray
                if not any(hinted.render(index, ppem)[5])]
    else:
        plain = freetype_render.Renderer(FONTS / label, interpreter, flags | freetype_render.NO_HINTING)
        cmap = font.getBestCmap()
        glyphs = [(f"U+{code:04X}", hinted.char_index(code))
                  for code in sorted({*latin_codes(cmap), *(c for c in spec.UNHINTED if c in cmap), 0x2E3A, 0x2E3B})]
        glyphs += [(f"U+{by_name[source]:04X} in Latin text", font.getGlyphID(target))
                   for source, target in symbols.items()]
        glyphs += [(f"{target} ({tag})", font.getGlyphID(target)) for target, tag in sorted(targets.items())]
        glyphs += [(f"{half} (hwid)", font.getGlyphID(half))
                   for half, source in sorted(half_widths.items()) if source in unhinted_ud]
        gone = [f"{what} at {ppem} ppem" for what, index in glyphs for ppem in HINTING_PPEMS
                if not any(hinted.render(index, ppem)[5]) and any(plain.render(index, ppem)[5])]
        plain.close()
    check(not gone, f"{label}: {mode}: hinting erases {len(gone)} glyphs, such as {gone[:3]}")
    hinted.close()


def check_generated_mark_hints(ctx: FontContext) -> None:
    """作った約物のヒントが効いていて、8–24 ppem の全描画モードで消えず、〝 〟 と高さがそろうこと。"""
    label = ctx.label
    path = ctx.path
    font = ctx.font
    shaper = ctx.shaper
    cmap, order = font.getBestCmap(), font.getGlyphOrder()
    vertical = lambda char, script: shaper.shape(char, "ja", True, (), script)[0][0]
    names = [(cmap[0x301E], cmap[0x301D])]
    for char, source, script in (("‘", "〝", "Hani"), ("’", "〟", "Hani"), ("‘", "〝", "Latn"), ("’", "〟", "Latn")):
        names.append((order[vertical(char, script)], order[vertical(source, "Hani")] if script == "Hani" else None))
    for name, reference in names:
        check(len(font["glyf"][name].program.getBytecode()) > 0, f"{label}: {name} has no hinting")
    for mode, interpreter, flags in freetype_render.MODES:
        renderer = freetype_render.Renderer(path, interpreter, flags)
        for ppem in range(8, 25):
            for name, reference in names:
                index = font.getGlyphID(name)
                bitmap = renderer.render(index, ppem)
                check(bitmap[4] >= 1 and any(bitmap[5]), f"{label}: {name} vanishes at {ppem} ppem ({mode})")
                if reference is not None:
                    ys = [y for _x, y in renderer.outline(index, ppem)]
                    reference_ys = [y for _x, y in renderer.outline(font.getGlyphID(reference), ppem)]
                    check(abs(min(ys) - min(reference_ys)) <= 64 and abs(max(ys) - max(reference_ys)) <= 64,
                          f"{label}: {name} is more than 1 px off {reference} at {ppem} ppem ({mode})")
        renderer.close()


def check_ruby_hint_rendering(ctx: FontContext) -> None:
    """ss03 の試作字形のヒントが、FreeType の全描画モードで効いていて、形を崩さないこと。

    6・7 ppem は prep が命令を止めるので、グレースケールではヒントなしと同じ画素。8–24 ppem は、点が縦にだけ 1 px 以内で動き
    (横は動かない)、消えず、濃さがヒントなしから大きく変わらず、横線の端が画素の境目にそろう (通常の仮名と同じくらい)。
    """
    label = ctx.label
    font = ctx.font
    trial = gsub_mapping(font, "ss03")
    pairs = [(font.getGlyphID(source), font.getGlyphID(target)) for source, target in trial.items()]
    for mode, interpreter, flags in freetype_render.MODES:
        hinted = freetype_render.Renderer(ctx.path, interpreter, flags)
        plain = freetype_render.Renderer(ctx.path, interpreter, flags | freetype_render.NO_HINTING)
        for ppem in range(6, 25):
            aligned = {"source": 0, "trial": 0, "plain": 0}
            ink = [0, 0]
            for source, target in pairs:
                shown, unhinted = hinted.render(target, ppem), plain.render(target, ppem)
                if ppem < 8:
                    # モノクロでは、命令の無い字も NO_HINTING と同じにならない (通常の仮名も同じ) ので比べない
                    check(flags or shown == unhinted, f"{label}: {mode}: trial ruby {target} is hinted at {ppem} ppem")
                    continue
                check(any(shown[5]), f"{label}: {mode}: trial ruby {target} vanishes at {ppem} ppem")
                fitted, original = hinted.outline(target, ppem), plain.outline(target, ppem)
                check(all(a[0] == b[0] and abs(a[1] - b[1]) <= 64 for a, b in zip(fitted, original)),
                      f"{label}: {mode}: trial ruby {target} is distorted at {ppem} ppem")
                for key, renderer, index in (("source", hinted, source), ("trial", hinted, target), ("plain", plain, target)):
                    ys = [y for _x, y in renderer.outline(index, ppem)]
                    aligned[key] += sum(1 for y in set(ys) if ys.count(y) >= 3 and y % 64 == 0)
                if not flags:
                    ratio = sum(shown[5]) / max(1, sum(unhinted[5]))
                    # 約 1〜2 px の点 (・) は、原字のヒントが点を 1 px の整数倍に丸めるので、原字そのものが同じ量だけ動く。
                    # 原字と同じ動きなら (0.1 以内) 許す。
                    original_ratio = sum(hinted.render(source, ppem)[5]) / max(1, sum(plain.render(source, ppem)[5]))
                    check(0.75 <= ratio <= 1.4 or abs(ratio - original_ratio) <= 0.1,
                          f"{label}: {mode}: trial ruby {target} changes its ink by {ratio:.2f} at {ppem} ppem (original {original_ratio:.2f})")
                ink[0] += sum(shown[5]) if not flags else sum(bin(b).count("1") for b in shown[5])
                ink[1] += sum(unhinted[5]) if not flags else sum(bin(b).count("1") for b in unhinted[5])
            if ppem >= 8:
                check(0.9 <= ink[0] / ink[1] <= 1.1, f"{label}: {mode}: hinting changes the ink of the trial ruby by {ink[0] / ink[1]:.2f} at {ppem} ppem")
                check(aligned["trial"] >= 0.8 * aligned["source"] and aligned["trial"] >= 5 * max(1, aligned["plain"]),
                      f"{label}: {mode}: trial ruby lines are not on pixel boundaries at {ppem} ppem {aligned}")
        hinted.close()
        plain.close()


def diagonal_listed(ctx: FontContext) -> dict[str, str]:
    """この書体で斜線を書き直した字 (グリフ名 → 文字)"""
    return spec.DIAGONAL_GLYPHS.get((ctx.family["key"], ctx.weight), {})


@contextmanager
def stripped_font(ctx: FontContext):
    """斜線を書き直した字から末尾を外したフォントの path と、その字の一覧 (グリフ名 → 文字)"""
    listed = diagonal_listed(ctx)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / ctx.label
        write_stripped(ctx, path, listed)
        yield path, listed


def program_tokens(font: TTFont, name: str) -> list | None:
    glyph = font["glyf"][name]
    glyph.expand(font["glyf"])
    program = getattr(glyph, "program", None)
    if glyph.numberOfContours == 0 or glyph.isComposite() or program is None or not program.getBytecode():
        return None
    return diagonal_hints.tokens(program)


def write_stripped(ctx: FontContext, path: Path, listed: dict[str, str]) -> None:
    """斜線を書き直した字から、足した末尾を外した (元の命令だけの) フォントを path に書く。末尾が決まった形で
    なければ、check_diagonal_hints が報告するので、ここでは外さない"""
    font = TTFont(ctx.path)
    for name in listed:
        tokens = program_tokens(font, name)
        split = diagonal_hints.split_tail(tokens) if tokens is not None else None
        if split is not None:
            font["glyf"][name].program = diagonal_hints.assemble(split[0])
    font.save(path)
    font.close()


def _polylines(points: list, flags: list, ends: list) -> list[list[tuple[float, float]]]:
    """TrueType の 2 次曲線の輪郭を折れ線にする (曲線は 8 に分ける)。points は (x, y)、flags の下位 1 bit が曲線の上の点"""
    polygons, start = [], 0
    for end in ends:
        ring = [(points[i], bool(flags[i] & 1)) for i in range(start, end + 1)]
        start = end + 1
        # 曲線の外の点が続くところに、間の曲線の上の点を足す
        expanded = []
        for k, (point, on) in enumerate(ring):
            expanded.append((point, on))
            following = ring[(k + 1) % len(ring)]
            if not on and not following[1]:
                expanded.append((((point[0] + following[0][0]) / 2, (point[1] + following[0][1]) / 2), True))
        first = next((k for k, (_p, on) in enumerate(expanded) if on), None)
        if first is None:
            continue
        expanded = expanded[first:] + expanded[:first]
        polygon, k, count = [expanded[0][0]], 1, len(expanded)
        while k <= count:
            point, on = expanded[k % count]
            if on:
                polygon.append(point)
                k += 1
            else:
                p0, end_point = polygon[-1], expanded[(k + 1) % count][0]
                for step in range(1, 9):
                    t = step / 8
                    polygon.append(((1 - t) ** 2 * p0[0] + 2 * t * (1 - t) * point[0] + t * t * end_point[0],
                                    (1 - t) ** 2 * p0[1] + 2 * t * (1 - t) * point[1] + t * t * end_point[1]))
                k += 2
        polygons.append(polygon)
    return polygons


def _vertical_thickness(polygons: list, x: float, y: float) -> float:
    """点 (x, y) を通る縦の線の上の、y に最も近いインクの区間の長さ (x の前後 1/32 px の平均)"""
    total = 0.0
    for dx in (-2, 2):
        crossings = []
        for polygon in polygons:
            for (x0, y0), (x1, y1) in zip(polygon, polygon[1:] + polygon[:1]):
                if (x0 <= x + dx < x1) or (x1 <= x + dx < x0):
                    crossings.append(y0 + (y1 - y0) * (x + dx - x0) / (x1 - x0))
        crossings.sort()
        best = None
        for a, b in zip(crossings[0::2], crossings[1::2]):
            distance = max(a - y, y - b, 0)
            if best is None or distance < best[0]:
                best = (distance, b - a)
        total += best[1] if best else 0
    return total / 2


def slash_loss(plain: list, hinted: list, flags: list, ends: list, points: list[int]) -> float:
    """斜線の縁の点 (points) の位置の、縦のインクの区間の長さが、ヒントなしからどれだけ縮んだか (px の平均。縮まなければ 0)。
    調査の斜線の濃さの点数 (骨格の点の濃さの差) の代わりに使う、輪郭だけから求める量"""
    before, after = _polylines(plain, flags, ends), _polylines(hinted, flags, ends)
    loss = [max(0.0, _vertical_thickness(before, plain[p][0], plain[p][1])
                - _vertical_thickness(after, plain[p][0], hinted[p][1])) / 64 for p in points]
    return sum(loss) / len(loss)


SLASH_PPEMS = range(9, 17)


def check_diagonal_hints(ctx: FontContext) -> None:
    """斜線を書き直した字 (spec.DIAGONAL_GLYPHS) を、画素の比較の代わりに縛る。

    - 命令が「元の BIZ UD・BIZ UDP の命令」+「決まった形の末尾」であること。末尾のある字は一覧にあるものだけ
    - 末尾を外した字は BIZ UD・BIZ UDP と同じ画素で描かれること (check_hinting が比べる。ここでは元の命令との一致)
    - x に動く点が 0 (ヒントなしと同じ x)、同じ高さの点が 3 つ以上の横線の組のうちそろう数が、末尾を外した字と同じ
      (8–24 ppem)、斜線の縁の縦の幅が、末尾を外した字より縮まないこと
    """
    label = ctx.label
    font = ctx.font
    listed = diagonal_listed(ctx)
    order = font.getGlyphOrder()
    ud_order, udp_order = set(ctx.ud.getGlyphOrder()), set(ctx.udp.getGlyphOrder())
    funcs = hinting_tools.functions(ctx.udp["fpgm"].program)
    offset = len(ctx.ud["cvt "].values)
    tails = {}
    plans = diagonal_hints.load_plans().get(f"{ctx.family['key']}-{ctx.weight}", {})
    for name in order:
        glyph = font["glyf"][name]
        if glyph.numberOfContours <= 0 or glyph.isComposite():
            continue
        tokens = program_tokens(font, name)
        split = diagonal_hints.split_tail(tokens) if tokens is not None else None
        if split is not None:
            tails[name] = split
    check(set(tails) == set(listed), f"{label}: the glyphs with a diagonal tail differ from spec.DIAGONAL_GLYPHS: "
                                     f"{sorted(set(tails) ^ set(listed))[:5]}")
    with tempfile.TemporaryDirectory() as directory:
        stripped_path = Path(directory) / label
        write_stripped(ctx, stripped_path, listed)
        for name in sorted(set(tails) & set(listed)):
            head, groups, after, method = tails[name]
            coordinates, ends, flags = outline(font, name)
            points = diagonal_hints.group_points(groups)
            references = diagonal_hints.reference_points(groups)
            plan = plans.get(name, {})
            check((groups, after, method) == (plan.get("groups"), plan.get("after", False), plan.get("method", "ip")),
                  f"{label}: {name}: the diagonal tail differs from its plan")
            check(all(0 <= p < len(coordinates) for p in points + references)
                  and len(set(points)) == len(points) and not set(references) & set(points)
                  and (method == "shp" or all(coordinates[lo][1] != coordinates[hi][1] for lo, hi, _g in groups)),
                  f"{label}: {name}: the points of the diagonal tail are not valid")
            # 元の命令と同じか (BIZ UD か BIZ UDP の同じ名前の字。名前の無い字 (読書 UD が作った字) は画素だけで比べる)
            origins = []
            if name in ud_order:
                origins.append(program_tokens(ctx.ud, name))
            if name in udp_order:
                program = getattr(ctx.udp["glyf"][name], "program", None)
                if program is not None and program.getBytecode():
                    try:
                        origins.append(diagonal_hints.tokens(hinting_tools.shift_cvt(program, funcs, offset, name, False)[0]))
                    except SystemExit:
                        pass
            check(not origins or head in origins, f"{label}: {name} ({listed[name]}): the program before the tail is not "
                                                  f"BIZ UD / BIZ UDP's")
        for mode, interpreter, flags_ in freetype_render.MODES:
            ours = freetype_render.Renderer(ctx.path, interpreter, flags_)
            stripped = freetype_render.Renderer(stripped_path, interpreter, flags_)
            plain = freetype_render.Renderer(ctx.path, interpreter, flags_ | freetype_render.NO_HINTING)
            for name in sorted(set(tails) & set(listed)):
                coordinates, ends, flags = outline(font, name)
                index = font.getGlyphID(name)
                by_height: dict[int, list[int]] = {}
                for i, (_x, y) in enumerate(coordinates):
                    by_height.setdefault(y, []).append(i)
                rows = [rows_ for rows_ in by_height.values() if len(rows_) >= 3]
                points = diagonal_hints.group_points(tails[name][1])
                moved, lines, loss_ours, loss_original = 0, 0, [], []
                for ppem in HINTING_PPEMS:
                    mine, original, unhinted = (r.outline(index, ppem) for r in (ours, stripped, plain))
                    moved += sum(1 for a, b in zip(mine, unhinted) if a[0] != b[0])
                    lines += abs(sum(1 for r in rows if all(mine[i][1] % 64 == 0 for i in r))
                                 - sum(1 for r in rows if all(original[i][1] % 64 == 0 for i in r)))
                    if ppem in SLASH_PPEMS:
                        loss_ours.append(slash_loss(unhinted, mine, flags, ends, points))
                        loss_original.append(slash_loss(unhinted, original, flags, ends, points))
                where = f"{label}: {mode}: {name} ({listed[name]})"
                check(moved == 0, f"{where}: the diagonal tail moves {moved} points in x")
                check(lines == 0, f"{where}: the diagonal tail changes the number of aligned horizontal lines")
                check(sum(loss_ours) <= sum(loss_original) + 0.02 * len(loss_ours),
                      f"{where}: the diagonal tail thins the slash ({sum(loss_ours) / len(loss_ours):.3f} px, "
                      f"before the tail {sum(loss_original) / len(loss_original):.3f} px)")
            for renderer in (ours, stripped, plain):
                renderer.close()
