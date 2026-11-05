"""約物の詰め (OpenType の halt と vhal) を作る。build.py が使う。

全角の約物は、字の枠の半分ほどが空いている。halt (横組) と vhal (縦組) は、その空きを
半分にする位置と字幅を持つ。ブラウザの text-spacing-trim (Chromium は既定で、続いた約物の
間を詰める) は、これを使って「『 や 。」 の間のアキを詰める。値は JLReq の約物の分類に従う。

- 始め括弧類 (cl-01): 横組は前 (左) の空き、縦組は上の空きを除く
- 終わり括弧類 (cl-02) と読点類・句点類 (cl-06・cl-07): 後ろ (右・下) の空きを除く
- 中点類 (cl-05): 前後の空きを 4 分の 1 ずつ除く

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


def add(font: TTFont) -> dict[str, int]:
    """GPOS に halt と vhal を作る (元の BIZ UD には GPOS が無い)。用字系は GSUB と同じにする"""
    if "GPOS" in font:
        raise SystemExit("the font already has GPOS; merge the features instead of replacing it")
    values = plan(font)
    scripts = [record.ScriptTag for record in font["GSUB"].table.ScriptList.ScriptRecord]
    lines = [f"languagesystem {script} dflt;" for script in ["DFLT"] + [s for s in scripts if s != "DFLT"]]
    for tag, glyphs in values.items():
        lines.append(f"feature {tag} {{")
        for glyph, (x, y, x_advance, y_advance) in sorted(glyphs.items()):
            lines.append(f"  pos {glyph} <{x} {y} {x_advance} {y_advance}>;")
        lines.append(f"}} {tag};")
    addOpenTypeFeaturesFromString(font, "\n".join(lines) + "\n", tables=["GPOS"])
    return {tag: len(glyphs) for tag, glyphs in values.items()}
