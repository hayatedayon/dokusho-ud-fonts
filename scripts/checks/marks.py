"""結合用の記号と濁点・半濁点の付く位置。"""

import unicodedata

from fontTools.ttLib import TTFont

import spec

from .common import FontContext, Report, check, problems
from .fonttables import combining_codes, feature_lookup_indexes, gsub_mapping, lookup_subtables, lookup_type, outline
from .geometry import glyph_bounds, moved_by


def mark_attachments(font: TTFont, kind: int) -> list:
    """mark (kind 4) か mkmk (kind 6) の lookup のサブテーブル"""
    gpos = font["GPOS"].table
    tag = "mark" if kind == 4 else "mkmk"
    result = []
    for record in gpos.FeatureList.FeatureRecord:
        if record.FeatureTag == tag:
            for index in record.Feature.LookupListIndex:
                lookup = gpos.LookupList.Lookup[index]
                if lookup.LookupType == kind:
                    result += [s for s in lookup.SubTable if s not in result]
    return result


def attach(font: TTFont, base: str, mark: str, kind: int = 4):
    """base の後の mark の、インクの外形 (base の原点からの位置)。付けられなければ None"""
    for subtable in mark_attachments(font, kind):
        if kind == 4:
            bases, marks = subtable.BaseCoverage.glyphs, subtable.MarkCoverage.glyphs
            records = subtable.BaseArray.BaseRecord
        else:
            bases, marks = subtable.Mark2Coverage.glyphs, subtable.Mark1Coverage.glyphs
            records = subtable.Mark2Array.Mark2Record
        if base not in bases or mark not in marks:
            continue
        mark_array = subtable.MarkArray if kind == 4 else subtable.Mark1Array
        mark_record = mark_array.MarkRecord[marks.index(mark)]
        record = records[bases.index(base)]
        base_anchor = (record.BaseAnchor if kind == 4 else record.Mark2Anchor)[mark_record.Class]
        if base_anchor is None:
            continue
        dx = base_anchor.XCoordinate - mark_record.MarkAnchor.XCoordinate
        dy = base_anchor.YCoordinate - mark_record.MarkAnchor.YCoordinate
        x0, y0, x1, y1 = glyph_bounds(font, mark)
        return x0 + dx, y0 + dy, x1 + dx, y1 + dy
    return None


