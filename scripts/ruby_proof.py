"""ルビ仮名の試作 (ss03) を、ヒントの有無・gasp・補強量をそろえて比べるページを dist/ruby-trial.html に作る。

python3 scripts/ruby_proof.py

配るフォントは変えない。見本のためだけの、補強量を変えた試作字形は、できたフォントを読み直して
輪郭を差し替えた一時のフォントで作り、配るフォントには入れない。FreeType の結果であり、Windows・macOS の
実機描画とは別である。数値は stdout にも出す。
"""

import build
import hashlib
import html
import sys
import tempfile
from pathlib import Path

from fontTools.ttLib import TTFont

import freetype_render
import harfbuzz_shape
import small_type
import spec
from checks.fonttables import gsub_mapping
from proof_page import figure_html, png, raster

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "dist"

# 本文 12〜20px のルビ (本文の半分) は 6〜10ppem
PPEMS = (6, 7, 8, 9, 10)
INTERPRETERS = (("v40", 40), ("v35", 35))
ENVIRONMENTS = (("gasp を守らない環境", False), ("gasp を守る環境", True))
# ss03 の対象 194 字を、平仮名・片仮名・小書きの片仮名拡張の順に、1 行 24 字までに分ける
CHUNK = 24


def _samples() -> tuple:
    groups = (("平仮名", range(0x3041, 0x3097)), ("片仮名", range(0x30A0, 0x30FC)), ("小書きの片仮名拡張", range(0x31F0, 0x3200)))
    samples = []
    for label, codes in groups:
        text = "".join(map(chr, codes))
        for start in range(0, len(text), CHUNK):
            samples.append((f"{label} {text[start]}〜{text[min(start + CHUNK, len(text)) - 1]}", text[start:start + CHUNK]))
    return tuple(samples)


SAMPLES = _samples()
assert "".join(text for _label, text in SAMPLES) == small_type.RUBY_KANA
LARGE_TEXT, LARGE_PPEM = "あぬれゃっが", 64
# 全字の一覧 (配るフォントのまま。通常字・試作字形・縦組の字形) の大きさ
LIST_PPEM, LIST_COLUMNS = 40, 16
BLUR_PPEMS = (8, 9, 10)

# (見出し, 現在の補強量 s に掛ける (横, 縦))。embolden の ex は横に、ey は縦に太らせる
# (縦線の太さは ex、横線の太さは ey で変わる)。None の行は通常字そのもの。
VARIANTS = (
    ("通常・ヒントなし（基準）", None),
    ("試作・補強なし（拡大も補強もしない。小書き仮名の拡大率が 1.0 なら通常字と同じ輪郭）", (0, 0)),
    ("試作・今の値（配るフォント）", (1, 1)),
    ("試作・2 倍", (2, 2)),
    ("試作・4 倍", (4, 4)),
    ("試作・横線だけ 4 倍（縦に太らせる）", (0, 4)),
    ("試作・縦線だけ 4 倍（横に太らせる）", (4, 0)),
)
CURRENT = 2


def difference(a: tuple, b: tuple) -> tuple[int, float]:
    """同じ大きさの 2 つのラスタの、濃さが違う画素の数と、濃さの差の合計 (インク 1 画素分を単位にする)。"""
    if a[:2] != b[:2]:
        raise SystemExit("rasters differ in size")
    pixels = [(x, y) for x, y in zip(a[2], b[2]) if x != y]
    return len(pixels), sum(abs(x - y) for x, y in pixels) / 255


def ink(canvas: tuple) -> float:
    return sum(255 - v for v in canvas[2]) / 255


def variant_font(path: Path, multipliers: tuple[float, float], output: Path) -> None:
    """配るフォントの試作字形 （ss03 の置き換え先） だけを、補強量を変えた輪郭に差し替えて保存する。"""
    font = TTFont(path)
    strength = small_type.trial_strength(font)
    trial = gsub_mapping(font, "ss03")
    for source, scale in small_type.trial_sources(font).items():
        name = trial[source]
        glyph = small_type.trial_glyph(font, source, scale, strength * multipliers[0], strength * multipliers[1])
        font["glyf"][name] = glyph
        glyph.recalcBounds(font["glyf"])
        font["hmtx"][name] = (font["hmtx"][name][0], glyph.xMin)
        original = font["glyf"][source]
        original.recalcBounds(font["glyf"])
        advance, side = font["vmtx"][source]
        font["vmtx"][name] = (advance, side + original.yMax - glyph.yMax)
    font.save(output)
    font.close()


