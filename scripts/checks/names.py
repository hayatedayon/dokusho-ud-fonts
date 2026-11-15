"""ライセンスと name 表・版・OS/2 の範囲。"""

from fontTools.ttLib import TTFont

import spec

from .common import FontContext, ROOT, SOURCES, check


def check_license() -> None:
    """OFL.txt の著作権表示が、元のフォントの中の著作権表示 (name ID 0) と同じであること。
    元の配布物の OFL.txt には、BIZ UDゴシックの行に BIZ UD明朝のリポジトリの URL を書いた
    誤りがある。フォントの中の表示を正しいものとして突き合わせる"""
    lines = (ROOT / "OFL.txt").read_text(encoding="utf-8").splitlines()
    for family in spec.FAMILIES:
        notice = TTFont(SOURCES / f"{family['ud']}-Regular.ttf")["name"].getDebugName(0)
        check(notice in lines, f"OFL.txt: the copyright line of {family['source_name']} is not {notice!r}")
    check(spec.COPYRIGHT in lines, "OFL.txt: our copyright line is missing")


def check_name_table(ctx: FontContext) -> None:
    """name 表 (名前・版・著作権・使用許諾) と post・DSIG・head・OS/2 の範囲。"""
    label = ctx.label
    family = ctx.family
    weight = ctx.weight
    font = ctx.font
    ud = ctx.ud
    udp = ctx.udp
    names = {(r.nameID, r.langID): r.toUnicode() for r in font["name"].names}
    check(names.get((1, 0x409)) == family["name_en"], f"{label}: English family name {names.get((1, 0x409))!r}")
    check(names.get((1, 0x411)) == family["name_ja"], f"{label}: Japanese family name {names.get((1, 0x411))!r}")
    check(names.get((2, 0x409)) == weight, f"{label}: style name {names.get((2, 0x409))!r}")
    check(names.get((6, 0x409)) == f"{family['postscript']}-{weight}", f"{label}: PostScript name")
    check((7, 0x409) not in names, f"{label}: the trademark of BIZ UD is still in the name table")
    # 版の表記 (5) が、元のフォントの版 ("Version 1.05" など) を正しく書くこと
    based_on = [f"{source['name'].getDebugName(1)} {source['name'].getDebugName(5).split()[1]}" for source in (ud, udp)]
    check(names.get((5, 0x409)) == f"Version {spec.VERSION}; based on {based_on[0]} and {based_on[1]}",
          f"{label}: name 5 is {names.get((5, 0x409))!r}, not based on {based_on}")
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
    # BIZ UD の範囲に、追加した数字の bit 32 だけを加える。
    ranges = ("ulUnicodeRange1", "ulUnicodeRange2", "ulUnicodeRange3", "ulUnicodeRange4")
    check([getattr(font["OS/2"], a) for a in ranges]
          == [ud["OS/2"].ulUnicodeRange1, ud["OS/2"].ulUnicodeRange2 | 1, ud["OS/2"].ulUnicodeRange3, ud["OS/2"].ulUnicodeRange4],
          f"{label}: OS/2 Unicode ranges are not those of BIZ UD plus bit 32")
    check(bool(font["OS/2"].ulUnicodeRange2 & 1), f"{label}: OS/2 bit 32 (Superscripts And Subscripts) is not set")
