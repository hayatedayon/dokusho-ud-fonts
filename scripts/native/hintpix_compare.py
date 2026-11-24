"""hintpix.exe が書いた JSON (小さい字の画素) を、公開済みのリリースのフォントとビルドしたフォントで比べる。標準ライブラリだけ。

    python scripts/native/hintpix_compare.py <リリースの JSON のディレクトリ> <ビルドの JSON のディレクトリ> <出力の JSON>

字 (code)・描き方 (mode)・大きさ (ppem) ごとに、ClearType の 3x1 の画素の濃さの合計 (ink) とその差、画素が違う数を出す。
同じ名前の JSON (書体ごと) だけを比べる。画素が違う字だけが、ビルドで変わった字 (斜線の濃さを保つ命令の字) のはず。
"""
import json
import sys
from pathlib import Path


def load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {(g["mode"], g["code"], g["ppem"]): g for g in data["glyphs"]}


def ink(glyph: dict) -> int:
    return sum(glyph["alpha"])


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    release_dir, build_dir, output = Path(argv[1]), Path(argv[2]), Path(argv[3])
    summary: dict = {}
    for release_path in sorted(release_dir.glob("*.json")):
        build_path = build_dir / release_path.name
        if not build_path.exists():
            raise SystemExit(f"{build_path} is missing")
        release, build = load(release_path), load(build_path)
        if release.keys() != build.keys():
            raise SystemExit(f"{release_path.name}: the rendered cases differ")
        rows = []
        for key in sorted(release):
            before, after = release[key], build[key]
            same_bounds = before["bounds"] == after["bounds"]
            differ = sum(a != b for a, b in zip(before["alpha"], after["alpha"])) if same_bounds and len(before["alpha"]) == len(after["alpha"]) else -1
            rows.append({"mode": key[0], "code": key[1], "ppem": key[2], "ink_release": ink(before), "ink_build": ink(after),
                         "same_bounds": same_bounds, "differing_subpixels": differ})
        summary[release_path.stem] = rows
        changed = sorted({row["code"] for row in rows if row["differing_subpixels"] != 0})
        print(f"{release_path.stem}: {len(rows)} cases, changed codes {[f'U+{code:04X}' for code in changed]}")
    output.write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
