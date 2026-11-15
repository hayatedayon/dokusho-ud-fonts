"""約物の詰め (halt・vhal・palt・vpal・chws・vchw) と字送り。"""

from fontTools.pens.boundsPen import BoundsPen

import spec

from .common import FontContext, Report, check, problems
from .fonttables import gpos_values, gsub_mapping, semi_voiced_kana_ligatures
from .geometry import glyph_bounds
from .vertical import VERTICAL_PROPORTIONAL_CODES


def check_spacing(ctx: FontContext) -> None:
    """約物の詰め (halt・vhal)。詰めた後もインクが字の枠に収まり、代表の字が JLReq の値であること"""
    label = ctx.label
    font = ctx.font
    if "GPOS" not in font:
        problems.append(f"{label}: no GPOS (halt and vhal are missing)")
        return
    em, half, quarter = font["head"].unitsPerEm, font["head"].unitsPerEm // 2, font["head"].unitsPerEm // 4
    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap()
    vertical_forms = gsub_mapping(font, "vert")
    halt, vhal = gpos_values(font, "halt"), gpos_values(font, "vhal")
    for glyph, (x, y, x_advance, y_advance) in halt.items():
        pen = BoundsPen(glyph_set)
        glyph_set[glyph].draw(pen)
        left, right = pen.bounds[0] + x, pen.bounds[2] + x
        width = font["hmtx"][glyph][0] + x_advance
        check(0 <= left and right <= width, f"{label}: halt of {glyph} puts its ink outside its width")
    for glyph, (x, y, x_advance, y_advance) in vhal.items():
        pen = BoundsPen(glyph_set)
        glyph_set[glyph].draw(pen)
        advance, top_side = font["vmtx"][glyph]
        top = top_side - y  # 上へ動かすと、枠の上からの位置は小さくなる
        bottom = top + (pen.bounds[3] - pen.bounds[1])
        check(0 <= top and bottom <= advance + y_advance, f"{label}: vhal of {glyph} puts its ink outside its advance")
    expected = {
        "「": ((-half, 0, -half, 0), (0, half, 0, -half)),
        "」": ((0, 0, -half, 0), (0, 0, 0, -half)),
        "。": ((0, 0, -half, 0), (0, 0, 0, -half)),
        "、": ((0, 0, -half, 0), (0, 0, 0, -half)),
        "・": ((-quarter, 0, -half, 0), (0, quarter, 0, -half)),
    }
    for char, (horizontal, vertical) in expected.items():
        glyph = cmap[ord(char)]
        check(halt.get(glyph) == horizontal, f"{label}: halt of {char} is {halt.get(glyph)}, not {horizontal}")
        upright = vertical_forms.get(glyph, glyph)
        check(vhal.get(upright) == vertical, f"{label}: vhal of {char} is {vhal.get(upright)}, not {vertical}")
    scripts = {r.ScriptTag for r in font["GPOS"].table.ScriptList.ScriptRecord}
    check({"hani", "kana", "DFLT"} <= scripts, f"{label}: GPOS scripts {sorted(scripts)}")


def check_proportional(ctx: FontContext) -> None:
    """palt で、仮名・約物・全角の字 (ccmp の半濁点の合字も) が BIZ UDP と同じ位置と字幅になること
    (インクの中心が 1 単位まで)。BIZ UDP と字幅が違い、インクの外形が 20 単位まで同じ字は、どれも palt を持つこと"""
    label = ctx.label
    font = ctx.font
    udp = ctx.udp
    palt = gpos_values(font, "palt")
    cmap, cmap_udp = font.getBestCmap(), udp.getBestCmap()
    kana_ligs = semi_voiced_kana_ligatures(font, udp)
    check(len(kana_ligs) >= 14, f"{label}: expected at least 14 semi-voiced kana ligatures, found {len(kana_ligs)}")
    candidates = [(chr(code), cmap.get(code), cmap_udp.get(code))
                  for code in [*range(0x3000, 0x3100), *range(0x31F0, 0x3200), *range(0xFF01, 0xFF61)]] + kana_ligs
    wrong, missing = [], []
    for item, name, other in candidates:
        if name is None or other is None or font["glyf"][name].numberOfContours == 0:
            continue
        if font["hmtx"][name] == udp["hmtx"][other] and name not in palt:
            continue
        a, b = glyph_bounds(font, name), glyph_bounds(udp, other)
        alike = (abs((a[2] - a[0]) - (b[2] - b[0])) <= 20 and abs(a[1] - b[1]) <= 20 and abs(a[3] - b[3]) <= 20)
        if name not in palt:
            if alike and (font["hmtx"][name][0] != udp["hmtx"][other][0]
                          or abs((a[0] + a[2]) / 2 - (b[0] + b[2]) / 2) > 1):
                missing.append(item)
            continue
        x, y, x_advance, y_advance = palt[name]
        center = (a[0] + a[2]) / 2 + x - (b[0] + b[2]) / 2
        if y or y_advance or abs(center) > 1 or font["hmtx"][name][0] + x_advance != udp["hmtx"][other][0]:
            wrong.append(item)
    check(len(palt) > 200, f"{label}: palt has only {len(palt)} glyphs")
    check(not wrong, f"{label}: palt does not set {len(wrong)} characters as BIZ UDP, such as {wrong[:5]}")
    check(not missing, f"{label}: {len(missing)} characters lack palt, such as {missing[:5]}")
    for char in "漢字読書":
        check(cmap[ord(char)] not in palt, f"{label}: {char} has palt")


