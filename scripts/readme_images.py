"""README に載せる見本の画像 (docs/images/*.svg) を、できたフォントの輪郭から作る。

HarfBuzz で組み、fontTools で輪郭を SVG のパスにする。文字はパスなので、見る環境にフォントが無くても同じに見える。
GitHub の暗い表示でも読めるよう、背景の紙の色も画像に含める。

    python3 scripts/readme_images.py
"""

import html
import sys
import unicodedata
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

import harfbuzz_shape
import spec

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "docs" / "images"

PAPER, INK, MUTED, RULE, ACCENT = "#fbfcfd", "#1b2430", "#5c6875", "#d5dbe2", "#2f5d8a"


def script_of(char: str) -> str | None:
    """ブラウザのように文字列を用字系ごとに分けるための用字系。記号などは None (前の字に続く)"""
    if unicodedata.category(char)[0] not in "LN" and char not in "゙゚":
        return None
    name = unicodedata.name(char, "")
    if name.startswith("LATIN") or name.startswith("MODIFIER") or name.startswith("FULLWIDTH LATIN"):
        return "Latn"
    if name.startswith("HIRAGANA"):
        return "Hira"
    if name.startswith(("KATAKANA", "HALFWIDTH KATAKANA")):
        return "Kana"
    if name.startswith("CJK"):
        return "Hani"
    return None


def runs(text: str) -> list[tuple[str, str]]:
    """[(部分文字列, 用字系), ...]。先頭の記号は次の字の用字系に入れる"""
    result: list[list[str]] = []
    for char in text:
        script = script_of(char)
        if result and (script is None or result[-1][1] in (None, script)):
            result[-1][0] += char
            result[-1][1] = result[-1][1] or script
        else:
            result.append([char, script])
    return [(part, script or "Latn") for part, script in result]


class Face:
    def __init__(self, path: Path):
        self.font = TTFont(path)
        self.shaper = harfbuzz_shape.Shaper(path)
        self.em = self.font["head"].unitsPerEm
        self.order = self.font.getGlyphOrder()
        self.glyphs = self.font.getGlyphSet()

    def path(self, gid: int) -> str:
        pen = SVGPathPen(self.glyphs)
        self.glyphs[self.order[gid]].draw(pen)
        return pen.getCommands()

    def shape(self, text: str, language: str, vertical: bool, features=()) -> list[tuple]:
        return [record for part, script in runs(text)
                for record in self.shaper.shape(part, language, vertical, features, script)]


class Canvas:
    def __init__(self, width: int, height: int, title: str):
        self.width, self.height, self.title = width, height, title
        self.body: list[str] = []
        self.defs: dict[tuple[int, int], str] = {}
        self.faces: dict[Face, int] = {}

    def _ref(self, face: Face, gid: int) -> str | None:
        index = self.faces.setdefault(face, len(self.faces))
        key = (index, gid)
        if key not in self.defs:
            commands = face.path(gid)
            if not commands:
                self.defs[key] = ""
                return None
            self.defs[key] = f'<path id="g{index}-{gid}" d="{commands}"/>'
        return f"g{index}-{gid}" if self.defs[key] else None

    def _use(self, face: Face, gid: int, x: float, y: float, size: float, fill: str) -> None:
        ref = self._ref(face, gid)
        if ref:
            scale = size / face.em
            self.body.append(f'<use href="#{ref}" transform="translate({x:.2f} {y:.2f}) scale({scale:.5f} {-scale:.5f})" '
                             f'fill="{fill}"/>')

    def text(self, face: Face, text: str, x: float, y: float, size: float, fill: str = INK,
             language: str = "ja", features=()) -> float:
        """横組。(x, y) は基準線の左端。終わりの x を返す"""
        scale = size / face.em
        for gid, _c, advance, _ya, dx, dy in face.shape(text, language, False, features):
            self._use(face, gid, x + dx * scale, y - dy * scale, size, fill)
            x += advance * scale
        return x

    def vertical(self, face: Face, text: str, x: float, y: float, size: float, fill: str = INK) -> None:
        """縦組。(x, y) は行の中心線の上端"""
        scale = size / face.em
        for gid, _c, _xa, advance, dx, dy in face.shape(text, "ja", True):
            self._use(face, gid, x + dx * scale, y - dy * scale, size, fill)
            y -= advance * scale

    def rule(self, x1: float, y1: float, x2: float, y2: float, color: str = RULE) -> None:
        self.body.append(f'<path d="M{x1} {y1}L{x2} {y2}" stroke="{color}" stroke-width="1"/>')

    def svg(self) -> str:
        defs = "".join(value for value in self.defs.values() if value)
        title = html.escape(self.title)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
                f'width="{self.width}" height="{self.height}" role="img" aria-label="{title}"><title>{title}</title>'
                f'<rect width="{self.width}" height="{self.height}" fill="{PAPER}"/><defs>{defs}</defs>'
                + "".join(self.body) + "</svg>\n")


