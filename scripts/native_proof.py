"""CoreText / DirectWrite 用の共通資料を作り、実際の OS の描画結果を検査・保存する。

--prepare は Linux でも動く。ネイティブ API の実行には各 OS が必要で、ダミーの結果を
実行済みの証拠として扱わない。JSON の字送りは px (emSize=24)、比較は字形と用字系ごとに行う。
"""

import argparse
import hashlib
import html
import json
from pathlib import Path
import subprocess
import sys
import math
import os
import unicodedata

ROOT = Path(__file__).resolve().parent.parent
# id, language, vertical, kern (-1=default), locl (-1=default), ss03 (-1=default), text
CASES = [
    ("ja", "ja", False, -1, -1, -1, "読書の記号— “本” ‘声’ − 35° ½ ‼ 𠮷野のくの字点〱〲。"),
    ("en", "en", False, -1, -1, -1, "The reader—“Hello,” ‘yes’ − 35° ½ ‼ It’s fine."),
    ("kern", "en", False, 1, -1, -1, "T. T, V. V, W. W, Y. Y, P. P, F. F, r. r, y. y, v. v, w. w,"),
    ("kern-off", "en", False, 0, -1, -1, "T. T, V. V, W. W, Y. Y, P. P, F. F, r. r, y. y, v. v, w. w,"),
    ("accents", "en", False, 1, -1, -1, "Ť. Ť, Ţ. Ţ, Ŷ. Ŷ, Ŵ. Ŵ, ŕ. ŕ, ý. ý, ŵ. ŵ, ÁV Tó"),
    ("always-udp", "ja", False, -1, -1, -1, "文‘’“”—−¼½¾⅓⅔⅕°‼⁇⁈⁉文"),
    ("locl-off", "ja", False, -1, 0, -1, "文‘’“”—−¼½¾⅓⅔⅕°‼⁇⁈⁉文"),
]
CASES += [(name + "-v", lang, True, kern, locl, ss03, text) for name, lang, _, kern, locl, ss03, text in CASES
          if name in ("ja", "en", "always-udp", "locl-off")]
# 縦組の 2 セル・3 セルの字 (〱 〲 ⸺ ⸻)。字 → セルの数。前後に 1 セルずつの仮名を置き、送りの合計を見る
VERTICAL_CELLS = {0x3031: 2, 0x3032: 2, 0x2E3A: 2, 0x2E3B: 3}
CASES += [(f"cell-{code:04x}", "ja", True, -1, -1, -1, f"あ{chr(code)}い") for code in VERTICAL_CELLS]
# ⦅ ⦆ (U+2985・U+2986) と ｟ ｠ (U+FF5F・U+FF60) を同じ並びで組み、同じに出るかを比べる (測るだけ。合否にしない)。
# Unicode の縦の向きは ⦅ ⦆ が R、｟ ｠ が Tr で違うので、環境が違う字形を選ぶことがある (フォントの不具合とは限らない)
WHITE_PARENS = "｟あ｠⦅あ⦆"
CASES += [("paren-h", "ja", False, -1, -1, -1, WHITE_PARENS), ("paren-v", "ja", True, -1, -1, -1, WHITE_PARENS)]
# ss03 (ルビ仮名の試作) を指定して、対象の 194 字を横組・縦組で組む。ss03 を指定しない同じ文字列は、通常の字形の対照
KANA = "".join(chr(c) for start, stop in ((0x3041, 0x3097), (0x30A0, 0x30FC), (0x31F0, 0x3200)) for c in range(start, stop))
CASES += [("ss03", "ja", False, -1, -1, 1, KANA), ("ss03-v", "ja", True, -1, -1, 1, KANA),
          ("ss03-off", "ja", False, -1, -1, 0, KANA), ("ss03-off-v", "ja", True, -1, -1, 0, KANA)]
CASES += [(f"pair-{ord(a):04x}-{ord(b):04x}", "en", False, 1, -1, -1, a + b)
          for a in "TVWYPFryvwŤŢŶŴŕýŵ" for b in ".,"]


def kern_total(font, pairs: dict, text: str, kerned: bool) -> float:
    """text を、cmap の字の hmtx の合計と、GPOS の kern の実効値 (kerned のとき) で組んだ幅 (px)。
    宣言値 (spec) ではなくフォントの表から求めるので、公開済みのフォントにも使える"""
    em, cmap = font["head"].unitsPerEm, font.getBestCmap()
    glyphs = [cmap[ord(c)] for c in text]
    total = sum(font["hmtx"][g][0] for g in glyphs)
    if kerned:
        total += sum(pairs.get(pair, 0) for pair in zip(glyphs, glyphs[1:]))
    return total * 24 / em