def check_shaped_proportional(ctx: FontContext) -> None:
    """vpal・palt をかけた仮名・約物・全角の字が BIZ UDP と同じ位置・字送りになること。"""
    font = ctx.font
    font_udp = ctx.udp
    ours = ctx.ours
    udp = ctx.udp_shaped
    cmap = ctx.cmap
    cmap_udp = ctx.cmap_udp
    marks = ctx.marks
    ignorable = ctx.ignorable
    report = Report(ctx.label)
    # 縦組の vpal と横組の palt: 仮名・約物・全角の字 (ccmp の半濁点の合字も) のインクの中心と字送り
    forms, forms_udp = gsub_mapping(font, "vert"), gsub_mapping(font_udp, "vert")
    prefix = len("あ".encode())
    vpal_items = [(f"U+{code:04X}", chr(code), forms.get(cmap[code], cmap[code]),
                   forms_udp.get(cmap_udp[code], cmap_udp[code]))
                  for code in VERTICAL_PROPORTIONAL_CODES
                  if code in cmap and code in cmap_udp and code not in marks and code not in ignorable]
    vpal_items += [(item, item, forms.get(name, name), forms_udp.get(other, other))
                   for item, name, other in semi_voiced_kana_ligatures(font, font_udp)]
    for tag_label, seq, up_a, up_b in vpal_items:
        a_box, b_box = glyph_bounds(font, up_a), glyph_bounds(font_udp, up_b)
        if a_box is None or b_box is None:
            continue
        if abs((a_box[3] - a_box[1]) - (b_box[3] - b_box[1])) > spec.VERTICAL_SAME_INK \
                or abs((a_box[2] - a_box[0]) - (b_box[2] - b_box[0])) > spec.VERTICAL_SAME_INK:
            continue
        text = f"あ{seq}あ"
        end = prefix + len(seq.encode())
        shaped_a = [x for x in ours.shaper.shape(text, "ja", True, ("vpal",)) if prefix <= x[1] < end]
        shaped_b = [x for x in udp.shaper.shape(text, "ja", True) if prefix <= x[1] < end]
        if len(shaped_a) != 1 or len(shaped_b) != 1:
            report("with vpal is not a single glyph in vertical text", tag_label)
            continue
        (ga, _ca, xa_a, ya_a, xo_a, yo_a), (gb, _cb, xa_b, ya_b, xo_b, yo_b) = shaped_a[0], shaped_b[0]
        ba, bb = glyph_bounds(font, ours.order[ga]), glyph_bounds(font_udp, udp.order[gb])
        cy = abs((ba[1] + ba[3]) / 2 + yo_a - ((bb[1] + bb[3]) / 2 + yo_b))
        if (xa_a, ya_a, xo_a) != (xa_b, ya_b, xo_b) or cy > 1:
            report("with vpal in vertical text is not placed as in BIZ UDP", tag_label)
    for item, _name, _other in semi_voiced_kana_ligatures(font, font_udp):
        text = f"あ{item}あ"
        end = prefix + len(item.encode())
        shaped_a = [x for x in ours.shaper.shape(text, "ja", False, ("palt",)) if prefix <= x[1] < end]
        shaped_b = [x for x in udp.shaper.shape(text, "ja", False) if prefix <= x[1] < end]
        if len(shaped_a) != 1 or len(shaped_b) != 1:
            report("semi-voiced kana ligature is not a single glyph", item)
            continue
        (ga, _ca, xa_a, ya_a, xo_a, yo_a), (gb, _cb, xa_b, ya_b, xo_b, yo_b) = shaped_a[0], shaped_b[0]
        ba, bb = glyph_bounds(font, ours.order[ga]), glyph_bounds(font_udp, udp.order[gb])
        cx = abs((ba[0] + ba[2]) / 2 + xo_a - ((bb[0] + bb[2]) / 2 + xo_b))
        if (xa_a, ya_a, yo_a) != (xa_b, ya_b, yo_b) or cx > 1:
            report("with palt in horizontal text is not placed as in BIZ UDP", item)
    report.flush()


