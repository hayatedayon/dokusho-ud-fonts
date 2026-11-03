"""fonts/ の読書 UD を、元の BIZ UD・BIZ UDP と突き合わせて確かめる。

build.py とは別の書き方で、できたものだけを見る。1 つでも合わなければ 1 で終わる。
"""

import sys
from pathlib import Path

from fontTools.ttLib import TTFont

import spec

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "sources"
FONTS = ROOT / "fonts"

# 和文の字。BIZ UD のままで、全角 (横も縦も 1 em) であること
JAPANESE = "あいうえおっゃー漢字読書。、・「」（）：！？　"

problems: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        problems.append(message)


def outline(font: TTFont, name: str):
    coordinates, ends, flags = font["glyf"][name].getCoordinates(font["glyf"])
    return list(coordinates), list(ends), list(flags)


def gsub_mapping(font: TTFont, tag: str) -> dict:
    gsub = font["GSUB"].table
    mapping = {}
    for record in gsub.FeatureList.FeatureRecord:
        if record.FeatureTag != tag:
            continue
        for index in record.Feature.LookupListIndex:
            for subtable in gsub.LookupList.Lookup[index].SubTable:
                subtable = getattr(subtable, "ExtSubTable", subtable)
                mapping.update(getattr(subtable, "mapping", {}))
    return mapping


def check_font(family: dict, weight: str) -> None:
    label = spec.output_name(family, weight)
    font = TTFont(FONTS / label)
    ud = TTFont(SOURCES / f"{family['ud']}-{weight}.ttf")
    udp = TTFont(SOURCES / f"{family['udp']}-{weight}.ttf")
    cmap, cmap_ud, cmap_udp = font.getBestCmap(), ud.getBestCmap(), udp.getBestCmap()
    em = font["head"].unitsPerEm

    check(cmap == cmap_ud, f"{label}: the character map differs from BIZ UD")
    check(font.getGlyphOrder() == ud.getGlyphOrder(), f"{label}: the glyph order differs from BIZ UD")

    for code in spec.LATIN:
        g, gp = cmap[code], cmap_udp[code]
        check(font["hmtx"][g][0] == udp["hmtx"][gp][0], f"{label}: U+{code:04X} width is not BIZ UDP's")
        check(outline(font, g) == outline(udp, gp), f"{label}: U+{code:04X} outline is not BIZ UDP's")
    widths = {chr(c): font["hmtx"][cmap[c]][0] for c in map(ord, "iWm")}
    check(widths["i"] * 2 < widths["W"], f"{label}: Latin letters are not proportional: {widths}")

    for char in JAPANESE:
        g = cmap[ord(char)]
        check(font["hmtx"][g][0] == em, f"{label}: {char} is not full width")
        check(font["vmtx"][g][0] == em, f"{label}: {char} does not advance 1 em in vertical text")
        check(outline(font, g) == outline(ud, cmap_ud[ord(char)]), f"{label}: {char} outline is not BIZ UD's")
    for char in "×÷":
        g = cmap[ord(char)]
        check(font["hmtx"][g] == ud["hmtx"][cmap_ud[ord(char)]], f"{label}: {char} is not BIZ UD's")

    latin_glyphs = {cmap[c] for c in spec.LATIN}
    for tag in spec.LATIN_FEATURES:
        ours = {k: v for k, v in gsub_mapping(font, tag).items() if k in latin_glyphs}
        theirs = {k: v for k, v in gsub_mapping(udp, tag).items() if k in latin_glyphs}
        check(ours == theirs, f"{label}: {tag} of the Latin letters differs from BIZ UDP")
        for target in theirs.values():
            check(font["hmtx"][target] == udp["hmtx"][target] and font["vmtx"][target] == udp["vmtx"][target],
                  f"{label}: {tag} target {target} metrics are not BIZ UDP's")
    features = {r.FeatureTag for r in font["GSUB"].table.FeatureList.FeatureRecord}
    check({"vert", "vrt2", "fwid"} <= features, f"{label}: vertical or full-width features are missing")
    check("vhea" in font and "vmtx" in font, f"{label}: vertical metrics are missing")

    names = {(r.nameID, r.langID): r.toUnicode() for r in font["name"].names}
    check(names.get((1, 0x409)) == family["name_en"], f"{label}: English family name {names.get((1, 0x409))!r}")
    check(names.get((1, 0x411)) == family["name_ja"], f"{label}: Japanese family name {names.get((1, 0x411))!r}")
    check(names.get((2, 0x409)) == weight, f"{label}: style name {names.get((2, 0x409))!r}")
    check(names.get((6, 0x409)) == f"{family['postscript']}-{weight}", f"{label}: PostScript name")
    check((7, 0x409) not in names, f"{label}: the trademark of BIZ UD is still in the name table")
    for (name_id, _), text in names.items():
        # BIZ UD の名前は、元の著作権表示 (0)・説明 (5・10)・使用許諾の全文 (13。著作権表示を含む) にだけ出る
        if name_id not in (0, 5, 10, 13):
            check("BIZ" not in text, f"{label}: name {name_id} still says {text!r}")
    check(spec.COPYRIGHT in names.get((0, 0x409), ""), f"{label}: our copyright line is missing")
    # フォントのファイルだけで配るので、使用許諾の全文がフォントの中にあること
    license_text = (ROOT / "OFL.txt").read_text(encoding="utf-8").replace("\r\n", "\n").strip()
    check(names.get((13, 0x409)) == license_text, f"{label}: name 13 is not the full text of OFL.txt")
    check(names.get((14, 0x409)) == "https://scripts.sil.org/OFL", f"{label}: name 14 is not the OFL URL")
    check(font["post"].isFixedPitch == 0, f"{label}: still marked as fixed pitch")
    check("DSIG" not in font, f"{label}: the signature of BIZ UD is still there")
    check(f"{font['head'].fontRevision:.3f}" == spec.VERSION, f"{label}: font revision")
    check(font["OS/2"].fsType == 0, f"{label}: embedding is restricted")


def check_license() -> None:
    """OFL.txt の著作権表示が、元のフォントの中の著作権表示 (name ID 0) と同じであること。
    元の配布物の OFL.txt には、BIZ UDゴシックの行に BIZ UD明朝のリポジトリの URL を書いた
    誤りがある。フォントの中の表示を正しいものとして突き合わせる"""
    lines = (ROOT / "OFL.txt").read_text(encoding="utf-8").splitlines()
    for family in spec.FAMILIES:
        notice = TTFont(SOURCES / f"{family['ud']}-Regular.ttf")["name"].getDebugName(0)
        check(notice in lines, f"OFL.txt: the copyright line of {family['source_name']} is not {notice!r}")
    check(spec.COPYRIGHT in lines, "OFL.txt: our copyright line is missing")


def main() -> int:
    check_license()
    for family in spec.FAMILIES:
        for weight in spec.WEIGHTS:
            check_font(family, weight)
    if problems:
        print("\n".join(problems[:50]))
        print(f"{len(problems)} problem(s)")
        return 1
    print(f"ok: {len(spec.FAMILIES) * len(spec.WEIGHTS)} fonts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