def check_current_variant(path: Path) -> None:
    """補強量 (1, 1) で作り直した輪郭が、配るフォントの試作字形と同じであること (見本の処理が配るフォントと同じ)。"""
    font = TTFont(path)
    strength = small_type.trial_strength(font)
    trial = gsub_mapping(font, "ss03")
    for source, scale in small_type.trial_sources(font).items():
        glyph = small_type.trial_glyph(font, source, scale, strength, strength)
        shipped = font["glyf"][trial[source]]
        if list(glyph.coordinates) != list(shipped.coordinates) or list(glyph.endPtsOfContours) != list(shipped.endPtsOfContours):
            raise SystemExit(f"{path.name}: rebuilt trial glyph of {source} differs from the shipped font")
    font.close()


class Counter:
    def __init__(self):
        self.value = 0

    def next(self, prefix: str) -> str:
        self.value += 1
        return f"{prefix}-{self.value}"


def hinting_section(path: Path, counter: Counter, summary: list) -> str:
    """通常・ヒントあり / 通常・ヒントなし / 試作・ヒントなし / 試作・ヒントあり を、gasp と FreeType の版ごとに並べる。

試作・ヒントありは配るフォントのままの描画 (試作字形は原字の命令を持つ)、試作・ヒントなしは、同じ字形を
ヒンティングを動かさずに描いたもの。"""
    font = TTFont(path)
    em = font["head"].unitsPerEm
    shaper = harfbuzz_shape.Shaper(path)
    plain = {}
    parts = []
    for interpreter_label, interpreter in INTERPRETERS:
        plain = freetype_render.Renderer(path, interpreter, freetype_render.NO_HINTING)
        for environment, respect in ENVIRONMENTS:
            hinted = freetype_render.Renderer(path, interpreter, 0, respect_gasp=respect)
            parts.append(f"<h4>FreeType {interpreter_label}・{environment}</h4>")
            if not (interpreter_label == "v40" and not respect):
                parts.append("<p>画像は FreeType v40・gasp を守らない環境だけに並べます（ほかは画素の差の数値だけ。数値のまとめにあります）。</p>")
            for ppem in PPEMS:
                totals = {"hint": [0, 0.0], "embolden": [0, 0.0], "all": [0, 0.0], "unhinted_trial": [0, 0.0], "trial_hint": [0, 0.0],
                          "ink_hinted": 0.0, "ink_plain": 0.0, "ink_trial_plain": 0.0, "ink_trial": 0.0}
                for script, text in SAMPLES:
                    a = raster(shaper, hinted, text, ppem, em)
                    b = raster(shaper, plain, text, ppem, em)
                    c = raster(shaper, hinted, text, ppem, em, ("ss03",))
                    c_plain = raster(shaper, plain, text, ppem, em, ("ss03",))
                    for key, pair in (("hint", (a, b)), ("embolden", (b, c_plain)), ("all", (a, c)), ("unhinted_trial", (a, c_plain)), ("trial_hint", (c_plain, c))):
                        count, amount = difference(*pair)
                        totals[key][0] += count
                        totals[key][1] += amount
                    totals["ink_hinted"] += ink(a)
                    totals["ink_plain"] += ink(b)
                    totals["ink_trial_plain"] += ink(c_plain)
                    totals["ink_trial"] += ink(c)
                    if interpreter_label == "v40" and not respect:
                        cells = "".join(
                            figure_html(*canvas, text, ppem, figure_id=counter.next("r"), caption=caption)
                            for caption, canvas in (("通常・ヒントあり", a), ("通常・ヒントなし", b), ("試作・ヒントなし", c_plain), ("試作・ヒントあり", c)))
                        parts.append(f"<p>{ppem} ppem（本文{ppem * 2}px のルビ）・{html.escape(script)}</p><div class=pair>{cells}</div>")
                summary.append((path.name, interpreter_label, environment, ppem, totals))
            if not respect:
                parts.append(f"<p>{LARGE_PPEM}px の拡大（画像は等倍）</p><div class=pair>")
                for caption, renderer, features in (("通常・ヒントあり", hinted, ()), ("通常・ヒントなし", plain, ()),
                                                    ("試作・ヒントなし", plain, ("ss03",)), ("試作・ヒントあり", hinted, ("ss03",))):
                    width, height, data = raster(shaper, renderer, LARGE_TEXT, LARGE_PPEM, em, features)
                    parts.append(f'<figure><figcaption>{caption}</figcaption><img alt="{LARGE_TEXT} {LARGE_PPEM}px {caption}" '
                                 f'src="{png(width, height, data)}" width="{width}" height="{height}"></figure>')
                parts.append("</div>")
            hinted.close()
        plain.close()
    shaper.close()
    font.close()
    return "".join(parts)