def expectations(font) -> dict:
    """フォントの hmtx・cmap・GSUB から求める、実環境の確認の期待値 (字形 ID と px の送り)。
    横組の字は locl の後の字 (BIZ UDP) を取る。縦組の 2 段の置き換えは、環境が使う feature の違いを、
    CoreText = vrt2、DirectWrite = vert として明示する。DirectWrite は ⸺ ⸻ を回さずに cmap の字を横倒しで送る"""
    import spec
    from checks.fonttables import gsub_mapping, gsub_multiple, latin_symbol_mapping
    from checks.fonttables import kerning_pairs
    em, cmap = font["head"].unitsPerEm, font.getBestCmap()
    pairs = kerning_pairs(font)
    locl = latin_symbol_mapping(font, "kana", None)
    gid = font.getGlyphID

    def horizontal(char: str) -> list:
        name = cmap[ord(char)]
        name = locl.get(name, name) if ord(char) in spec.ALWAYS_UDP else name
        return [gid(name), font["hmtx"][name][0] * 24 / em]

    vert, vrt2 = gsub_mapping(font, "vert"), gsub_mapping(font, "vrt2")
    vert_multiple, vrt2_multiple = gsub_multiple(font, "vert"), gsub_multiple(font, "vrt2")

    def sequence(mapping, multiple, char):
        name = mapping.get(cmap[ord(char)], cmap[ord(char)])
        return [gid(n) for n in multiple.get(name, [name])]

    vertical = {}
    for code in VERTICAL_CELLS:
        kana = [gid(cmap[ord(c)]) for c in "あい"]
        vertical[f"{code:04x}"] = {
            "coretext": kana[:1] + sequence(vrt2, vrt2_multiple, chr(code)) + kana[1:],
            "directwrite": kana[:1] + (sequence(vert, vert_multiple, chr(code)) if code in (0x3031, 0x3032)
                                       else [gid(cmap[code])]) + kana[1:],
        }
    kern_text = next(c[-1] for c in CASES if c[0] == "kern")
    # ss03: 横組は cmap の字から ss03 の置き換え先へ、縦組は vert (DirectWrite)・vrt2 (CoreText) の後に ss03。送りは原字と同じ
    ss03 = gsub_mapping(font, "ss03")
    # 期待値はフォントの GSUB から求める。ss03 が一部の仮名だけの版 (1.009 までの 20 字) では、残りは通常の字形が期待値になる
    ss03_horizontal = [[gid(ss03.get(cmap[ord(c)], cmap[ord(c)])), font["hmtx"][cmap[ord(c)]][0] * 24 / em] for c in KANA]

    def ss03_vertical(mapping):
        names = [mapping.get(cmap[ord(c)], cmap[ord(c)]) for c in KANA]
        return [gid(ss03.get(n, n)) for n in names]

    # ⦅ ⦆ と ｟ ｠ の期待値: 横組は cmap の字形と送り、縦組は CoreText = vrt2、DirectWrite = vert の置き換え後の字形 ID (先頭)
    parens = {}
    for char in "｟｠⦅⦆":
        if ord(char) not in cmap:  # ⦅ ⦆ は 1.011 から。公開済みの古い版には無い
            continue
        parens[char] = {"horizontal": [gid(cmap[ord(char)]), font["hmtx"][cmap[ord(char)]][0] * 24 / em],
                        "vertical": {"coretext": sequence(vrt2, vrt2_multiple, char)[0],
                                     "directwrite": sequence(vert, vert_multiple, char)[0]}}

    return {
        "whiteParens": parens,
        "horizontal": {char: horizontal(char) for case in CASES if case[0] in ("ja", "always-udp") for char in case[-1]},
        "kernTotals": {"on": kern_total(font, pairs, kern_text, True), "off": kern_total(font, pairs, kern_text, False)},
        "pairWidths": {name: kern_total(font, pairs, text, True) for name, _, _, _, _, _, text in CASES if name.startswith("pair-")},
        "vertical": vertical,
        "ss03": {"horizontal": ss03_horizontal, "default": [gid(cmap[ord(c)]) for c in KANA],
                 "vertical": {"coretext": ss03_vertical(vrt2), "directwrite": ss03_vertical(vert)},
                 "defaultVertical": {"coretext": [gid(vrt2.get(cmap[ord(c)], cmap[ord(c)])) for c in KANA],
                                     "directwrite": [gid(vert.get(cmap[ord(c)], cmap[ord(c)])) for c in KANA]}},
        "uncovered": sorted({f"{ord(c):04X}" for case in CASES for c in case[-1] if ord(c) not in cmap}),
    }


