"""字の向き・位置の取り違えを、横組と縦組の両方で検出する。check.py が使う。

python3 scripts/glyph_reference.py record NotoSerifCJK-Regular.ttc NotoSansCJK-Regular.ttc   # 基準を記録し直す
python3 scripts/glyph_reference.py audit fonts/DokushoUDMincho-Regular.ttf Mincho            # 1 書体を調べる

基準の tests/fixtures/glyph-reference.json は Noto CJK JP の字の低解像度の形と位置で、フォント生成コードに依存しない。
CI は Noto を入れず、この固定データと比べる (Noto の版の更新で結果が変わらない)。

- 向き: 全字で、そのままより反転・回転した形のほうが基準に近い字を検出する
- 位置: BIZ UD・BIZ UDP と同じ字はデザインの差なので除き、読書 UD で作った・変えた字だけ比べる
- vrt2: 欧字の横倒しの字が、横組の字を右へ 90 度回した形であること
- 数字: 上付き・下付き・分数・tnum・hwid などの出力が、横組・縦組とも同じ数字の形であること
"""

import argparse
import json
import sys
import unicodedata
from functools import lru_cache
from pathlib import Path

from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont

from harfbuzz_shape import Shaper

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "glyph-reference.json"
GRID = 16
SAMPLES = 3
MARGIN = 0.20  # そのままより、この差以上に他の向きが近ければ疑う (書体デザインの差は小さい)
POSITION = 0.25  # em
THIN = 0.03  # em。細い線だけの字は、形を正規化できないので比べない

# 基準と向きが違うと分かっていて、読書 UD の変更ではない字 (コードポイント, 向き)
KNOWN_ORIENTATION = {
    # 罫線: BIZ UD は縦組で回さず、Noto は回す
    **{(code, "v"): "BIZ UD は縦組で回さない罫線" for code in (0x250C, 0x2510, 0x2514, 0x2518, 0x250F, 0x2513, 0x2517, 0x251B)},
}
# 縦組の引用符は意図してミニュートの形にしてある。check.py の check_vertical_minutes が別に検査する
for _code in (0x201C, 0x201D, 0x2018, 0x2019):
    KNOWN_ORIENTATION[(_code, "v")] = "ミニュートの形"
# 細かいデザインの差で向きの判定が揺れる字
DESIGN = {0x03C6, 0x03C7, 0x03C8, 0x21E8, 0x30CF, 0x31F5}
# Noto は縦組の ⸺ ⸻ の送りが 1 em のままで、位置が比較にならない
KNOWN_POSITION = {0x2E3A, 0x2E3B}
# 縦組の引用符は 〝 〟 の位置に置く (Noto の “ ” ‘ ’ は列の中央)
KNOWN_VERTICAL_POSITION = {0x2018, 0x2019, 0x201C, 0x201D}

DIGIT_FEATURES = ("sups", "subs", "sinf", "numr", "dnom", "tnum", "hwid", "fwid")


class _Flatten(BasePen):
    def __init__(self, glyphs):
        super().__init__(glyphs)
        self.contours = []

    def _moveTo(self, point):
        self.contours.append([point])

    def _lineTo(self, point):
        self.contours[-1].append(point)

    def _curveToOne(self, a, b, c):
        p = self._getCurrentPoint()
        for i in range(1, 11):
            t, u = i / 10, 1 - i / 10
            self.contours[-1].append(tuple(u**3 * p[k] + 3 * u * u * t * a[k] + 3 * u * t * t * b[k] + t**3 * c[k] for k in (0, 1)))

    def _qCurveToOne(self, a, c):
        p = self._getCurrentPoint()
        for i in range(1, 11):
            t, u = i / 10, 1 - i / 10
            self.contours[-1].append(tuple(u * u * p[k] + 2 * u * t * a[k] + t * t * c[k] for k in (0, 1)))