def trial_labels(font) -> list[tuple[str, str, str]]:
    """ss03 の (字の表示, 元の字形, 試作字形)。横組の 194 字のあとに、縦組で別の字形になる字を付ける。"""
    trial = gsub_mapping(font, "ss03")
    cmap, gsub = font.getBestCmap(), font["GSUB"].table
    rows, vertical = [], []
    for char in small_type.RUBY_KANA:
        base = cmap[ord(char)]
        rows.append((char, base, trial[base]))
        forms = set()
        for tag in ("vert", "vrt2"):
            forms.update(build.single_mapping(gsub, tag, {base}).values())
        vertical.extend((char + "(縦)", form, trial[form]) for form in sorted(forms - {base}))
    return rows + vertical


def pixels_of(renderer, gid: int, ppem: int, em: int | None = None) -> dict:
    left, top, _advance, cols, rows, bitmap = renderer.render(gid, ppem)
    stride = len(bitmap) // rows if rows else 0
    return {(left + x, y - top): bitmap[y * stride + x] for y in range(rows) for x in range(cols) if bitmap[y * stride + x]}


def boundary(pixels: dict) -> float:
    """境界のにじみ (中間の濃さの画素の量)。濃さ v (0〜255) の画素ごとに min(v, 255 - v) を足し、インク 1 画素分を単位にする。"""
    return sum(min(v, 255 - v) for v in pixels.values()) / 255


def blur_rows(paths: list) -> list:
    """試作字形ごとの、FreeType v40 グレースケール・8〜10ppem・4 書体の合計の、境界のにじみ (ヒントあり・なし)。

    ヒントなしは、同じ試作字形を FreeType でヒンティングを動かさずに描いたもの。(字の表示, ヒントなし, ヒントあり, 命令の無い書体の数) を返す。"""
    totals: dict[str, list] = {}
    for path in paths:
        font = TTFont(path)
        hinted = freetype_render.Renderer(path, 40, 0)
        plain = freetype_render.Renderer(path, 40, freetype_render.NO_HINTING)
        for label, _source, target in trial_labels(font):
            row = totals.setdefault(label, [0.0, 0.0, 0])
            gid = font.getGlyphID(target)
            for ppem in BLUR_PPEMS:
                row[0] += boundary(pixels_of(plain, gid, ppem))
                row[1] += boundary(pixels_of(hinted, gid, ppem))
            row[2] += 0 if len(font["glyf"][target].program.getBytecode()) else 1
        hinted.close()
        plain.close()
        font.close()
    return [(label, *row) for label, row in totals.items()]