def check_marks(ctx: FontContext) -> None:
    """結合用の記号 (アクセント U+0300〜036F と、濁点・半濁点 U+3099・U+309A)。
    - 字幅が 0 で、形は BIZ UD の字を横に動かしただけ。GDEF で記号の字
    - 上の記号は、欧字・ギリシャ文字・キリル文字の上の真ん中に、字に触れずに乗る。下の記号は、
      下の真ん中に付き、ディセンダーのある字では、その下に下がる
    - 上の記号を 2 つ続けると、後の記号は前の記号の上に乗る (mkmk)
    - 濁点・半濁点は、仮名の枠の中で、高さは BIZ UD の字のまま、右の端が合成済みの字 (が など) の
      濁点の右の端の範囲に入る
    - i の後に上の記号が続くと、点の無い ı になる (ccmp)
    - BIZ UD の半角の ´ ｀ ¨ (hwid) は、BIZ UD の字のまま"""
    label = ctx.label
    font = ctx.font
    ud = ctx.ud
    cmap, cmap_ud = font.getBestCmap(), ud.getBestCmap()
    em = font["head"].unitsPerEm
    if "GDEF" not in font or font["GDEF"].table.GlyphClassDef is None:
        problems.append(f"{label}: no GDEF glyph classes")
        return
    classes = font["GDEF"].table.GlyphClassDef.classDefs
    codes = combining_codes(cmap)
    check(codes == combining_codes(cmap_ud), f"{label}: other combining marks than in BIZ UD")
    for code in codes:
        g = cmap[code]
        check(font["hmtx"][g][0] == 0 and font["vmtx"][g][0] == 0, f"{label}: U+{code:04X} is not of zero width")
        check(classes.get(g) == 3, f"{label}: U+{code:04X} is not a mark in GDEF")
        moved = moved_by(font, g, ud, cmap_ud[code])
        check(moved is not None and moved[1] == 0 and moved[0] < 0,
              f"{label}: U+{code:04X} is not BIZ UD's glyph moved to the left")

    x_height = glyph_bounds(font, cmap[0x78])[3]
    marks_set = {cmap[c] for c in codes}
    bases = [cmap[c] for c in cmap
             if (c in spec.LATIN or 0x0370 <= c <= 0x052F or 0xFF10 <= c <= 0xFF19
                 or 0xFF21 <= c <= 0xFF3A or 0xFF41 <= c <= 0xFF5A)
             and unicodedata.category(chr(c))[0] in "LN" and glyph_bounds(font, cmap[c]) is not None]
    base_set = set(bases)
    for tag in ("tnum", "zero", "hwid", "fwid"):
        for key, target in gsub_mapping(font, tag).items():
            if key in base_set and target not in marks_set and target not in base_set \
                    and glyph_bounds(font, target) is not None:
                bases.append(target)
                base_set.add(target)
    above = [c for c in codes if unicodedata.combining(chr(c)) == 230]
    below = [c for c in codes if unicodedata.combining(chr(c)) == 220]
    for base in bases:
        check(classes.get(base) == 1, f"{label}: {base} is not a base glyph in GDEF")
        bx0, by0, bx1, by1 = glyph_bounds(font, base)
        center = (bx0 + bx1) / 2
        for code in above + below:
            placed = attach(font, base, cmap[code])
            if placed is None:
                problems.append(f"{label}: U+{code:04X} does not attach to {base}")
                continue
            x0, y0, x1, y1 = placed
            check(abs((x0 + x1) / 2 - center) <= 1, f"{label}: U+{code:04X} is not centered on {base}")
            if code in above:
                check(y0 > by1, f"{label}: U+{code:04X} touches {base}")
            else:
                lowered = by0 if by0 < -em / 16 else 0  # ディセンダーのある字だけ、その下へ
                check(abs(y1 - (glyph_bounds(font, cmap[code])[3] + lowered)) <= 1,
                      f"{label}: U+{code:04X} is not under {base}")
    for code in above:
        first = attach(font, cmap[0x6F], cmap[code])
        second = attach(font, cmap[code], cmap[code], 6)
        check(first is not None and second is not None and second[1] + (first[1] - glyph_bounds(font, cmap[code])[1]) > first[3],
              f"{label}: U+{code:04X} does not stack on itself")

    for mark in (0x3099, 0x309A):
        ends = []
        for code in range(0x3041, 0x3100):
            parts = unicodedata.decomposition(chr(code)).split()
            if len(parts) == 2 and int(parts[1], 16) == mark:
                ends.append((int(parts[0], 16), glyph_bounds(font, cmap[code])[2]))
        low, high = min(e for _, e in ends), max(e for _, e in ends)
        design = glyph_bounds(ud, cmap_ud[mark])
        for base_code, _end in ends:
            placed = attach(font, cmap[base_code], cmap[mark])
            if placed is None:
                problems.append(f"{label}: U+{mark:04X} does not attach to U+{base_code:04X}")
                continue
            x0, y0, x1, y1 = placed
            check(0 <= x0 and x1 <= em and low <= x1 <= high and (y0, y1) == (design[1], design[3]),
                  f"{label}: U+{mark:04X} on U+{base_code:04X} is not where the precomposed kana have it")

    # i と上の記号 → ı (ccmp の文脈の置き換え。下の記号などを飛ばす MarkFilteringSet 付き)
    gsub = font["GSUB"].table
    mark_sets = getattr(font["GDEF"].table, "MarkGlyphSetsDef", None)
    i, dotless = cmap[0x69], cmap[0x131]
    want_above = {cmap[c] for c in codes if unicodedata.combining(chr(c)) in (230, 232, 234)}
    found = False
    for index in feature_lookup_indexes(font, {"ccmp"}):
        if lookup_type(gsub, index) != 6:
            continue
        lookup = gsub.LookupList.Lookup[index]
        for subtable in lookup_subtables(gsub, index):
            if (subtable.Format == 3 and i in subtable.InputCoverage[0].glyphs and subtable.LookAheadCoverage
                    and want_above <= set(subtable.LookAheadCoverage[0].glyphs)
                    and (lookup.LookupFlag & 0x0010) and mark_sets is not None
                    and mark_sets.Coverage[lookup.MarkFilteringSet].glyphs == subtable.LookAheadCoverage[0].glyphs):
                found = all(dict(next(iter(lookup_subtables(gsub, r.LookupListIndex))).mapping).get(i) == dotless
                            for r in subtable.SubstLookupRecord)
    check(found, f"{label}: i before marks above does not become dotless with mark filtering")

    # BIZ UD の hwid の置き換え先だった結合用の記号 (半角の ´ ｀ ¨) は、BIZ UD の字のまま
    hwid, hwid_ud = gsub_mapping(font, "hwid"), gsub_mapping(ud, "hwid")
    marks_ud = {cmap_ud[c] for c in codes}
    for key, value in hwid_ud.items():
        if value in marks_ud:
            ours = hwid.get(key)
            check(ours is not None and font["hmtx"][ours] == ud["hmtx"][value] and outline(font, ours) == outline(ud, value),
                  f"{label}: hwid of {key} is not BIZ UD's half-width {value}")


