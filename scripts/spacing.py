"""約物の詰め (OpenType の halt と vhal) と、仮名・約物を詰めて組む palt・vpal を作る。build.py が使う。

全角の約物は、字の枠の半分ほどが空いている。halt (横組) と vhal (縦組) は、その空きを
半分にする位置と字幅を持つ。ブラウザの text-spacing-trim (Chromium は既定で、続いた約物の
間を詰める) は、これを使って「『 や 。」 の間のアキを詰める。値は JLReq の約物の分類に従う。

- 始め括弧類 (cl-01): 横組は前 (左) の空き、縦組は上の空きを除く
- 終わり括弧類 (cl-02) と読点類・句点類 (cl-06・cl-07): 後ろ (右・下) の空きを除く
- 中点類 (cl-05): 前後の空きを 4 分の 1 ずつ除く

縦組の値は、vert で置き換えた縦組の字に付ける。インクが、詰めて残す半分に収まっている字だけを
選ぶ (詰めると隣の字と重なる字には付けない。縦組の “ と ； がそうなる)。

palt (横組) と vpal (縦組) は、プロポーショナルな字幅・縦の字送り (見出しなどで使う) で、BIZ UDP に
合わせる。BIZ UDP の仮名・約物・全角の字 (か゚・ㇷ゚ など ccmp の半濁点の合字も) は、BIZ UD と同じ形を、
字幅や縦の字送りを変えて置き直したもの。
palt は、形が同じで (横にずらしただけ) 字幅の違う字に、BIZ UDP と同じ位置と字幅になる値を付ける。明朝
Bold の BIZ UDP は輪郭が少し作り直されている (点の数が違い、1 単位ずれる) ので、インクの外形が
SAME_INK 単位まで同じなら同じ字とみなし、インクの中心を BIZ UDP にそろえる。vpal は、vert で置き換えた
縦組の字 (BIZ UDP 側だけに vert がある仮名なども含む) のうち、インクの幅と高さが spec.VERTICAL_SAME_INK
単位まで同じもの (BIZ UDP の縦組の括弧は、縦の線が少し短いものがある) に、縦組の原点 (glyf の yMax +
vmtx の上サイドベアリング) からのインクの中心と縦の字送りが BIZ UDP と同じになる値を付ける。
"""

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont

import spec

OPENING = "「『（［｛〔〈《【〖〘〝‘“｟"
CLOSING = "」』）］｝〕〉》】〗〙〞〟’”｠、。，．"
MIDDLE = "・：；"
KINDS = [("opening", OPENING), ("closing", CLOSING), ("middle", MIDDLE)]


def vertical_forms(font: TTFont) -> dict[str, str]:
    forms: dict[str, str] = {}
    gsub = font["GSUB"].table
    for record in gsub.FeatureList.FeatureRecord:
        if record.FeatureTag != "vert":
            continue
        for index in record.Feature.LookupListIndex:
            for subtable in gsub.LookupList.Lookup[index].SubTable:
                subtable = getattr(subtable, "ExtSubTable", subtable)
                for key, value in getattr(subtable, "mapping", {}).items():
                    forms.setdefault(key, value)  # 先の lookup のものを取る
    return forms


def ink(font: TTFont, glyph: str):
    pen = BoundsPen(font.getGlyphSet())
    font.getGlyphSet()[glyph].draw(pen)
    return pen.bounds


def fits(font: TTFont, glyph: str, kind: str, vertical: bool) -> bool:
    """詰めた後も、インクが字の枠 (詰めて残す半分) に収まるか"""
    em = font["head"].unitsPerEm
    bounds = ink(font, glyph)
    if bounds is None:
        return False
    if vertical:
        advance, top_side = font["vmtx"][glyph]
        start, end = top_side, top_side + (bounds[3] - bounds[1])  # 字の枠の上からの位置
    else:
        advance = font["hmtx"][glyph][0]
        start, end = bounds[0], bounds[2]
    if advance != em:
        return False
    if kind == "opening":
        return start >= em // 2
    if kind == "closing":
        return end <= em // 2
    return start >= em // 4 and end <= em - em // 4


def value(kind: str, em: int, vertical: bool) -> tuple[int, int, int, int]:
    """(XPlacement, YPlacement, XAdvance, YAdvance)"""
    half, quarter = em // 2, em // 4
    shift = {"opening": half, "closing": 0, "middle": quarter}[kind]
    if vertical:
        return (0, shift, 0, -half)
    return (-shift, 0, -half, 0)


def plan(font: TTFont) -> dict[str, dict[str, tuple[int, int, int, int]]]:
    """halt と vhal に付ける、グリフごとの値"""
    em = font["head"].unitsPerEm
    cmap = font.getBestCmap()
    forms = vertical_forms(font)
    result: dict[str, dict[str, tuple[int, int, int, int]]] = {"halt": {}, "vhal": {}}
    for kind, chars in KINDS:
        for char in chars:
            glyph = cmap.get(ord(char))
            if glyph is None:
                continue
            if fits(font, glyph, kind, vertical=False):
                result["halt"][glyph] = value(kind, em, vertical=False)
            upright = forms.get(glyph, glyph)
            if fits(font, upright, kind, vertical=True):
                result["vhal"][upright] = value(kind, em, vertical=True)
    return result