def prepare(output: Path, fonts_dir: Path = ROOT / "fonts"):
    output.mkdir(parents=True, exist_ok=True)
    (output / "cases.tsv").write_text("".join(
        f"{name}\t{lang}\t{int(vertical)}\t{kern}\t{locl}\t{ss03}\t{text}\n"
        for name, lang, vertical, kern, locl, ss03, text in CASES), encoding="utf-8")
    fonts = sorted(fonts_dir.glob("*.ttf"))
    if len(fonts) != 4:
        raise ValueError("build all four fonts before preparing native proofs")
    # 期待値 (送り・字形 ID・詰め) は、フォントの hmtx・cmap・GSUB・GPOS から求める。ネイティブの組版には依らない。
    # 実環境の字形 ID と送りは、比較のため成果物に残る。
    from fontTools.ttLib import TTFont
    from checks.fonttables import gsub_mapping, gsub_multiple
    font_data = {}
    for path in fonts:
        with TTFont(path) as font:
            em, cmap = font["head"].unitsPerEm, font.getBestCmap()
            # 縦組の 〱 〲 ⸺ ⸻ の、輪郭のある字 (vert の 2 段目の 1 つ目) の字形 ID。位置のずれを見るため
            multiple = gsub_multiple(font, "vert")
            # 2 段の置き換えを持たない版 (1.008 など) では、置き換えた 1 字の ID。長さの検査が外れとして報告する
            vert = gsub_mapping(font, "vert")
            cells = {f"{code:04x}": font.getGlyphID(multiple.get(vert.get(cmap[code], cmap[code]), [vert.get(cmap[code], cmap[code])])[0])
                     for code in VERTICAL_CELLS}
            font_data[path.stem] = {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                    "cellGlyphs": cells, "expected": expectations(font)}
    manifest = {"emSize": 24, "cases": [c[0] for c in CASES], "fonts": font_data}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return fonts


def validate(output: Path, engine: str):
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    for font, data in manifest["fonts"].items():
        for case in manifest["cases"]:
            stem = output / engine / font / case
            record = json.loads(stem.with_suffix(".json").read_text(encoding="utf-8"))
            if record["engine"] != engine or record["sample"] != case or record["emSize"] != 24:
                raise ValueError(f"incorrect metadata: {stem}")
            if record["vertical"] != next(c[2] for c in CASES if c[0] == case):
                raise ValueError(f"incorrect direction: {stem}")
            if not record["runs"]:
                raise ValueError(f"no shaped runs: {stem}")
            for run in record["runs"]:
                if len(run["glyphs"]) != len(run["advances"]) or not run["glyphs"]:
                    raise ValueError(f"missing glyph or advance: {stem}")
                if not all(math.isfinite(v) for advance in run["advances"]
                           for v in (advance if isinstance(advance, list) else [advance])):
                    raise ValueError(f"nonfinite advance: {stem}")
            image = stem.with_suffix(".png").read_bytes()
            if not image.startswith(b"\x89PNG\r\n\x1a\n") or len(image) < 100:
                raise ValueError(f"missing PNG: {stem}")
    print(f"ok: {engine}: {len(manifest['fonts'])} fonts x {len(manifest['cases'])} cases (structure, advances, PNG)")


def check_vertical_cells(output: Path, engine: str):
    """縦組の 〱 〲 ⸺ ⸻ が、セルの数 × 24px (2 em・3 em) で送られ、輪郭のある字が左右にずれていないこと。
    前後の仮名とあわせた全体の送りで見る。DirectWrite はレイアウトの縦の長さ (extent)、CoreText は最初と最後の
    字の位置の差。外れた項目の一覧を返す (失敗にするのは report)"""
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    problems = []
    for font, data in manifest["fonts"].items():
        for code, cells in VERTICAL_CELLS.items():
            case = f"cell-{code:04x}"
            record = json.loads((output / engine / font / f"{case}.json").read_text(encoding="utf-8"))
            runs = record["runs"]
            if engine == "directwrite":
                total, want = record["extent"][1], (cells + 2) * 24
                # 輪郭のある字は、左右にずらして置かない (ascenderOffset が 0)
                cell = data["cellGlyphs"][f"{code:04x}"]
                shifted = [o for r in runs for g, o in zip(r["glyphs"], r["offsets"]) if g == cell and abs(o[1]) > .01]
            else:
                positions = [p for r in runs for p in r["positions"]]
                total, want = abs(positions[-1][1] - positions[0][1]) + 24, (cells + 2) * 24
                shifted = []
            if abs(total - want) > .5 or shifted:
                problems.append(f"{engine} {font} U+{code:04X}: length {total:g}px, expected {want}px" + (", glyph shifted sideways" if shifted else ""))
    if not problems:
        print(f"ok: {engine}: U+3031 U+3032 U+2E3A U+2E3B are {', '.join(str(c) for c in VERTICAL_CELLS.values())} em in vertical text")
    return problems