def blur_section(rows: list) -> str:
    worse = sorted((r for r in rows if r[2] > r[1]), key=lambda r: r[2] / r[1], reverse=True)
    total = (sum(r[1] for r in rows), sum(r[2] for r in rows))
    body = "".join(f"<tr><td>{html.escape(label)}</td><td>{plain:.1f}</td><td>{hinted:.1f}</td><td>{hinted / plain:.3f}</td><td>{missing}</td></tr>"
                   for label, plain, hinted, missing in worse)
    return (f"<h2 id=blur>ヒントでにじみが増える字</h2><p>FreeType v40・グレースケール・{BLUR_PPEMS[0]}〜{BLUR_PPEMS[-1]}ppem・4 書体の合計で、境界のにじみ"
            f"（中間の濃さの画素の量。濃さ v の画素ごとに min(v, 255 − v) を足し、インク 1 画素分を単位にする）が、試作字形のヒントなしよりヒントありで多い字は、"
            f"{len(rows)} グリフのうち {len(worse)} です。全グリフの合計は、ヒントなし {total[0]:.1f}、ヒントあり {total[1]:.1f} です。"
            f"最後の列は、その字がヒントを持たない書体の数です（ヒントを持たない書体は、ヒントあり・なしが同じ画素になります）。</p>"
            f"<table><thead><tr><th>字</th><th>ヒントなし</th><th>ヒントあり</th><th>比</th><th>ヒントを持たない書体</th></tr></thead><tbody>{body}</tbody></table>")


def glyph_list_section(path: Path, counter: Counter) -> str:
    """ss03 の全グリフ (横組 194、縦組の別の字形 41) を、通常字と試作字形 (ヒントなし・ヒントあり) で大きく並べる。崩れた字を探すための一覧です。"""
    font = TTFont(path)
    em = font["head"].unitsPerEm
    rows = trial_labels(font)
    plain = freetype_render.Renderer(path, 40, freetype_render.NO_HINTING)
    hinted = freetype_render.Renderer(path, 40, 0)
    pitch = round(LIST_PPEM * 1.25)
    parts = []
    for start in range(0, len(rows), LIST_COLUMNS):
        chunk = rows[start:start + LIST_COLUMNS]
        width, height = pitch * len(chunk) + LIST_PPEM // 2, round(LIST_PPEM * 1.7)
        figures = []
        for caption, renderer, index in (("通常", plain, 1), ("試作", plain, 2), ("試作・ヒントあり", hinted, 2)):
            canvas = bytearray([255] * (width * height))
            for column, row in enumerate(chunk):
                left, top, _advance, cols, rows_, bitmap = renderer.render(font.getGlyphID(row[index]), LIST_PPEM)
                stride = len(bitmap) // rows_ if rows_ else 0
                for by in range(rows_):
                    for bx in range(cols):
                        x, y = LIST_PPEM // 4 + column * pitch + left + bx, round(LIST_PPEM * 1.25) - top + by
                        if 0 <= x < width and 0 <= y < height:
                            canvas[y * width + x] = min(canvas[y * width + x], 255 - bitmap[by * stride + bx])
            uri = png(width, height, bytes(canvas))
            figures.append(f'<figure><figcaption>{caption}</figcaption><img alt="{html.escape("".join(r[0] for r in chunk))} {caption}" src="{uri}" width="{width}" height="{height}"></figure>')
        parts.append(f"<p>{html.escape(' '.join(r[0] for r in chunk))}</p><div class=pair>{''.join(figures)}</div>")
    renderers = (plain, hinted)
    for renderer in renderers:
        renderer.close()
    font.close()
    return "".join(parts)


