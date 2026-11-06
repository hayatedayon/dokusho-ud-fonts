"""行の上と下からはみ出す字を、目で確かめる HTML (dist/overflow.html) を作る。

Windows の GDI で描くアプリは、OS/2 の usWinAscent (上) と usWinDescent (下) の外を描かない。fonts/ の
読書 UD で、その外に出る字を拾い、字の形 (フォントの輪郭をそのまま SVG にしたもの) に、行の上と下の線を
引き、外に出た所を赤く塗って並べる。同じ字の BIZ UD・BIZ UDP でのはみ出しも並べる。縦組の ⸺ ⸻ は、
縦の字送りの向きに伸びる字なので除く。

ブラウザで実際のフォントで描いた字も、いくつかの大きさで並べる (ブラウザは字を切らないので、そのまま
全部出る)。フォントを読むには、リポジトリの一番上で python3 -m http.server を動かし、
http://localhost:8000/dist/overflow.html を開く (ファイルを直接開くと、ブラウザによっては fonts/ を
読まない)。

    python3 scripts/overflow_page.py
"""

import html
import sys
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

import check
import spec

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "dist" / "overflow.html"
SIZES = [16, 24, 48, 96]  # 何 px のときに何 px はみ出すかを出す大きさ


def bounds(font: TTFont, name: str):
    glyph_set = font.getGlyphSet()
    pen = BoundsPen(glyph_set)
    glyph_set[name].draw(pen)
    return pen.bounds


def path(font: TTFont, name: str) -> str:
    glyph_set = font.getGlyphSet()
    pen = SVGPathPen(glyph_set)
    glyph_set[name].draw(pen)
    return pen.getCommands()


def overflow(font: TTFont, name: str) -> tuple[float, float]:
    b = bounds(font, name)
    if b is None:
        return 0, 0
    os2 = font["OS/2"]
    return max(0, b[3] - os2.usWinAscent), max(0, -os2.usWinDescent - b[1])


def labels(font: TTFont) -> dict[str, str]:
    """グリフ → 説明 (文字。欧文の中でだけ使う字は、その旨)"""
    cmap = font.getBestCmap()
    result = {}
    for code, name in sorted(cmap.items()):
        result.setdefault(name, f"{chr(code)} U+{code:04X}")
    for name, symbol in check.latin_symbol_mapping(font, "latn", None).items():
        if symbol not in result and name in result:
            result[symbol] = f"欧文の中の {result[name]} (BIZ UDP の字)"
    return result


def svg(font: TTFont, name: str, height: int = 220, zoom: str | None = None) -> str:
    """字と、行の上・ベースライン・行の下の線。外に出た所は赤。zoom ("top" か "bottom") は、その線の
    あたりだけを拡大する"""
    os2 = font["OS/2"]
    top, bottom = os2.usWinAscent, -os2.usWinDescent
    advance = font["hmtx"][name][0]
    x0, y0, x1, y1 = bounds(font, name)
    pad = 160
    left, right = min(0, x0) - pad, max(advance, x1) + pad
    high, low = max(top, y1) + pad, min(bottom, y0) - pad
    if zoom:
        left, right = x0 - 40, x1 + 40
        line = top if zoom == "top" else bottom
        high, low = (max(y1, line) + 30, line - 120) if zoom == "top" else (line + 120, min(y0, line) - 30)
    width = (right - left) * height / (high - low)
    d = path(font, name)
    key = "k" + "".join(ch for ch in f"{font['name'].getDebugName(6)}{name}{zoom}" if ch.isalnum())
    stroke = (high - low) / 80  # 線の太さは、拡大しても同じに見えるように
    # 中の g は、フォントの座標 (y が上向き)。外の SVG は y が下向き
    return f"""<svg viewBox="{left} {-high} {right - left} {high - low}" width="{width:.0f}" height="{height}" role="img">
<defs><clipPath id="{key}" clipPathUnits="userSpaceOnUse">
<rect x="{left}" y="{top}" width="{right - left}" height="{high - top}"/>
<rect x="{left}" y="{low}" width="{right - left}" height="{bottom - low}"/>
</clipPath></defs>
<rect x="0" y="{-top}" width="{advance}" height="{top - bottom}" class="box"/>
<line x1="{left}" x2="{right}" y1="{-top}" y2="{-top}" class="win" style="stroke-width: {stroke:.1f}; stroke-dasharray: {stroke * 5:.0f} {stroke * 3:.0f}"/>
<line x1="{left}" x2="{right}" y1="{-bottom}" y2="{-bottom}" class="win" style="stroke-width: {stroke:.1f}; stroke-dasharray: {stroke * 5:.0f} {stroke * 3:.0f}"/>
<line x1="{left}" x2="{right}" y1="0" y2="0" class="base" style="stroke-width: {stroke * 0.7:.1f}"/>
<g transform="scale(1,-1)">
<path d="{d}" class="ink"/>
<path d="{d}" class="cut" clip-path="url(#{key})"/>
</g>
</svg>"""