def check_shaped_marks(ctx: FontContext) -> None:
    """結合用の記号が前の字に乗ること、i の点、縦組の小書きの仮名と濁点 (HarfBuzz)。"""
    font = ctx.font
    ours = ctx.ours
    cmap = ctx.cmap
    marks = ctx.marks
    report = Report(ctx.label)
    # 結合用の記号
    bases = [code for code in sorted(cmap)
             if (code in spec.LATIN or 0x0370 <= code <= 0x052F or 0xFF10 <= code <= 0xFF19
                 or 0xFF21 <= code <= 0xFF3A or 0xFF41 <= code <= 0xFF5A)
             and unicodedata.category(chr(code))[0] in "LN" and glyph_bounds(font, cmap[code]) is not None]
    for mark in sorted(marks):
        combining = unicodedata.combining(chr(mark))
        if combining not in (220, 230):
            continue
        for base in bases:
            text = chr(base) + chr(mark)
            boxes = ours.ink(text, "en")
            if len(boxes) != 2:
                continue  # 合成済みの字になった (é など)
            (bx0, by0, bx1, by1), (mx0, my0, mx1, my1) = boxes
            centered = abs((bx0 + bx1) / 2 - (mx0 + mx1) / 2) <= 1
            clear = my0 > by1 if combining == 230 else my1 < by1
            if not (centered and clear):
                report("combining marks do not sit on the letter", f"U+{base:04X} U+{mark:04X}")
    for base_char, feat in [("1", ("tnum",)), ("0", ("zero",)), ("０", ("zero",)), ("A", ("hwid",)), ("Ａ", ("hwid",))]:
        for mark, above_mark in [(0x030B, True), (0x0325, False)]:
            boxes = ours.ink(base_char + chr(mark), "en", False, feat)
            if len(boxes) != 2 or abs((boxes[0][0] + boxes[0][2]) / 2 - (boxes[1][0] + boxes[1][2]) / 2) > 1 \
                    or (boxes[1][1] <= boxes[0][3] if above_mark else boxes[1][3] >= boxes[0][3]):
                report("combining marks do not sit on substituted bases", f"{base_char} {feat} U+{mark:04X}")
    # i と上の記号 (下の記号を挟んだ i̥̋ や、2 つの字の上にかかる i͡a も) → 点の無い ı
    dotless_id, dotted_id = font.getGlyphID(cmap[0x131]), font.getGlyphID(cmap[0x69])
    for text, above_index in [("i\u030b", 1), ("i\u0325\u030b", 2), ("i\u0361a", 1)]:
        shaped_i = ours.shaper.shape(text, "en")
        boxes = ours.ink(text, "en")
        if shaped_i[0][0] != dotless_id or boxes[above_index][1] <= boxes[0][3]:
            report("i before a mark above does not become dotless cleanly", repr(text))
    # 全角の ｉ も、上の記号の前では点の無い字
    fullwidth_id = font.getGlyphID(cmap[0xFF49])
    if ours.shaper.shape("\uff49\u0301", "en")[0][0] == fullwidth_id:
        report("full-width i before a mark above keeps its dot", "U+FF49 U+0301")
    if ours.shaper.shape("\uff49", "en")[0][0] != fullwidth_id:
        report("full-width i without a mark loses its dot", "U+FF49")
    # 縦組の小書きの仮名は、間にほかの記号があっても濁点と同じ位置に戻る (GPOS の文脈が記号を飛ばす)
    for mark in (0x3099, 0x309A):
        plain, between = ours.shaper.shape(f"っ{chr(mark)}", "ja", True), ours.shaper.shape(f"っ\u0334{chr(mark)}", "ja", True)
        if (plain[0][4:], plain[1][4:]) != (between[0][4:], between[-1][4:]):
            report("small kana do not move for a kana mark after another mark", f"U+{mark:04X}")
    for text in ("i\u0325", "ia\u030b"):
        if ours.shaper.shape(text, "en")[0][0] != dotted_id:
            report("i without a mark above loses its dot", repr(text))
    report.flush()


