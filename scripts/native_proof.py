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
import unicodedata

ROOT = Path(__file__).resolve().parent.parent
# id, language, vertical, kern (-1=default), locl (-1=default), text
CASES = [
    ("ja", "ja", False, -1, -1, "読書の記号— “本” ‘声’ − 35° ½ ‼ 𠮷野のくの字点〱〲。"),
    ("en", "en", False, -1, -1, "The reader—“Hello,” ‘yes’ − 35° ½ ‼ It’s fine."),
    ("kern", "en", False, 1, -1, "T. T, V. V, W. W, Y. Y, P. P, F. F, r. r, y. y, v. v, w. w,"),
    ("kern-off", "en", False, 0, -1, "T. T, V. V, W. W, Y. Y, P. P, F. F, r. r, y. y, v. v, w. w,"),
    ("accents", "en", False, 1, -1, "Ť. Ť, Ţ. Ţ, Ŷ. Ŷ, Ŵ. Ŵ, ŕ. ŕ, ý. ý, ŵ. ŵ, ÁV Tó"),
    ("always-udp", "ja", False, -1, -1, "文‘’“”—−¼½¾⅓⅔⅕°‼⁇⁈⁉文"),
    ("locl-off", "ja", False, -1, 0, "文‘’“”—−¼½¾⅓⅔⅕°‼⁇⁈⁉文"),
]
CASES += [(name + "-v", lang, True, kern, locl, text) for name, lang, _, kern, locl, text in CASES
          if name in ("ja", "en", "always-udp", "locl-off")]
# 縦組の 2 セル・3 セルの字 (〱 〲 ⸺ ⸻)。字 → セルの数。前後に 1 セルずつの仮名を置き、送りの合計を見る
VERTICAL_CELLS = {0x3031: 2, 0x3032: 2, 0x2E3A: 2, 0x2E3B: 3}
CASES += [(f"cell-{code:04x}", "ja", True, -1, -1, f"あ{chr(code)}い") for code in VERTICAL_CELLS]
CASES += [(f"pair-{ord(a):04x}-{ord(b):04x}", "en", False, 1, -1, a + b)
          for a in "TVWYPFryvwŤŢŶŴŕýŵ" for b in ".,"]


def prepare(output: Path):
    output.mkdir(parents=True, exist_ok=True)
    (output / "cases.tsv").write_text("".join(
        f"{name}\t{lang}\t{int(vertical)}\t{kern}\t{locl}\t{text}\n"
        for name, lang, vertical, kern, locl, text in CASES), encoding="utf-8")
    fonts = sorted((ROOT / "fonts").glob("*.ttf"))
    if len(fonts) != 4:
        raise ValueError("build all four fonts before preparing native proofs")
    # Pair widths come from the declarative specification and unchanged cmap metrics,
    # independently of native shaping. Native IDs remain in the artifacts for comparison.
    from fontTools.ttLib import TTFont
    from checks.fonttables import gsub_mapping, gsub_multiple
    import kerning
    font_data = {}
    for path in fonts:
        with TTFont(path) as font:
            em, cmap = font["head"].unitsPerEm, font.getBestCmap()
            family = "Mincho" if "Mincho" in path.stem else "Gothic"
            widths = {}
            for name, lang, vertical, kern, locl, text in CASES:
                if not name.startswith("pair-"):
                    continue
                base = unicodedata.normalize("NFD", text[0])[0]
                amount = next((kerning.adjustment(em, family, m, g) for a, b, m, g in kerning.PAIRS
                               if base in a and text[1] in b), 0)
                if text[0] in kerning.EXCLUDED_LEFT:
                    amount = 0
                widths[name] = (sum(font["hmtx"][cmap[ord(c)]][0] for c in text) + amount) * 24 / em
            # 縦組の 〱 〲 ⸺ ⸻ の、輪郭のある字 (vert の 2 段目の 1 つ目) の字形 ID。位置のずれを見るため
            multiple = gsub_multiple(font, "vert")
            cells = {f"{code:04x}": font.getGlyphID(multiple[gsub_mapping(font, "vert")[cmap[code]]][0])
                     for code in VERTICAL_CELLS}
            font_data[path.stem] = {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                    "pairWidths": widths, "cellGlyphs": cells}
    manifest = {"emSize": 24, "cases": [c[0] for c in CASES], "fonts": font_data}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return fonts


def validate(output: Path, engine: str):
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    for font, data in manifest["fonts"].items():
        # DirectWrite may return an uppercase filename from GetFilePathFromKey.
        expected_fonts = {font.casefold(), data["file"].casefold()}
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
                if run["font"].casefold() not in expected_fonts:
                    raise ValueError(f"font fallback in {stem}: {run['font']}")
                if not run["glyphs"] or 0 in run["glyphs"] or len(run["glyphs"]) != len(run["advances"]):
                    raise ValueError(f"missing glyph or advance: {stem}")
                if not all(math.isfinite(v) for advance in run["advances"]
                           for v in (advance if isinstance(advance, list) else [advance])):
                    raise ValueError(f"nonfinite advance: {stem}")
            if case in data.get("pairWidths", {}):
                actual = sum(math.hypot(*a) if isinstance(a, list) else a
                             for r in record["runs"] for a in r["advances"])
                if abs(actual - data["pairWidths"][case]) > .02:
                    raise ValueError(f"declared pair width differs in {stem}: {actual} vs {data['pairWidths'][case]}")
            image = stem.with_suffix(".png").read_bytes()
            if not image.startswith(b"\x89PNG\r\n\x1a\n") or len(image) < 100:
                raise ValueError(f"missing PNG: {stem}")
    print(f"ok: {engine}: {len(manifest['fonts'])} fonts x {len(manifest['cases'])} cases (glyphs, advances, PNG)")


def check_vertical_cells(output: Path, engine: str):
    """縦組の 〱 〲 ⸺ ⸻ が、セルの数 × 24px (2 em・3 em) で送られ、輪郭のある字が左右にずれていないこと。
    前後の仮名とあわせた全体の送りで見る。DirectWrite はレイアウトの縦の長さ (extent)、CoreText は最初と最後の
    字の位置の差。補助の確認なので、外れても止めずに全部を調べてから、まとめて失敗にする"""
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
    if problems:
        raise ValueError("vertical cells differ from the expected length:\n" + "\n".join(problems))
    print(f"ok: {engine}: U+3031 U+3032 U+2E3A U+2E3B are {', '.join(str(c) for c in VERTICAL_CELLS.values())} em in vertical text")


def gallery(output: Path, engine: str):
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    rows = ["<!doctype html><meta charset=utf-8><title>Native shaping proofs</title>",
            "<style>img{max-width:100%;border:1px solid #ccc}table{border-collapse:collapse}td{padding:6px;border:1px solid #ccc}</style>",
            f"<h1>{engine}</h1><p>24px. Compare kern / kern-off and always-udp / locl-off, then compare the two OS artifacts with matching font SHA-256. JSON preserves glyph IDs and advances; locl-off is a diagnostic, not a passing requirement.</p>"]
    for font, data in manifest["fonts"].items():
        rows += [f"<h2>{font}</h2><p>SHA-256 {data['sha256']}</p>"]
        for name, lang, vertical, kern, locl, text in CASES:
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
    args = parser.parse_args()
    if args.validate:
        validate(args.output, args.validate)
        check_vertical_cells(args.output, args.validate)
        return 0
    fonts = prepare(args.output)
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
    check_vertical_cells(args.output, engine)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