def source_overflow(source: TTFont, label: str) -> str:
    """同じ文字の、元のフォントでのはみ出し"""
    if "U+" not in label:
        return "—"
    code = int(label.split("U+")[1][:4], 16)
    # 欧文の中でだけ使う字は、BIZ UDP の字 (BIZ UD の欄は、その文字の BIZ UD の字)
    name = source.getBestCmap().get(code)
    if name is None:
        return "—"
    up, down = overflow(source, name)
    return describe(up, down)


def describe(up: float, down: float) -> str:
    parts = []
    if up:
        parts.append(f"上 {up:.0f}")
    if down:
        parts.append(f"下 {down:.0f}")
    return "・".join(parts) if parts else "なし"


def section(family: dict, weight: str) -> str:
    label = spec.output_name(family, weight)
    font = TTFont(ROOT / "fonts" / label)
    ud = TTFont(ROOT / "sources" / f"{family['ud']}-{weight}.ttf")
    udp = TTFont(ROOT / "sources" / f"{family['udp']}-{weight}.ttf")
    em = font["head"].unitsPerEm
    os2 = font["OS/2"]
    cmap = font.getBestCmap()
    vertical_dashes = {check.gsub_mapping(font, "vert").get(cmap.get(code)) for code in (0x2E3A, 0x2E3B)}
    names = labels(font)
    rows = []
    samples = []
    for name in font.getGlyphOrder():
        if name in vertical_dashes:
            continue
        up, down = overflow(font, name)
        if not (up or down):
            continue
        text = names.get(name, name)
        pixels = " / ".join(f"{max(up, down) * size / em:.2f}" for size in SIZES)
        rows.append(f"""<div class="glyph">
{svg(font, name)}
<figure>{svg(font, name, 220, "top" if up >= down else "bottom")}<figcaption>{"上" if up >= down else "下"}の線のあたりを拡大</figcaption></figure>
<dl>
<dt>字</dt><dd>{html.escape(text)}</dd>
<dt>はみ出し (1 em = {em})</dt><dd>{describe(up, down)}</dd>
<dt>{" / ".join(f"{s}px" for s in SIZES)} のとき</dt><dd>{pixels} px</dd>
<dt>BIZ UD</dt><dd>{source_overflow(ud, text)}</dd>
<dt>BIZ UDP</dt><dd>{source_overflow(udp, text)}</dd>
</dl>
</div>""")
        if "U+" in text:
            samples.append(chr(int(text.split("U+")[1][:4], 16)))
    family_css = f"{family['postscript']}-{weight}"
    sample_text = html.escape("".join(dict.fromkeys(samples)))
    live = "\n".join(
        f'<p class="live" style="font-family: \'{family_css}\'; font-size: {size}px"><span>{size}px</span>'
        f'<span class="line">„Ja“ ‚nein‘ {sample_text} 読書</span></p>'
        for size in (16, 48, 128))
    body = "\n".join(rows) if rows else "<p>はみ出す字はありません。</p>"
    return f"""<section>
<h2>{html.escape(family['name_ja'])} {weight} <small>({label}・usWinAscent {os2.usWinAscent}・usWinDescent {os2.usWinDescent})</small></h2>
<div class="glyphs">{body}</div>
<h3>ブラウザで描いた字 (フォントを読めたときだけ)</h3>
<p class="note">ブラウザは字を切らないので、全部出ます。行の高さは、線のある箱です。</p>
{live}
</section>"""