# 環境ごとに分かっている挙動。期待値はフォントから求め、環境で違う点だけをここに書く
# kernOffApplies: kern=0 の指定で詰めが外れるか。DirectWrite は SetPairKerning(false) を指定しても詰めたまま (2026-11-16 の観測)
ENGINE_BEHAVIOR = {"coretext": {"kernOffApplies": True}, "directwrite": {"kernOffApplies": False}}


def flatten(record: dict) -> list:
    """run をまたいで、字ごとの (字形 ID, 送りの px)。CoreText の送りは [幅, 高さ] で、幅 (横組の送り) を取る"""
    items = []
    for run in record["runs"]:
        for glyph, advance in zip(run["glyphs"], run["advances"]):
            if isinstance(advance, list):
                advance = advance[0]
            items.append((glyph, advance))
    return items


def check_expectations(output: Path, engine: str) -> list[str]:
    """フォントから求めた期待値 (manifest の expected) と、実環境の結果を比べる。外れた項目を全部集めて返す。
    項目: フォールバックと欠落グリフ、句読点のペアの幅、17 字の字幅と字形 (横組)、カーニング (宣言した詰めの合計)、追加字 (𠮷 〱 〲) の字形と送り、
    縦組の 〱 〲 ⸺ ⸻ の字形の並び、確認文のすべての字がこのフォントにあること"""
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    behavior, problems = ENGINE_BEHAVIOR[engine], []

    def record(font, case):
        return json.loads((output / engine / font / f"{case}.json").read_text(encoding="utf-8"))

    for font, data in manifest["fonts"].items():
        expected = data["expected"]
        label = f"{engine} {font}"
        if expected["uncovered"]:
            problems.append(f"{label}: characters missing from the font: U+{', U+'.join(expected['uncovered'])}")
        # DirectWrite は GetFilePathFromKey が大文字のファイル名を返すことがある (別のフォントではない)
        own = {font.casefold(), data["file"].casefold()}
        for case in manifest["cases"]:
            if case.startswith("paren-"):
                continue  # 測るだけ。white_parens が記録する
            text = next(c[-1] for c in CASES if c[0] == case)
            result = record(font, case)
            flat = flatten(result)
            chars = list(text) if len(flat) == len(text) else [f"glyph#{i}" for i in range(len(flat))]
            index = 0
            for number, run in enumerate(result["runs"]):
                if run["font"].casefold() not in own:
                    problems.append(f"{label} {case}: run {number} (glyphs {index}-{index + len(run['glyphs']) - 1}, "
                                    f"{''.join(chars[index:index + len(run['glyphs'])])!r}) fell back to {run['font']}")
                for offset, glyph in enumerate(run["glyphs"]):
                    if glyph == 0:
                        char = chars[index + offset]
                        problems.append(f"{label} {case}: missing glyph (.notdef) for {char if char.startswith('glyph#') else 'U+%04X' % ord(char)}")
                index += len(run["glyphs"])
            if case in expected["pairWidths"]:
                actual = sum(a for _, a in flat)
                if abs(actual - expected["pairWidths"][case]) > .02:
                    problems.append(f"{label} {case}: width {actual:.3f}px, expected {expected['pairWidths'][case]:.3f}px (GPOS kern)")
        for case in ("always-udp", "ja"):
            text = next(c[-1] for c in CASES if c[0] == case)
            actual = flatten(record(font, case))
            if len(actual) != len(text):
                problems.append(f"{label} {case}: {len(actual)} glyphs for {len(text)} characters")
                continue
            for char, (glyph, advance) in zip(text, actual):
                if char not in expected["horizontal"]:
                    continue
                want_glyph, want_advance = expected["horizontal"][char]
                if glyph != want_glyph or abs(advance - want_advance) > .02:
                    problems.append(f"{label} {case} U+{ord(char):04X}: glyph {glyph} advance {advance:g}px, expected glyph {want_glyph} advance {want_advance:g}px")
        for case, kerned in (("kern", True), ("kern-off", False)):
            total = sum(a for _, a in flatten(record(font, case)))
            want = expected["kernTotals"]["on" if kerned or not behavior["kernOffApplies"] else "off"]
            if abs(total - want) > .05:
                problems.append(f"{label} {case}: width {total:.3f}px, expected {want:.3f}px")
        for code in VERTICAL_CELLS:
            want = expected["vertical"][f"{code:04x}"][engine]
            actual = [g for g, _ in flatten(record(font, f"cell-{code:04x}"))]
            if actual != want:
                problems.append(f"{label} cell-{code:04x}: glyphs {actual}, expected {want}")
        # ss03: フォントの ss03 の置き換えどおり (今の版は 194 字すべて) の試作字形になり、送りは原字と同じ。ss03=0 の対照は通常の字形のまま (縦組は字形だけ見る)
        want = expected["ss03"]
        for case, vertical, trial in (("ss03", False, True), ("ss03-off", False, False), ("ss03-v", True, True), ("ss03-off-v", True, False)):
            actual = flatten(record(font, case))
            if len(actual) != len(KANA):
                problems.append(f"{label} {case}: {len(actual)} glyphs for {len(KANA)} characters")
                continue
            if vertical:
                wanted = want["vertical"][engine] if trial else want["defaultVertical"][engine]
            else:
                wanted = [g for g, _ in want["horizontal"]] if trial else want["default"]
            bad = [(char, got, glyph) for char, (got, _), glyph in zip(KANA, actual, wanted) if got != glyph]
            if bad:
                problems.append(f"{label} {case}: {len(bad)} of {len(KANA)} kana differ, e.g. U+{ord(bad[0][0]):04X} glyph {bad[0][1]}, expected {bad[0][2]}")
            if not vertical and trial:
                moved = [char for char, (_, advance), (_, width) in zip(KANA, actual, want["horizontal"]) if abs(advance - width) > .02]
                if moved:
                    problems.append(f"{label} {case}: advance differs from the original kana for {len(moved)} kana, e.g. U+{ord(moved[0]):04X}")
    return problems