SAME_INK = 20


def shift(font: TTFont, name: str, other: TTFont, other_name: str) -> int | None:
    """name を横にずらすと other の other_name と重なるなら、そのずれ。そうでなければ None。
    輪郭が同じならそのずれ、インクの外形 (幅・高さ・上下) が SAME_INK まで同じなら、中心のずれ"""
    a, ends_a, flags_a = font["glyf"][name].getCoordinates(font["glyf"])
    b, ends_b, flags_b = other["glyf"][other_name].getCoordinates(other["glyf"])
    if len(a) == 0 or len(b) == 0:
        return None
    if list(ends_a) == list(ends_b) and list(flags_a) == list(flags_b):
        dx = b[0][0] - a[0][0]
        if all((q[0] - p[0], q[1] - p[1]) == (dx, 0) for p, q in zip(a, b)):
            return dx
    box_a, box_b = ink(font, name), ink(other, other_name)
    width_a, width_b = box_a[2] - box_a[0], box_b[2] - box_b[0]
    if abs(width_a - width_b) > SAME_INK or abs(box_a[1] - box_b[1]) > SAME_INK or abs(box_a[3] - box_b[3]) > SAME_INK:
        return None
    return round(((box_b[0] + box_b[2]) - (box_a[0] + box_a[2])) / 2)


def ccmp_ligatures(font: TTFont) -> dict[tuple[str, ...], str]:
    """ccmp の合字 {(最初の字, つなぐ字, ...): 置き換え先}"""
    import build  # build.py がこのモジュールを読み込むので、ここで読み込む

    result: dict[tuple[str, ...], str] = {}
    for subtable in build.feature_subtables(font["GSUB"].table, "ccmp", "ligatures"):
        for first, items in subtable.ligatures.items():
            for item in items:
                result.setdefault((first, *item.Component), item.LigGlyph)
    return result


def glyph_pairs(font: TTFont, udp: TTFont) -> list[tuple[str, str]]:
    """文字に割り当てた字と、ccmp の和文の合字 (か゚・ㇷ゚ など) の、(読書 UD の字, BIZ UDP の字)"""
    cmap, cmap_udp = font.getBestCmap(), udp.getBestCmap()
    pairs = [(name, cmap_udp[code]) for code, name in sorted(cmap.items()) if code in cmap_udp]
    by_name = {name: code for code, name in sorted(cmap.items(), reverse=True)}
    ligs_udp = ccmp_ligatures(udp)
    for sequence, target in sorted(ccmp_ligatures(font).items()):
        if not all(g in by_name for g in sequence) or by_name[sequence[0]] in spec.LATIN:
            continue
        codes = [by_name[g] for g in sequence]
        if all(c in cmap_udp for c in codes):
            other = ligs_udp.get(tuple(cmap_udp[c] for c in codes))
            if other is not None:
                pairs.append((target, other))
    return pairs


def proportional(font: TTFont, udp: TTFont) -> dict[str, tuple[int, int, int, int]]:
    """palt の値。読書 UD の字が、BIZ UDP の同じ文字 (または ccmp の合字) の字を横にずらしたもので、
    字幅か横の位置が違うもの (明朝 Bold の ヅ・プ・け゚・ツ゚ などは、字幅は全角のまま横にずれている)"""
    values: dict[str, tuple[int, int, int, int]] = {}
    for name, other in glyph_pairs(font, udp):
        if font["hmtx"][name] == udp["hmtx"][other]:
            continue
        dx = shift(font, name, udp, other)
        advance = udp["hmtx"][other][0] - font["hmtx"][name][0]
        if dx is None or (not dx and not advance):
            continue
        value = (dx, 0, advance, 0)
        if values.setdefault(name, value) != value:
            raise SystemExit(f"{name} would need two palt values")
    return values


def vertical_origin(font: TTFont, glyph: str) -> int:
    """TrueType (VORG の無い glyf フォント) の縦組の原点の y 座標。yMax は制御点も含む外形で、保存するときに
    計算し直される値なので、ビルドの途中で字を動かしても合うように、輪郭から求める"""
    glyf = font["glyf"]
    return glyf[glyph].getCoordinates(glyf)[0].calcIntBounds()[3] + font["vmtx"][glyph][1]