class Face:
    def __init__(self, path, number=None):
        self.font = TTFont(path, fontNumber=number) if number is not None else TTFont(path)
        self.shaper = Shaper(path)
        self.glyphs = self.font.getGlyphSet()
        self.order = self.font.getGlyphOrder()
        self.em = self.font["head"].unitsPerEm
        self.cmap = self.font.getBestCmap()
        self._outlines = {}
        self._masks = {}

    def outline(self, gid):
        if gid not in self._outlines:
            pen = _Flatten(self.glyphs)
            self.glyphs[self.order[gid]].draw(pen)
            self._outlines[gid] = [[(x / self.em, y / self.em) for x, y in c] for c in pen.contours if len(c) > 2]
        return self._outlines[gid]

    def mask(self, gid):
        if gid not in self._masks:
            self._masks[gid] = rasterize(self.outline(gid))
        return self._masks[gid]

    def close(self):
        self.shaper.close()
        self.font.close()


def bounds(contours):
    xs, ys = [x for c in contours for x, _ in c], [y for c in contours for _, y in c]
    return min(xs), min(ys), max(xs), max(ys)


def rasterize(contours) -> int:
    """外接矩形を GRID×GRID に広げた形を、非ゼロ規則で塗ったビット列にする (上の行が上位ではなく、行×GRID+列 番目のビット)"""
    x0, y0, x1, y1 = bounds(contours)
    width, height = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
    size = GRID * SAMPLES
    edges = []
    for contour in contours:
        for (ax, ay), (bx, by) in zip(contour, contour[1:] + contour[:1]):
            if ay != by:
                edges.append((((ax - x0) / width * size, (ay - y0) / height * size), ((bx - x0) / width * size, (by - y0) / height * size)))
    counts = [0] * (GRID * GRID)
    for row in range(size):
        y = row + 0.5
        crossings = []
        for (ax, ay), (bx, by) in edges:
            if (ay <= y) != (by <= y):
                crossings.append((ax + (y - ay) * (bx - ax) / (by - ay), 1 if by > ay else -1))
        crossings.sort()
        winding, index = 0, 0
        for column in range(size):
            x = column + 0.5
            while index < len(crossings) and crossings[index][0] <= x:
                winding += crossings[index][1]
                index += 1
            if winding:
                counts[(size - 1 - row) // SAMPLES * GRID + column // SAMPLES] += 1
    return sum(1 << i for i, count in enumerate(counts) if count * 2 >= SAMPLES * SAMPLES)


@lru_cache(maxsize=None)
def transforms(mask: int) -> dict[str, int]:
    bit = [(mask >> i) & 1 for i in range(GRID * GRID)]
    last = GRID - 1

    def make(where):
        return sum(1 << (y * GRID + x) for y in range(GRID) for x in range(GRID) if bit[where(x, y)])

    return {
        "id": mask,
        "flipH": make(lambda x, y: y * GRID + last - x),
        "flipV": make(lambda x, y: (last - y) * GRID + x),
        "rot180": make(lambda x, y: (last - y) * GRID + last - x),
        "rot90cw": make(lambda x, y: (last - x) * GRID + y),
        "rot90ccw": make(lambda x, y: x * GRID + last - y),
    }


def similarity(a: int, b: int) -> float:
    union = (a | b).bit_count()
    return (a & b).bit_count() / union if union else 1.0


def skipped(code: int) -> bool:
    char = chr(code)
    return (unicodedata.category(char) in ("Zs", "Cf", "Cc", "Co", "Cn")
            or unicodedata.name(char, "").startswith(("CJK UNIFIED", "CJK COMPATIBILITY IDEO", "HANGUL")))


def thin(contours) -> bool:
    x0, y0, x1, y1 = bounds(contours)
    return x1 - x0 < THIN or y1 - y0 < THIN


def single(face: Face, char: str, language: str, vertical: bool, features=()):
    shaped = face.shaper.shape(char, language, vertical, ("kern=0", *features))
    return shaped[0] if len(shaped) == 1 else None


def center(face: Face, record) -> tuple[float, float]:
    x0, y0, x1, y1 = bounds(face.outline(record[0]))
    return (x0 + x1) / 2 + record[4] / face.em, (y0 + y1) / 2 + record[5] / face.em


def record_fixture(serif: Path, sans: Path, output: Path) -> None:
    data = {"source": {}, "grid": GRID, "styles": {}}
    for style, path in (("Mincho", serif), ("Gothic", sans)):
        face = Face(path, 0)
        name = face.font["name"].getDebugName(1)
        if "JP" not in name:
            raise SystemExit(f"{path}: the first face is {name}, not a JP face")
        data["source"][style] = f"{name} {face.font['name'].getDebugName(5)}"
        entries = {}
        for code in sorted(face.cmap):
            if skipped(code):
                continue
            entry = {}
            for key, vertical in (("h", False), ("v", True)):
                shaped = single(face, chr(code), "ja", vertical)
                if shaped is None or not face.outline(shaped[0]) or thin(face.outline(shaped[0])):
                    continue
                x, y = center(face, shaped)
                entry[key] = [f"{face.mask(shaped[0]):x}", round(x, 3), round(y, 3)]
            if entry:
                entries[f"{code:04X}"] = entry
        data["styles"][style] = entries
        face.close()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{output}: {sum(len(s) for s in data['styles'].values())} entries, {output.stat().st_size // 1024} KiB")


@lru_cache(maxsize=1)
def load():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def same_as_source(ours: Face, sources: list[Face], char, language, vertical, record) -> bool:
    for source in sources:
        if ord(char) in source.cmap:
            other = single(source, char, language, vertical)
            if (other is not None and other[4:] == record[4:]
                    and source.outline(other[0]) == ours.outline(record[0])):
                return True
    return False


def check_face(label: str, ours: Face, style: str, sources: list[Face]) -> list[str]:
    problems = []
    for key, reference in load()["styles"][style].items():
        code = int(key, 16)
        if code not in ours.cmap:
            continue
        char = chr(code)
        for orientation, vertical in (("h", False), ("v", True)):
            if orientation not in reference:
                continue
            expected, x, y = reference[orientation]
            expected = int(expected, 16)
            for language in ("ja", "en"):
                shaped = single(ours, char, language, vertical)
                if shaped is None or not ours.outline(shaped[0]) or thin(ours.outline(shaped[0])):
                    continue
                candidates = transforms(ours.mask(shaped[0]))
                scores = {name: similarity(candidates[name], expected) for name in ("id", "flipH", "flipV", "rot180")}
                best = max(scores, key=scores.get)
                if (best != "id" and scores[best] > scores["id"] + MARGIN
                        and (code, orientation) not in KNOWN_ORIENTATION and code not in DESIGN):
                    problems.append(f"{label}: U+{code:04X} {char} ({language}, {orientation}) looks like {best} of Noto "
                                    f"({scores['id']:.2f} as is, {scores[best]:.2f} {best})")
                ours_x, ours_y = center(ours, shaped)
                if ((abs(ours_x - x) > POSITION or abs(ours_y - y) > POSITION)
                        and unicodedata.category(char) != "Mn" and code not in KNOWN_POSITION
                        and not (vertical and code in KNOWN_VERTICAL_POSITION)
                        and not same_as_source(ours, sources, char, language, vertical, shaped)):
                    problems.append(f"{label}: U+{code:04X} {char} ({language}, {orientation}) is "
                                    f"({ours_x - x:+.2f}, {ours_y - y:+.2f}) em from Noto")
    problems.extend(check_sideways(label, ours))
    problems.extend(check_sideways_quotes(label, ours))
    problems.extend(check_digits(label, ours))
    return problems


def check_sideways(label: str, ours: Face) -> list[str]:
    """vrt2 の欧字が、横組の字を右へ 90 度回した形であること"""
    problems = []
    for code in sorted(ours.cmap):
        char = chr(code)
        if unicodedata.category(char)[0] not in "LN" or not unicodedata.name(char, "").startswith(("LATIN", "DIGIT")):
            continue
        plain = single(ours, char, "ja", False)
        turned = single(ours, char, "ja", True, ("vert=0", "vrt2"))
        if plain is None or turned is None or plain[0] == turned[0]:
            continue
        if not ours.outline(plain[0]) or thin(ours.outline(plain[0])) or thin(ours.outline(turned[0])):
            continue
        candidates = transforms(ours.mask(plain[0]))
        expected = ours.mask(turned[0])
        scores = {name: similarity(mask, expected) for name, mask in candidates.items()}
        if max(scores, key=scores.get) != "rot90cw" and max(scores.values()) > scores["rot90cw"] + MARGIN:
            problems.append(f"{label}: vrt2 of U+{code:04X} {char} is not the horizontal glyph turned 90 degrees clockwise: {scores}")
    return problems


def check_sideways_quotes(label: str, ours: Face) -> list[str]:
    """縦組の英語の中の ‘ ’ が、横組の字を右へ 90 度回した形であること"""
    problems = []
    for char in "‘’":
        for language in ("ja", "en"):
            for features in ((), ("vert=0", "vrt2")):
                upright = ours.shaper.shape(char, language, False, (), "Latn")
                turned = ours.shaper.shape(char, language, True, ("kern=0", *features), "Latn")
                if len(upright) != 1 or len(turned) != 1:
                    problems.append(f"{label}: {char} is not one glyph in Latin text")
                    continue
                scores = {name: similarity(mask, ours.mask(turned[0][0])) for name, mask in transforms(ours.mask(upright[0][0])).items()}
                if max(scores, key=scores.get) != "rot90cw":
                    problems.append(f"{label}: {char} in vertical Latin text is not turned 90 degrees clockwise: {scores}")
    return problems


def check_digits(label: str, ours: Face) -> list[str]:
    """数字の機能の出力が、横組・縦組とも同じ数字の形であること"""
    problems = []
    digits = "0123456789"
    base = {d: ours.mask(single(ours, d, "ja", False)[0]) for d in digits}
    turned = {d: transforms(mask)["rot90cw"] for d, mask in base.items()}
    for digit in digits:
        for tag in DIGIT_FEATURES:
            for vertical, features, reference in ((False, (tag,), base), (True, (tag,), base),
                                                  (True, ("vert=0", "vrt2", tag), None)):
                shaped = single(ours, digit, "ja", vertical, features)
                if shaped is None or not ours.outline(shaped[0]):
                    problems.append(f"{label}: {tag} of {digit} (vertical={vertical}) is not one visible glyph")
                    continue
                mask = ours.mask(shaped[0])
                table = reference
                if table is None:  # vrt2 は横倒しの字になることも、ならないこともある
                    table = turned if max(similarity(mask, turned[d]) for d in digits) > max(similarity(mask, base[d]) for d in digits) else base
                if max(digits, key=lambda d: similarity(mask, table[d])) != digit:
                    problems.append(f"{label}: {tag} of {digit} (vertical={vertical}, {features}) looks like another digit")
    return problems


def check_font(label: str, path, style: str, source_paths) -> list[str]:
    ours, sources = Face(path), [Face(p) for p in source_paths]
    problems = check_face(label, ours, style, sources)
    for face in (ours, *sources):
        face.close()
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    record = commands.add_parser("record")
    record.add_argument("serif", type=Path)
    record.add_argument("sans", type=Path)
    audit = commands.add_parser("audit")
    audit.add_argument("font", type=Path)
    audit.add_argument("style", choices=("Mincho", "Gothic"))
    audit.add_argument("sources", type=Path, nargs="*")
    options = parser.parse_args()
    if options.command == "record":
        record_fixture(options.serif, options.sans, FIXTURE)
        return 0
    problems = check_font(options.font.name, options.font, options.style, options.sources)
    print("\n".join(problems) if problems else "ok")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