def white_parens(output: Path, engine: str) -> list[str]:
    """⦅ ⦆ と ｟ ｠ を同じ並びで組んだ結果 (paren-h・paren-v) を比べて white-parens-<engine>.json に残し、行を返す。
    合否にしない (測るだけ)。見るもの: 字形 ID・送り (px)・代わりのフォントになっていないか、⦅ が ｟ と、⦆ が ｠ と同じか、
    フォントから求めた期待の字形 (横組は cmap、縦組は vrt2・vert の置き換え後) と合うか。縦組の送りは、CoreText は高さ、DirectWrite はそのまま"""
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    out, lines = {}, []
    for font, data in manifest["fonts"].items():
        expected = data["expected"]["whiteParens"]
        out[font] = {}
        for case, vertical in (("paren-h", False), ("paren-v", True)):
            result = json.loads((output / engine / font / f"{case}.json").read_text(encoding="utf-8"))
            items = []
            for run in result["runs"]:
                for glyph, advance in zip(run["glyphs"], run["advances"]):
                    if isinstance(advance, list):
                        advance = abs(advance[1] if vertical else advance[0])
                    items.append({"glyph": glyph, "advance": round(advance, 3), "font": run["font"]})
            entry = {"text": WHITE_PARENS, "items": items}
            if len(items) != len(WHITE_PARENS):
                entry["note"] = f"{len(items)} glyphs for {len(WHITE_PARENS)} characters; not compared"
                lines.append(f"{engine} {font} {case}: {entry['note']}")
                out[font][case] = entry
                continue
            pairs = {}
            for plain, white, index in (("｟", "⦅", 3), ("｠", "⦆", 5)):
                a, b = items[WHITE_PARENS.index(plain)], items[index]
                want = None  # フォントに無い字 (古い版の ⦅ ⦆) は期待の字形なし。字形 0 (.notdef) か代わりのフォントで現れる
                if white in expected:
                    want = expected[white]["vertical"][engine] if vertical else expected[white]["horizontal"][0]
                pairs[f"{white} vs {plain}"] = {
                    "sameGlyph": a["glyph"] == b["glyph"], "sameAdvance": abs(a["advance"] - b["advance"]) <= .02,
                    "glyphs": [a["glyph"], b["glyph"]], "advances": [a["advance"], b["advance"]],
                    "expectedGlyph": want, "whiteMatchesExpected": b["glyph"] == want,
                    "fellBack": [a["font"], b["font"]] if a["font"] != b["font"] or b["glyph"] == 0 else None}
                lines.append(f"{engine} {font} {case} U+{ord(white):04X} vs U+{ord(plain):04X}: glyph {b['glyph']} vs {a['glyph']}, "
                             f"advance {b['advance']:g}px vs {a['advance']:g}px, expected glyph {want}"
                             + ("" if pairs[f"{white} vs {plain}"]["sameGlyph"] and pairs[f"{white} vs {plain}"]["sameAdvance"] else "  <-- differs"))
            entry["pairs"] = pairs
            out[font][case] = entry
    (output / f"white-parens-{engine}.json").write_text(json.dumps({"engine": engine, "advisory": True, "results": out}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return lines


def report(output: Path, engine: str, problems: list[str]):
    """検査の結果を JSON に残し、外れた項目を全部出す。すべて合格なら True (失敗の扱いは呼び出し側)"""
    (output / f"checks-{engine}.json").write_text(json.dumps({"engine": engine, "problems": problems}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for line in problems:
        print(f"::error::{line}" if os.environ.get("GITHUB_ACTIONS") else f"FAIL {line}")
    if problems:
        print(f"{len(problems)} native check(s) failed ({engine}); see checks-{engine}.json")
    else:
        print(f"ok: {engine}: expectations (17 symbols, kerning, added characters, vertical glyphs, ss03, coverage)")
    return not problems


def gallery(output: Path, engine: str):
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    rows = ["<!doctype html><meta charset=utf-8><title>Native shaping proofs</title>",
            "<style>img{max-width:100%;border:1px solid #ccc}table{border-collapse:collapse}td{padding:6px;border:1px solid #ccc}</style>",
            f"<h1>{engine}</h1><p>24px. Compare kern / kern-off and always-udp / locl-off, then compare the two OS artifacts with matching font SHA-256. JSON preserves glyph IDs and advances; locl-off is a diagnostic, not a passing requirement.</p>"]
    for font, data in manifest["fonts"].items():
        rows += [f"<h2>{font}</h2><p>SHA-256 {data['sha256']}</p>"]
        for name, lang, vertical, kern, locl, ss03, text in CASES:
            prefix = f"{engine}/{font}/{name}"
            rows += [f"<h3>{name} ({lang}, {'vertical' if vertical else 'horizontal'})</h3>",
                     f"<p>{html.escape(text)} <a href='{prefix}.json'>glyphs / advances</a></p>",
                     f"<img alt='{html.escape(text, quote=True)}' src='{prefix}.png'>"]
    (output / "index.html").write_text("\n".join(rows), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--validate", choices=("coretext", "directwrite"))
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "native")
    parser.add_argument("--renderer", type=Path)
    parser.add_argument("--fonts", type=Path, default=ROOT / "fonts",
                        help="確かめる 4 つの TTF のフォルダー (既定は fonts。公開済みのリリースのフォントを確かめるときに指定する)")
    args = parser.parse_args()
    if args.validate:
        validate(args.output, args.validate)
        print("\n".join("INFO white-parens " + line for line in white_parens(args.output, args.validate)))
        return 0 if report(args.output, args.validate, check_vertical_cells(args.output, args.validate)
                           + check_expectations(args.output, args.validate)) else 1
    fonts = prepare(args.output, args.fonts)
    if args.prepare:
        print(f"prepared: {len(fonts)} fonts x {len(CASES)} cases")
        return 0
    engine = {"darwin": "coretext", "win32": "directwrite"}.get(sys.platform)
    if engine is None or args.renderer is None:
        parser.error("native rendering requires macOS/Windows and --renderer")
    for font in fonts:
        family = "Dokusho UD " + ("Mincho" if "Mincho" in font.stem else "Gothic")
        target = args.output / engine / font.stem
        target.mkdir(parents=True, exist_ok=True)
        subprocess.run([str(args.renderer.resolve()), str(font.resolve()), str((args.output / "cases.tsv").resolve()),
                        str(target.resolve()), family, "Bold" if "Bold" in font.stem else "Regular"], check=True)
    validate(args.output, engine)
    gallery(args.output, engine)
    print("\n".join("INFO white-parens " + line for line in white_parens(args.output, engine)))
    return 0 if report(args.output, engine, check_vertical_cells(args.output, engine)
                       + check_expectations(args.output, engine)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
