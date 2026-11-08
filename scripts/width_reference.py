"""公開版の hwid/fwid を独立した基準にする。フォント生成コードは使わない。

python3 scripts/width_reference.py record /path/to/v1.0.6 tests/fixtures/widths-1.006.json
python3 scripts/width_reference.py compare /path/to/v1.0.6

固定データは公開版の記号・空白・幅変換の入力を対象に、送りと字形・配置のハッシュを持つ。
compare は参照フォントに収録された全コードポイントの送りを直接比較する。
"""

import argparse
from collections import Counter
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import unicodedata

from fontTools.ttLib import TTFont

from harfbuzz_shape import Shaper

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "widths-1.006.json"
FILES = tuple(f"DokushoUD{family}-{weight}.ttf" for family in ("Mincho", "Gothic") for weight in ("Regular", "Bold"))


def cases():
    for language in ("ja", "en"):
        for tag in ("hwid", "fwid"):
            for vertical in (False, True):
                yield f"{language}/{tag}/{'vertical' if vertical else 'horizontal'}", language, tag, vertical


def shape(shaper, code, language, tag, vertical):
    return shaper.shape(chr(code), language, vertical, ("kern=0", "ss01=0", "ss02=0", "ss03=0", tag))


def snapshot(font, shaper, codes, language, tag, vertical, geometry):
    advances, drawings = [], []
    order = font.getGlyphOrder()
    for code in codes:
        shaped = shape(shaper, code, language, tag, vertical)
        advances.append(sum(row[3 if vertical else 2] for row in shaped))
        drawing = []
        for gid, _cluster, *position in shaped:
            if gid not in geometry:
                coordinates, ends, flags = font["glyf"][order[gid]].getCoordinates(font["glyf"])
                data = [list(coordinates), list(ends), [flag & 1 for flag in flags]]
                geometry[gid] = hashlib.sha256(json.dumps(data, separators=(",", ":")).encode()).hexdigest()
            drawing.append([geometry[gid], *position])
        drawings.append(drawing)
    digest = hashlib.sha256(json.dumps(drawings, separators=(",", ":")).encode()).hexdigest()
    return advances, digest


def record(reference: Path, output: Path):
    data = {"version": "1.006", "codepoints": None, "files": {}}
    for name in FILES:
        path = reference / name
        font, shaper = TTFont(path), Shaper(path)
        if f"{font['head'].fontRevision:.3f}" != data["version"]:
            raise SystemExit(f"{name}: expected published version {data['version']}")
        gsub = font["GSUB"].table
        if {record.FeatureTag for record in gsub.FeatureList.FeatureRecord} & {"ss01", "ss02", "ss03"}:
            raise SystemExit(f"{name}: expected the published 1.006, not an unreleased development build")
        indexes = {i for r in gsub.FeatureList.FeatureRecord if r.FeatureTag in ("hwid", "fwid")
                   for i in r.Feature.LookupListIndex}
        inputs = {key for i in indexes for raw in gsub.LookupList.Lookup[i].SubTable
                  for key in getattr(getattr(raw, "ExtSubTable", raw), "mapping", {})}
        codes = sorted(code for code, glyph in font.getBestCmap().items()
                       if glyph in inputs or unicodedata.category(chr(code))[0] in "PSZ")
        if data["codepoints"] is None:
            data["codepoints"] = codes
        if codes != data["codepoints"]:
            raise SystemExit(f"{name}: reference character coverage differs")
        entry = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "cases": {}}
        geometry = {}
        for key, language, tag, vertical in cases():
            advances, digest = snapshot(font, shaper, codes, language, tag, vertical, geometry)
            default = Counter(advances).most_common(1)[0][0]
            entry["cases"][key] = {
                "default_advance": default,
                "advances": {str(code): advance for code, advance in zip(codes, advances) if advance != default},
                "shaping_sha256": digest,
            }
        data["files"][name] = entry
        shaper.close()
        font.close()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"{output}: {len(data['codepoints'])} characters × 8 cases × {len(FILES)} fonts")


@lru_cache(maxsize=1)
def load():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def check_recorded(name, font, shaper):
    data = load()
    problems, geometry = [], {}
    for key, language, tag, vertical in cases():
        expected = data["files"][name]["cases"][key]
        advances, digest = snapshot(font, shaper, data["codepoints"], language, tag, vertical, geometry)
        wrong = [(f"U+{code:04X}", expected["advances"].get(str(code), expected["default_advance"]), actual)
                 for code, actual in zip(data["codepoints"], advances)
                 if actual != expected["advances"].get(str(code), expected["default_advance"])]
        if wrong:
            problems.append(f"{name}: {key}: {len(wrong)} advances differ from published 1.006: {wrong[:6]}")
        if digest != expected["shaping_sha256"]:
            problems.append(f"{name}: {key}: glyph outlines or positioning differ from published 1.006")
    return problems


def compare(reference: Path, current: Path) -> int:
    total, differences = 0, 0
    for name in FILES:
        if hashlib.sha256((reference / name).read_bytes()).hexdigest() != load()["files"][name]["sha256"]:
            raise SystemExit(f"{name}: reference file does not match the recorded published 1.006 SHA-256")
        old_font, new_font = TTFont(reference / name), TTFont(current / name)
        old, new = Shaper(reference / name), Shaper(current / name)
        codes = sorted(old_font.getBestCmap())
        missing = set(codes) - new_font.getBestCmap().keys()
        if missing:
            raise SystemExit(f"{name}: {len(missing)} published characters missing")
        for key, language, tag, vertical in cases():
            wrong = []
            for code in codes:
                a = shape(old, code, language, tag, vertical)
                b = shape(new, code, language, tag, vertical)
                before, after = tuple(sum(r[i] for r in a) for i in (2, 3)), tuple(sum(r[i] for r in b) for i in (2, 3))
                if before != after:
                    wrong.append((f"U+{code:04X}", before, after))
            print(f"{name} {key}: {len(wrong)} / {len(codes)} differ" + (f"; {wrong[:5]}" if wrong else ""))
            total += len(codes)
            differences += len(wrong)
        old.close()
        new.close()
        old_font.close()
        new_font.close()
    print(f"published 1.006: {differences} differences in {total} single-character width cases")
    return int(bool(differences))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("record")
    capture.add_argument("reference", type=Path)
    capture.add_argument("output", type=Path)
    comparison = commands.add_parser("compare")
    comparison.add_argument("reference", type=Path)
    comparison.add_argument("--fonts", type=Path, default=ROOT / "fonts")
    args = parser.parse_args()
    if args.command == "record":
        record(args.reference, args.output)
        return 0
    return compare(args.reference, args.fonts)


if __name__ == "__main__":
    raise SystemExit(main())
