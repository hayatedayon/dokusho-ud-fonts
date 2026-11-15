"""検査の共通の部品。問題の記録 (`check`・`problems`)、フォント 1 つ分の文脈 (`FontContext`)、フォントをまたいで組んだ結果を比べる `Shaped`。"""

from functools import cached_property
from pathlib import Path

from fontTools.ttLib import TTFont

import harfbuzz_shape
import spec

from .fonttables import combining_codes, latin_codes, outline
from .geometry import glyph_bounds

ROOT = Path(__file__).resolve().parent.parent.parent
SOURCES = ROOT / "sources"
FONTS = ROOT / "fonts"

problems: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        problems.append(message)


# 和文の文脈と英語の文脈 (検査が組む)
JAPANESE_CONTEXTS = [("あ{}あ", "ja"), ("漢{}漢", "ja"), ("{}", "ja")]
LATIN_CONTEXT = ("a{}a", "en")
UNICODE_DATA = Path("/usr/share/unicode")


def unicode_property(name: str, field: str | None = None) -> dict[int, str]:
    """Unicode の文字のデータ (DerivedCoreProperties.txt・VerticalOrientation.txt)。field が None なら、
    その名前の性質を持つ文字 → 名前"""
    path = UNICODE_DATA / name
    if not path.exists():
        raise SystemExit(f"{path} is needed to check the shaping (Debian / Ubuntu: unicode-data)")
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        fields = [f.strip() for f in line.split(";")]
        if field is not None and fields[1] != field:
            continue
        first, _, last = fields[0].partition("..")
        for code in range(int(first, 16), int(last or first, 16) + 1):
            result[code] = fields[1]
    return result


class Shaped:
    """組んだ字を、フォントをまたいで比べられる形にする (グリフの番号はフォントごとに違う)"""

    def __init__(self, path: Path, font: TTFont | None = None):
        self.font = font if font is not None else TTFont(path)
        self.shaper = harfbuzz_shape.Shaper(path)
        self.order = self.font.getGlyphOrder()
        self.outlines: dict[int, tuple] = {}

    def outline_of(self, glyph: int) -> tuple:
        if glyph not in self.outlines:
            coordinates, ends, _flags = outline(self.font, self.order[glyph])
            self.outlines[glyph] = (tuple(coordinates), tuple(ends))
        return self.outlines[glyph]

    def run(self, text: str, language: str, vertical: bool = False, features=(), cluster: int | None = None):
        """元フォントとの比較用。kern を切って (輪郭, 送り x, 送り y, ずれ x, ずれ y) を比べる。
        新しい kern の振る舞いは checks/kerning.py が、既定で有効なまま別に確かめる。"""
        return [(self.outline_of(g), xa, ya, xo, yo)
                for g, c, xa, ya, xo, yo in self.shaper.shape(text, language, vertical, ("kern=0", *features))
                if cluster is None or c == cluster]

    def run_script(self, text: str, script: str, language: str, vertical: bool) -> list:
        """用字系を指定して組む (ブラウザは、記号を前の字の用字系の組に入れる)"""
        return [(self.outline_of(g), xa, ya, xo, yo)
                for g, _c, xa, ya, xo, yo in self.shaper.shape(text, language, vertical, ("kern=0",), script)]

    def ink(self, text: str, language: str, vertical: bool = False, features=()) -> list:
        """組んだ字のインクの外形 (最初の字の原点から)。インクの無い字は None"""
        x = y = 0
        boxes = []
        for g, _c, xa, ya, xo, yo in self.shaper.shape(text, language, vertical, ("kern=0", *features)):
            bounds = glyph_bounds(self.font, self.order[g])
            boxes.append(None if bounds is None else
                         (bounds[0] + x + xo, bounds[1] + y + yo, bounds[2] + x + xo, bounds[3] + y + yo))
            x, y = x + xa, y + ya
        return boxes

    def close(self) -> None:
        self.shaper.close()


def same_glyph(font: TTFont, name: str, other: TTFont, other_name: str) -> bool:
    return (font["hmtx"][name] == other["hmtx"][other_name] and font["vmtx"][name] == other["vmtx"][other_name]
            and outline(font, name) == outline(other, other_name))


class Report:
    """組んだ結果の食い違いを、種類ごとに集めて `problems` に 1 行ずつ足す (例は 5 つまで)"""

    def __init__(self, label: str):
        self.label = label
        self.found: dict[str, list[str]] = {}

    def __call__(self, what: str, item: str) -> None:
        self.found.setdefault(what, []).append(item)

    def flush(self) -> None:
        for what, items in self.found.items():
            problems.append(f"{self.label}: {len(items)} {what}, such as {', '.join(items[:5])}")
        self.found = {}


class FontContext:
    """フォント 1 つ (書体 × 太さ) の検査に使うもの。ファイルは使うときに開き、終わったら閉じる"""

    def __init__(self, family: dict, weight: str):
        self.family, self.weight = family, weight
        self.label = spec.output_name(family, weight)
        self.path = FONTS / self.label
        self.ud_path = SOURCES / f"{family['ud']}-{weight}.ttf"
        self.udp_path = SOURCES / f"{family['udp']}-{weight}.ttf"

    @cached_property
    def font(self) -> TTFont:
        return TTFont(self.path)

    @cached_property
    def ud(self) -> TTFont:
        return TTFont(self.ud_path)

    @cached_property
    def udp(self) -> TTFont:
        return TTFont(self.udp_path)

    @cached_property
    def cmap(self) -> dict:
        return self.font.getBestCmap()

    @cached_property
    def cmap_ud(self) -> dict:
        return self.ud.getBestCmap()

    @cached_property
    def cmap_udp(self) -> dict:
        return self.udp.getBestCmap()

    @cached_property
    def em(self) -> int:
        return self.font["head"].unitsPerEm

    @cached_property
    def order(self) -> list[str]:
        return self.font.getGlyphOrder()

    @cached_property
    def latin_glyphs(self) -> set[str]:
        return {self.cmap[c] for c in latin_codes(self.cmap)}

    @cached_property
    def marks(self) -> set[int]:
        return set(combining_codes(self.cmap))

    @cached_property
    def ignorable(self) -> dict[int, str]:
        return unicode_property("DerivedCoreProperties.txt", "Default_Ignorable_Code_Point")

    @cached_property
    def orientation(self) -> dict[int, str]:
        return unicode_property("VerticalOrientation.txt")

    @cached_property
    def shaper(self) -> harfbuzz_shape.Shaper:
        return harfbuzz_shape.Shaper(self.path)

    @cached_property
    def ours(self) -> Shaped:
        return Shaped(self.path, self.font)

    @cached_property
    def ud_shaped(self) -> Shaped:
        return Shaped(self.ud_path, self.ud)

    @cached_property
    def udp_shaped(self) -> Shaped:
        return Shaped(self.udp_path, self.udp)

    def run(self, text, features=(), vertical=False):
        return self.shaper.shape(text, "ja", vertical, features)

    def width(self, text, features=()):
        return sum(r[2] for r in self.run(text, features))

    def close(self) -> None:
        for name in ("ours", "ud_shaped", "udp_shaped"):
            if name in self.__dict__:
                self.__dict__[name].close()
        if "shaper" in self.__dict__:
            self.shaper.close()
