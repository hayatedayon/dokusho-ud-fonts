"""約物の詰め (OpenType の halt と vhal) と、仮名・約物を詰めて組む palt を作る。build.py が使う。

全角の約物は、字の枠の半分ほどが空いている。halt (横組) と vhal (縦組) は、その空きを
半分にする位置と字幅を持つ。ブラウザの text-spacing-trim (Chromium は既定で、続いた約物の
間を詰める) は、これを使って「『 や 。」 の間のアキを詰める。値は JLReq の約物の分類に従う。

- 始め括弧類 (cl-01): 横組は前 (左) の空き、縦組は上の空きを除く
- 終わり括弧類 (cl-02) と読点類・句点類 (cl-06・cl-07): 後ろ (右・下) の空きを除く
- 中点類 (cl-05): 前後の空きを 4 分の 1 ずつ除く

palt (プロポーショナルな字幅。見出しなどで使う) は、BIZ UDP の字幅にする。BIZ UDP の仮名・約物・
全角の字は、BIZ UD と同じ形を、字幅を変えて置き直したもの。形が同じで (横にずらしただけ)、字幅の
違う字に、BIZ UDP と同じ位置と字幅になる値を付ける。明朝 Bold の BIZ UDP は輪郭が少し作り直されて
いる (点の数が違い、1 単位ずれる) ので、インクの外形が SAME_INK 単位まで同じなら同じ字とみなし、
インクの中心と縦送りを BIZ UDP にそろえる vpal も作る。

縦組の値は、vert で置き換えた縦組の字に付ける。インクが、詰めて残す半分に収まっている字だけを
選ぶ (詰めると隣の字と重なる字には付けない。縦組の “ と ； がそうなる)。
"""

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont

OPENING = "「『（［｛〔〈《【〖〘〝‘“｟"
CLOSING = "」』）］｝〕〉》】〗〙〟’”｠、。，．"
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
VERTICAL_SAME_INK = 100


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


def proportional(font: TTFont, udp: TTFont) -> dict[str, tuple[int, int, int, int]]:
    """palt の値。読書 UD の字が、BIZ UDP の同じ文字の字を横にずらしたもので、字幅が違うもの"""
    cmap, cmap_udp = font.getBestCmap(), udp.getBestCmap()
    values: dict[str, tuple[int, int, int, int]] = {}
    for code, name in sorted(cmap.items()):
        other = cmap_udp.get(code)
        if other is None or font["hmtx"][name][0] == udp["hmtx"][other][0]:
            continue
        dx = shift(font, name, udp, other)
        if dx is None:
            continue
        value = (dx, 0, udp["hmtx"][other][0] - font["hmtx"][name][0], 0)
        if values.setdefault(name, value) != value:
            raise SystemExit(f"{name} would need two palt values")
    return values


def proportional_vertical(font: TTFont, udp: TTFont) -> dict[str, tuple[int, int, int, int]]:
    """vpal の値。vert 置換後の字形を BIZ UDP と同じ縦位置・縦送りにする。"""
    cmap, cmap_udp = font.getBestCmap(), udp.getBestCmap()
    forms, forms_udp = vertical_forms(font), vertical_forms(udp)
    values: dict[str, tuple[int, int, int, int]] = {}
    for code, name in sorted(cmap.items()):
        other = cmap_udp.get(code)
        if other is None:
            continue
        upright, upright_udp = forms.get(name, name), forms_udp.get(other, other)
        if upright == name and upright_udp == other:
            continue
        a, b = ink(font, upright), ink(udp, upright_udp)
        if a is None or b is None:
            continue
        # 同じ縦組字形で、輪郭の縦寸法が近いものだけを位置補正する。
        if (abs((a[3] - a[1]) - (b[3] - b[1])) > VERTICAL_SAME_INK
                or abs((a[2] - a[0]) - (b[2] - b[0])) > VERTICAL_SAME_INK):
            continue
        dy = round(((b[1] + b[3]) - (a[1] + a[3])) / 2)
        advance = udp["vmtx"][upright_udp][0] - font["vmtx"][upright][0]
        if dy or advance:
            value = (0, dy, 0, advance)
            if values.setdefault(upright, value) != value:
                raise SystemExit(f"{upright} would need two vpal values")
    return values


def add(font: TTFont, udp: TTFont, extra: str = "") -> dict[str, int]:
    """GPOS に halt・vhal・palt を作る (元の BIZ UD には GPOS が無い)。用字系は GSUB と同じにする。
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
    lines.append(extra)
    tables = ["GPOS", "GDEF"] if "table GDEF" in extra else ["GPOS"]
    addOpenTypeFeaturesFromString(font, "\n".join(lines) + "\n", tables=tables)
    return {tag: len(glyphs) for tag, glyphs in values.items()}