def embolden_section(path: Path, directory: Path, counter: Counter, ink_table: list) -> str:
    """補強量を変えた試作字形を、ヒントなしで 6〜10ppem と拡大で並べる。"""
    font = TTFont(path)
    em = font["head"].unitsPerEm
    strength = small_type.trial_strength(font)
    font.close()
    check_current_variant(path)
    sources = []
    for index, (label, multipliers) in enumerate(VARIANTS):
        if multipliers is None or index == CURRENT:
            sources.append(path)
            continue
        target = directory / f"{path.stem}-{index}.ttf"
        variant_font(path, multipliers, target)
        sources.append(target)
    shapers = [harfbuzz_shape.Shaper(source) for source in sources]
    # 補強量の組ごとに、FreeType (v40・ヒントなし) で描く。通常字もヒントなしにして補強量の差だけを見る。
    renderers = [freetype_render.Renderer(source, 40, freetype_render.NO_HINTING) for source in sources]
    parts = [f"<p>補強量の単位は {strength}（配るフォントの値、{strength / em * 100:.2f}% em）。"
             "各行の見出しは、現在の値に掛けた倍率の組（横, 縦）です。</p>"]
    for ppem in PPEMS:
        for script, text in SAMPLES:
            cells, base = [], None
            for index, (label, multipliers) in enumerate(VARIANTS):
                features = () if multipliers is None else ("ss03",)
                canvas = raster(shapers[index], renderers[index], text, ppem, em, features)
                if multipliers is None:
                    base = ink(canvas)
                ink_table.append((path.name, label, ppem, ink(canvas) / base))
                cells.append(figure_html(*canvas, text, ppem, figure_id=counter.next("e"), caption=label))
            parts.append(f"<p>{ppem} ppem（本文{ppem * 2}px のルビ）・{html.escape(script)}</p><div class=pair>{''.join(cells)}</div>")
    parts.append(f"<h4>拡大（{LARGE_PPEM}px・ヒントなし。画像は等倍）</h4><div class=pair>")
    for index, (label, multipliers) in enumerate(VARIANTS):
        features = () if multipliers is None else ("ss03",)
        width, height, data = raster(shapers[index], renderers[index], LARGE_TEXT, LARGE_PPEM, em, features)
        parts.append(f'<figure><figcaption>{html.escape(label)}</figcaption>'
                     f'<img alt="{html.escape(LARGE_TEXT)} {LARGE_PPEM}px {html.escape(label)}" src="{png(width, height, data)}" '
                     f'width="{width}" height="{height}"></figure>')
    parts.append("</div>")
    for shaper, renderer in zip(shapers, renderers):
        renderer.close()
        shaper.close()
    return "".join(parts)


def summary_table(rows: list) -> str:
    out = ["<table><thead><tr><th>書体</th><th>FreeType</th><th>環境</th><th>ppem</th>"
           "<th>ヒントの差（画素数 / 濃さの差）</th><th>補強の差（画素数 / 濃さの差）</th><th>通常・ヒントありと試作・ヒントありの差（画素数 / 濃さの差）</th><th>通常・ヒントありと試作・ヒントなしの差（画素数 / 濃さの差）</th>"
           "<th>試作のヒントの差（画素数 / 濃さの差）</th><th>インク（通常ヒントあり / 通常ヒントなし / 試作ヒントなし / 試作ヒントあり）</th></tr></thead><tbody>"]
    for name, interpreter, environment, ppem, t in rows:
        out.append(f"<tr><td>{html.escape(name)}</td><td>{interpreter}</td><td>{html.escape(environment)}</td><td>{ppem}</td>"
                   f"<td>{t['hint'][0]} / {t['hint'][1]:.1f}</td><td>{t['embolden'][0]} / {t['embolden'][1]:.1f}</td>"
                   f"<td>{t['all'][0]} / {t['all'][1]:.1f}</td><td>{t['unhinted_trial'][0]} / {t['unhinted_trial'][1]:.1f}</td><td>{t['trial_hint'][0]} / {t['trial_hint'][1]:.1f}</td>"
                   f"<td>{t['ink_hinted']:.1f} / {t['ink_plain']:.1f} / {t['ink_trial_plain']:.1f} / {t['ink_trial']:.1f}</td></tr>")
    out.append("</tbody></table>")
    return "".join(out)


def ink_table_html(rows: list) -> str:
    names = list(dict.fromkeys(row[0] for row in rows))
    out = ["<table><thead><tr><th>書体</th><th>補強量の組</th>" + "".join(f"<th>{p} ppem</th>" for p in PPEMS) + "</tr></thead><tbody>"]
    for name in names:
        for label, _multipliers in VARIANTS:
            cells = []
            for ppem in PPEMS:
                values = [r[3] for r in rows if r[0] == name and r[1] == label and r[2] == ppem]
                cells.append(f"<td>{sum(values) / len(values):.3f}</td>")
            out.append(f"<tr><td>{html.escape(name)}</td><td>{html.escape(label)}</td>{''.join(cells)}</tr>")
    out.append("</tbody></table>")
    return "".join(out)