def page() -> str:
    faces = "\n".join(
        f"@font-face {{ font-family: '{family['postscript']}-{weight}'; "
        f"src: url('../fonts/{spec.output_name(family, weight)}'); }}"
        for family in spec.FAMILIES for weight in spec.WEIGHTS)
    sections = "\n".join(section(family, weight) for family in spec.FAMILIES for weight in spec.WEIGHTS)
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>読書 UD: 行の上と下からはみ出す字</title>
<style>
{faces}
body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #222; line-height: 1.6; }}
h2 small {{ font-weight: normal; color: #666; font-size: 0.7em; }}
.glyphs {{ display: flex; flex-wrap: wrap; gap: 1rem; }}
.glyph {{ border: 1px solid #ddd; padding: 0.5rem; display: flex; gap: 0.75rem; align-items: center; }}
.glyph dl {{ margin: 0; font-size: 0.85rem; display: grid; grid-template-columns: max-content max-content; gap: 0 0.75rem; }}
.glyph dt {{ color: #666; }}
.glyph dd {{ margin: 0; }}
svg .box {{ fill: #f4f8ff; stroke: none; }}
svg .win {{ stroke: #1d6fd8; }}
svg .base {{ stroke: #aaa; }}
figure {{ margin: 0; text-align: center; font-size: 0.75rem; color: #666; }}
svg .ink {{ fill: #222; }}
svg .cut {{ fill: #e0322b; }}
.legend span {{ display: inline-block; margin-right: 1.5rem; }}
.swatch {{ display: inline-block; width: 1em; height: 1em; vertical-align: -0.15em; margin-right: 0.3em; }}
.live {{ margin: 0.25rem 0; display: flex; align-items: baseline; gap: 1rem; }}
.live span:first-child {{ font-family: system-ui, sans-serif; font-size: 12px; color: #666; width: 3rem; }}
.live .line {{ outline: 1px solid #9bc0f0; line-height: normal; }}
.note {{ color: #666; font-size: 0.9rem; }}
</style>
</head>
<body>
<h1>行の上と下からはみ出す字</h1>
<p>Windows の GDI で描くアプリは、フォントの usWinAscent (行の上) と usWinDescent (行の下) の外を描きません。
読書 UD のうち、その外に出る字を並べました。字の形は、フォントの輪郭をそのまま描いたものです。
macOS・iOS・Android と、ブラウザの多くは、字を切りません。</p>
<p class="legend"><span><span class="swatch" style="background:#e0322b"></span>行の外に出た所 (GDI では描かれない)</span>
<span><span class="swatch" style="border-top:3px dashed #1d6fd8"></span>行の上と下</span>
<span><span class="swatch" style="border-top:3px solid #aaa"></span>ベースライン</span>
<span><span class="swatch" style="background:#f4f8ff"></span>字の枠</span></p>
<p class="note">縦組の ⸺ ⸻ (縦の字送りの向きに 2 em・3 em 伸びる字) は除いています。BIZ UD・BIZ UDP の欄は、同じ文字の元のフォントでのはみ出しです。</p>
{sections}
</body>
</html>
"""


def main() -> int:
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(page(), encoding="utf-8")
    print(f"{OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