def face(family: dict, weight: str) -> Face:
    return Face(ROOT / "fonts" / spec.output_name(family, weight))


COLUMNS = [
    "　吾輩は猫である。名前はまだ無い。",
    "　どこで生れたかとんと見当がつかぬ。",
    "何でも薄暗いじめじめした所で",
    "ニャーニャー泣いていた事だけは",
    "記憶している。吾輩はここで始めて",
    "人間というものを見た。",
]


def specimen() -> str:
    mincho, gothic = spec.FAMILIES
    mr, mb, gr, gb = face(mincho, "Regular"), face(mincho, "Bold"), face(gothic, "Regular"), face(gothic, "Bold")
    canvas = Canvas(1200, 640, "読書 UD明朝と読書 UDゴシックの見本")
    # 左半分: 縦組の本文。右の行から順に置く
    x = 500
    for column in COLUMNS:
        canvas.vertical(mr, column, x, 64, 29)
        x -= 54
    canvas.vertical(gr, "夏目漱石『吾輩は猫である』", 100, 64, 15, MUTED)
    canvas.rule(600, 56, 600, 584)
    # 右半分: 2 つの書体の横組
    left = 650
    canvas.text(mb, "読書 UD明朝", left, 104, 46)
    canvas.text(mr, "画面に“Hello, world”と出たのは、", left, 160, 25)
    canvas.text(mr, "2026年11月6日の午後3時だった。", left, 200, 25)
    canvas.text(mr, "あいう アイウ 永遠の本 Aa Gg Qq 0123", left, 240, 25, ACCENT)
    canvas.rule(left, 288, 1150, 288)
    canvas.text(gb, "読書 UDゴシック", left, 354, 46)
    canvas.text(gr, "Alice was beginning to get very tired", left, 410, 25, language="en")
    canvas.text(gr, "of sitting by her sister on the bank.", left, 450, 25, language="en")
    canvas.text(gr, "あいう アイウ 永遠の本 Aa Gg Qq 0123", left, 490, 25, ACCENT)
    canvas.rule(left, 538, 1150, 538)
    canvas.text(gr, "Regular・Bold　縦組・横組　SIL Open Font License 1.1", left, 578, 16, MUTED)
    return canvas.svg()


def comparison() -> str:
    mincho = spec.FAMILIES[0]
    labels = face(spec.FAMILIES[1], "Regular")
    rows = [("BIZ UD明朝", "仮名は全角、欧字は半角の等幅", Face(ROOT / "sources" / f"{mincho['ud']}-Regular.ttf")),
            ("BIZ UDP明朝", "欧字は字ごとの幅、仮名も字ごとの幅", Face(ROOT / "sources" / f"{mincho['udp']}-Regular.ttf")),
            ("読書 UD明朝", "仮名は全角、欧字は字ごとの幅", face(mincho, "Regular"))]
    sentence = "彼女は「It’s alive!」と叫んで、iPhone と MacBook を見比べた。"
    canvas = Canvas(1200, 400, "BIZ UD明朝、BIZ UDP明朝、読書 UD明朝で同じ文を組んだ比較")
    y = 42
    for index, (name, note, font) in enumerate(rows):
        highlighted = index == 2
        end = canvas.text(labels, name, 40, y + 16, 18, ACCENT if highlighted else INK)
        canvas.text(labels, note, end + 16, y + 16, 15, MUTED)
        canvas.text(font, sentence, 40, y + 70, 30)
        y += 118
        if index < 2:
            canvas.rule(40, y - 14, 1160, y - 14)
    return canvas.svg()


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, data in (("specimen.svg", specimen()), ("comparison.svg", comparison())):
        (OUTPUT / name).write_text(data, encoding="utf-8")
        print(f"{OUTPUT / name}: {len(data) // 1024} KiB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