INTRO = """<!doctype html><html lang=ja><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>読書 UD ルビ仮名の試作の比較</title><style>
body{font:14px/1.6 system-ui,sans-serif;margin:2rem;color:#222;background:#f8f7f3}
h2{margin-top:3rem}code{overflow-wrap:anywhere}.pair{display:flex;gap:1rem;flex-wrap:wrap}
figure{margin:0;background:white;padding:8px;overflow:auto;max-width:100%}
figcaption{font-size:12px;color:#666;margin-bottom:6px}
svg,img{display:block}
table{border-collapse:collapse;font-size:12px;margin:1rem 0}td,th{border:1px solid #ccc;padding:2px 6px;text-align:right}
td:first-child,td:nth-child(2){text-align:left}details{margin:1rem 0}
</style><h1>ルビ仮名の試作（ss03）の比較</h1>
<p>__VERSION__。<a href=small-type.html>小さい数字のラスタ比較</a> ／ <a href=proof.html>固定版面</a> ／ <a href=specimen.html>文章の見本</a>。
配るフォントの字形は変えていません。各画像は上が実寸、下が同じ画素の4倍表示です（１画像ピクセルを１画面ピクセルに対応させるにはDPR 1・ズーム100%）。FreeType の結果であり、Windows・macOS の実機描画とは別です。</p>
<h2 id=how>見方</h2>
<ul>
<li>ルビは本文の半分の大きさです。本文12〜20pxのルビは6〜10ppemです。</li>
<li><b>ヒントの有無をそろえた比較（1）</b>: 同じ字を「通常・ヒントあり」「通常・ヒントなし」「試作・ヒントなし」「試作・ヒントあり」の4つで並べます。
通常字は元のヒントを持ち、試作字形は原字と同じ命令を持ちます（点の番号だけを指す縦方向の命令で、輪郭の点の構成が原字と同じなため）。「通常・ヒントなし」「試作・ヒントなし」は、
この見本のために FreeType でヒンティングを動かさずに描いたもので（フォントは変えていません）、「通常・ヒントあり」→「通常・ヒントなし」の差がヒントによる差、
「通常・ヒントなし」→「試作・ヒントなし」の差が線の補強（と小書き仮名の拡大）による差、「試作・ヒントなし」→「試作・ヒントあり」の差が試作字形のヒントによる差です。
「通常・ヒントあり」と「試作・ヒントあり」の差は、補強と拡大だけの差に近くなります。64px の拡大も並べます。</li>
<li><b>gasp を守る・守らない描画（2）</b>: フォントの gasp は <code>{7: 10, 65535: 15}</code> で、7ppem 以下はグリッドに合わせません（ヒントを使わない）。
「gasp を守る環境」は、gasp がグリッドに合わせないとする大きさ（6・7ppem）でヒントを使わず、「守らない環境」はどの大きさでもヒントを使う描き方です。
どちらの環境になるかは、アプリと OS によります。FreeType の TrueType 命令の解釈は、v40（今の既定）と v35（昔の Windows に近い）の両方を出します。</li>
<li><b>補強量を広く試す比較（3）</b>: 配るフォントの補強量（Regular 8、Bold 4 ／ 2048 em）を基準に、0（補強なし）・2倍・4倍・横線だけ・縦線だけを並べます。
補強量を変えた字形は、この見本の中だけで作り、配るフォントには入れません。すべてヒントなしで描き、補強量の差だけを見ます。</li>
</ul>
<p>測ってわかったこと: 通常の仮名のヒントは、prep が 8ppem 未満で命令を止めるため、6・7ppem では「gasp を守らない環境」でもヒントなしと同じ画素になります
（gasp の指定と同じ結果）。そのため、この2つの環境の違いは 6・7ppem の仮名には出ません。8ppem 以上のヒントは縦方向だけに効き、v35 と v40 で同じ画素になります。
数値は <a href=#numbers>数値のまとめ</a> にあります。</p>
<p>目次: <a href=#numbers>数値のまとめ</a> ／ __LINKS__</p>
"""