def proportional_vertical(font: TTFont, udp: TTFont) -> dict[str, tuple[int, int, int, int]]:
    """vpal の値。vert で置き換えた縦組の字を、BIZ UDP と同じ縦の位置 (縦組の原点からのインクの中心) と
    縦の字送りにする"""
    forms, forms_udp = vertical_forms(font), vertical_forms(udp)
    values: dict[str, tuple[int, int, int, int]] = {}
    for name, other in glyph_pairs(font, udp):
        upright, upright_udp = forms.get(name, name), forms_udp.get(other, other)
        if upright == name and upright_udp == other:
            continue
        a, b = ink(font, upright), ink(udp, upright_udp)
        if a is None or b is None:
            continue
        # 同じ縦組字形で、輪郭の寸法が近いものだけを位置補正する (括弧は縦の線の長さが少し違う)
        if (abs((a[3] - a[1]) - (b[3] - b[1])) > spec.VERTICAL_SAME_INK
                or abs((a[2] - a[0]) - (b[2] - b[0])) > spec.VERTICAL_SAME_INK):
            continue
        # 明朝 Bold では、制御点の違いで縦組の原点 (yMax + 上サイドベアリング) が BIZ UDP とずれる字がある
        origin_a, origin_b = vertical_origin(font, upright), vertical_origin(udp, upright_udp)
        dy = round(((b[1] + b[3]) - 2 * origin_b - ((a[1] + a[3]) - 2 * origin_a)) / 2)
        advance = udp["vmtx"][upright_udp][0] - font["vmtx"][upright][0]
        if dy or advance:
            value = (0, dy, 0, advance)
            if values.setdefault(upright, value) != value:
                raise SystemExit(f"{upright} would need two vpal values")
    return values


def contextual_spacing(font: TTFont, values: dict) -> list[str]:
    """chws (横組) と vchw (縦組)。halt・vhal の字が続く所だけを詰める。Chromium は、chws を持つフォントでは自前の
    詰めの代わりにこれを使うので、text-spacing-trim: normal の結果 (GPOS の halt だけのときと同じ) にそろえる。
    終わりの字 (括弧・句読点) は、後ろに括弧・中点類・全角の空白・終わりの引用符が続くと半角に、始め括弧は、前に始め括弧・
    中点類・全角の空白・始めの引用符があると半角にする"""
    em, cmap, forms = font["head"].unitsPerEm, font.getBestCmap(), vertical_forms(font)
    lines = []
    for tag, source, vertical in (("chws", "halt", False), ("vchw", "vhal", True)):
        opening_value, closing_value = value("opening", em, vertical), value("closing", em, vertical)
        opening = sorted(g for g, v in values[source].items() if v == opening_value)
        closing = sorted(g for g, v in values[source].items() if v == closing_value)
        # 詰められない字 (縦組の ； は halt・vhal を持たない) は、隣の字の詰めにも数えない
        middle = sorted({forms.get(cmap[ord(c)], cmap[ord(c)]) if vertical else cmap[ord(c)] for c in MIDDLE}
                        & set(values[source]))
        space = [cmap[0x3000]]

        def quote_forms(codes) -> list[str]:
            """locl で BIZ UDP の字にした引用符 (縦組は、その縦組の字もあれば含める)"""
            names = [f"{cmap[code]}.latn" for code in codes]
            if vertical:
                names += [f"{name}.vert" for name in names if f"{name}.vert" in font["hmtx"].metrics]
            return names

        opening_quotes, closing_quotes = quote_forms((0x2018, 0x201C)), quote_forms((0x2019, 0x201D))
        after_closing = " ".join(sorted({*opening, *closing, *middle, *space, *closing_quotes}))
        before_opening = " ".join(sorted({*opening, *middle, *space, *opening_quotes}))

        def record(v: tuple[int, int, int, int]) -> str:
            return f"<{v[0]} {v[1]} {v[2]} {v[3]}>"

        lines += [f"feature {tag} {{",
                  f"  pos [{' '.join(closing)}]' {record(closing_value)} [{after_closing}];",
                  f"  pos [{before_opening}] [{' '.join(opening)}]' {record(opening_value)};",
                  f"}} {tag};"]
    return lines


def add(font: TTFont, udp: TTFont, extra: str = "") -> dict[str, int]:
    """GPOS に halt・vhal・palt・vpal を作る (元の BIZ UD には GPOS が無い)。用字系は GSUB と同じにする。
    extra は、一緒に組み込む機能ファイルの文 (結合用の記号の mark・mkmk と GDEF。combining_marks.py)"""
    if "GPOS" in font:
        raise SystemExit("the font already has GPOS; merge the features instead of replacing it")
    values = plan(font)
    values["palt"] = proportional(font, udp)
    values["vpal"] = proportional_vertical(font, udp)
    scripts = [record.ScriptTag for record in font["GSUB"].table.ScriptList.ScriptRecord]
    lines = [f"languagesystem {script} dflt;" for script in ["DFLT"] + [s for s in scripts if s != "DFLT"]]
    for tag, glyphs in values.items():
        lines.append(f"feature {tag} {{")
        for glyph, (x, y, x_advance, y_advance) in sorted(glyphs.items()):
            lines.append(f"  pos {glyph} <{x} {y} {x_advance} {y_advance}>;")
        lines.append(f"}} {tag};")
    lines.extend(contextual_spacing(font, values))
    lines.append(extra)
    tables = ["GPOS", "GDEF"] if "table GDEF" in extra else ["GPOS"]
    addOpenTypeFeaturesFromString(font, "\n".join(lines) + "\n", tables=tables)
    return {tag: len(glyphs) for tag, glyphs in values.items()}