def check_contextual_spacing(ctx: FontContext) -> None:
    """chws・vchw: 続いた約物だけが詰まり、続いていない括弧は詰まらないこと。"""
    font = ctx.font
    ours = ctx.ours
    report = Report(ctx.label)
    # chws・vchw: 続いた約物だけが詰まり (既定ではかからない)、続いていない括弧は詰まらない
    em_half = font["head"].unitsPerEm // 2
    for tag, vertical in (("chws", False), ("vchw", True)):
        for text, index in (("「『あ", 1), ("あ。」い", 1), ("あ」「い", 1), ("あ、　い", 1), ("・「あ", 1)):
            on = ours.shaper.shape(text, "ja", vertical, (tag,))
            off = ours.shaper.shape(text, "ja", vertical)
            saved = abs(off[index][3 if vertical else 2]) - abs(on[index][3 if vertical else 2])
            if saved != em_half:
                report(f"{tag} does not trim adjacent punctuation by half an em", text)
        for text in ("「あ」", "あ。い"):
            if ours.shaper.shape(text, "ja", vertical, (tag,)) != ours.shaper.shape(text, "ja", vertical):
                report(f"{tag} trims punctuation that is not adjacent", text)
    report.flush()


def check_double_trimming(ctx: FontContext) -> None:
    """安全な palt・vpal の指定と、二重に詰まる指定の区別。"""
    label = ctx.label
    ours = ctx.ours
    udp = ctx.udp_shaped
    run = ctx.run
    # chws/vchw と halt/vhal を明示的に有効にして二重詰めを再現し、安全な指定と区別する。
    text = "「春、（花）・風。」"
    for vertical, proportional, contextual, half in [(False, "palt", "chws", "halt"),
                                                     (True, "vpal", "vchw", "vhal")]:
        safe = (proportional, contextual + "=0", half + "=0")
        positioned, reference = ours.run(text, "ja", vertical, safe), udp.run(text, "ja", vertical)
        # BIZ UDP は輪郭そのものを移動した字を持つので、輪郭と placement の生値ではなく、
        # 実際の送りとインクの中心を比べる。縦組の括弧などの輪郭寸法の違いは許す。
        check([r[1:3] for r in positioned] == [r[1:3] for r in reference],
              f"{label}: safe {proportional} advances differ from BIZ UDP")
        ink, reference_ink = ours.ink(text, "ja", vertical, safe), udp.ink(text, "ja", vertical)
        check(len(ink) == len(reference_ink) and all(
            a is not None and b is not None and all(abs((a[k] + a[k+2] - b[k] - b[k+2]) / 2) <= 1 for k in (0, 1))
            for a, b in zip(ink, reference_ink)), f"{label}: safe {proportional} positions differ from BIZ UDP")
        a = run(text, safe, vertical)
        safe_advance = sum(abs(r[3]) if vertical else r[2] for r in a)
        check(all(abs(r[3]) > 0 if vertical else r[2] > 0 for r in a),
              f"{label}: safe proportional spacing has non-positive advances")
        for incompatible in (contextual, half):
            b = run(text, (proportional, incompatible), vertical)
            double_advance = sum(abs(r[3]) if vertical else r[2] for r in b)
            check(double_advance < safe_advance and a != b,
                  f"{label}: {proportional}+{incompatible} did not reproduce double trimming")