def page() -> str:
    counter = Counter()
    summary, ink_rows = [], []
    sections, links = [], []
    blur = blur_rows([ROOT / "fonts" / spec.output_name(family, weight) for family in spec.FAMILIES for weight in spec.WEIGHTS])
    with tempfile.TemporaryDirectory() as directory:
        for family in spec.FAMILIES:
            for weight in spec.WEIGHTS:
                path = ROOT / "fonts" / spec.output_name(family, weight)
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                anchor = f"{family['key']}-{weight}".lower()
                links.append(f"<a href=#{anchor}>{family['name_ja']} {weight}</a>")
                sections.append(f"<h2 id={anchor}>{family['name_ja']} {weight}</h2><p><code>{digest}</code></p>"
                                f"<h3>0　全グリフの一覧（{LIST_PPEM}px）</h3>{glyph_list_section(path, counter)}"
                                f"<h3>1・2　ヒントの有無と gasp</h3>{hinting_section(path, counter, summary)}"
                                f"<h3>3　補強量</h3>{embolden_section(path, Path(directory), counter, ink_rows)}")
    numbers = ("<h2 id=numbers>数値のまとめ</h2><p>同じ字を同じ位置に描いた2つのラスタの、濃さが違う画素の数と、濃さの差の合計です"
               "（インク1画素分を単位にする。ss03 の対象 194 字の合計）。「ヒントの差」が通常字のヒントによる差、「補強の差」が試作との差です。</p>"
               f"<details><summary>ヒント・補強・gasp ごとの数値</summary>{summary_table(summary)}</details>"
               f"<details><summary>補強量ごとのインクの量（通常・ヒントなしを 1 とした比）</summary>{ink_table_html(ink_rows)}</details>")
    content = (INTRO.replace("__VERSION__", spec.VERSION).replace("__LINKS__", " ／ ".join(links) + " ／ <a href=#blur>ヒントでにじみが増える字</a>")
               + numbers + blur_section(blur) + "\n".join(sections) + "</html>")
    return content, summary, ink_rows, blur


def main() -> int:
    OUTPUT.mkdir(exist_ok=True)
    content, summary, ink_rows, blur = page()
    (OUTPUT / "ruby-trial.html").write_text(content, encoding="utf-8")
    print("dist/ruby-trial.html")
    for name, interpreter, environment, ppem, t in summary:
        print(f"{name} {interpreter} {environment} {ppem}ppem: hint {t['hint'][0]} px / {t['hint'][1]:.1f}, "
              f"embolden {t['embolden'][0]} px / {t['embolden'][1]:.1f}, all {t['all'][0]} px / {t['all'][1]:.1f}, unhinted trial {t['unhinted_trial'][0]} px / {t['unhinted_trial'][1]:.1f}, "
              f"trial hint {t['trial_hint'][0]} px / {t['trial_hint'][1]:.1f}, "
              f"ink {t['ink_hinted']:.1f}/{t['ink_plain']:.1f}/{t['ink_trial_plain']:.1f}/{t['ink_trial']:.1f}")
    worse = [r for r in blur if r[2] > r[1]]
    print(f"blur (v40 gray, 8-10ppem, 4 fonts): {len(worse)} of {len(blur)} glyphs get more boundary blur with hinting; total {sum(r[1] for r in blur):.1f} -> {sum(r[2] for r in blur):.1f}")
    for label, plain, hinted, missing in sorted(worse, key=lambda r: r[2] / r[1], reverse=True):
        print(f"  blur {label}: {plain:.1f} -> {hinted:.1f} ({hinted / plain:.3f}), fonts without instructions {missing}")
    for name in dict.fromkeys(row[0] for row in ink_rows):
        for label, _multipliers in VARIANTS:
            ratios = [f"{sum(r[3] for r in ink_rows if r[:3] == (name, label, ppem)) / len(SAMPLES):.3f}" for ppem in PPEMS]
            print(f"{name} ink ratio to unhinted normal: {label}: " + " ".join(ratios))
    return 0


if __name__ == "__main__":
    sys.exit(main())