def check_kana_marks(ctx: FontContext) -> None:
    """濁点・半濁点が前の仮名の枠の中に付き、縦組・vpal でも位置が変わらないこと。"""
    font = ctx.font
    ours = ctx.ours
    cmap = ctx.cmap
    report = Report(ctx.label)
    em = font["head"].unitsPerEm
    for mark in (0x3099, 0x309A):
        for base in [c for c in [*range(0x3041, 0x3100), *range(0x31F0, 0x3200)]
                     if c in cmap and unicodedata.category(chr(c)) == "Lo"]:
            text = chr(base) + chr(mark)
            if unicodedata.normalize("NFC", text) != text:
                continue
            horizontal_boxes = ours.ink(text, "ja", False)
            if len(horizontal_boxes) != 2 or horizontal_boxes[1] is None:
                continue  # 合字になった (か゚ など)
            (hbx0, hby0, hbx1, hby1), (hmx0, hmy0, hmx1, hmy1) = horizontal_boxes
            h_rel = ((hmx0 + hmx1 - hbx0 - hbx1) / 2, (hmy0 + hmy1 - hby0 - hby1) / 2)
            for vertical in (False, True):
                boxes = horizontal_boxes if not vertical else ours.ink(text, "ja", True)
                if len(boxes) != 2 or boxes[1] is None:
                    report("kana marks are lost in vertical text", f"U+{base:04X} U+{mark:04X}")
                    continue
                (bx0, by0, bx1, by1), (mx0, my0, mx1, my1) = boxes
                # 仮名の枠: 横組は (0, -usWinDescent)〜(em, usWinAscent)、縦組は x が -em/2〜em/2、y が -em〜0
                # (HarfBuzz は、縦組の字の位置を、縦組の原点 (枠の上の真ん中) からのずれで返す)
                inside = (-em / 2 <= mx0 and mx1 <= em / 2 and -em <= my0 and my1 <= 0) if vertical else \
                    (0 <= mx0 and mx1 <= em and -font["OS/2"].usWinDescent <= my0 and my1 <= font["OS/2"].usWinAscent)
                if not inside:
                    report("kana marks are not in the box of the kana", f"U+{base:04X} U+{mark:04X}"
                           f"{' (vertical)' if vertical else ''}")
                if vertical:
                    rel = ((mx0 + mx1 - bx0 - bx1) / 2, (my0 + my1 - by0 - by1) / 2)
                    if abs(rel[0] - h_rel[0]) > 1.5 or abs(rel[1] - h_rel[1]) > 1.5:
                        report("kana marks shift on vertical kana", f"U+{base:04X} U+{mark:04X}")
                    vpal_boxes = ours.ink(text, "ja", True, ("vpal",))
                    if len(vpal_boxes) != 2 or vpal_boxes[1] is None \
                            or (vpal_boxes[1][0] - vpal_boxes[0][0], vpal_boxes[1][1] - vpal_boxes[0][1]) != (mx0 - bx0, my0 - by0):
                        report("kana marks do not follow the kana with vpal", f"U+{base:04X} U+{mark:04X}")
    report.flush()
