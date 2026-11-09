"""追加漢字・くの字点を、FreeType の実寸・４倍・96ppemで dist/ に描く。

HarfBuzz で vert / vrt2 を組み、FreeType v40 の実際の画素を保存する。字形は元の部品だけから
作ったヒントなしの字。既存字との太さ・接合・２セルの送りの比較用で、目視での合格は記録しない。
"""
import base64
import hashlib
import html
from pathlib import Path

import freetype_render
import harfbuzz_shape
from fontTools.ttLib import TTFont
from proof_page import png, raster
import spec

ROOT = Path(__file__).resolve().parent.parent


def vertical_raster(shaper, renderer, ppem, em):
    columns = ["あ〱い", "あ〳〵い", "あ〲い", "あ〴〵い", "吉𠮷野"]
    width, height = ppem * (len(columns) * 2 + 1), ppem * 7
    canvas = bytearray([255] * (width * height))
    for column, text in enumerate(columns):
        x, y = ppem * (column * 2 + 1.5), ppem
        for gid, cluster, xa, ya, xo, yo in shaper.shape(text, "ja", True):
            left, top, _, cols, rows, bitmap = renderer.render(gid, ppem)
            stride = len(bitmap) // rows if rows else 0
            for by in range(rows):
                yy = round(y - yo * ppem / em) - top + by
                for bx in range(cols):
                    xx = round(x + xo * ppem / em) + left + bx
                    if 0 <= xx < width and 0 <= yy < height:
                        canvas[yy * width + xx] = min(canvas[yy * width + xx], 255 - bitmap[by * stride + bx])
            x += xa * ppem / em
            y -= ya * ppem / em
    return width, height, bytes(canvas)


def enlarge(width, height, pixels, factor=4):
    rows = []
    for y in range(height):
        row = bytes(v for v in pixels[y * width:(y + 1) * width] for _ in range(factor))
        rows.extend([row] * factor)
    return width * factor, height * factor, b"".join(rows)


def save(path, raster_data):
    path.write_bytes(base64.b64decode(png(*raster_data).split(",", 1)[1]))


def main():
    target = ROOT / "dist" / "additions"
    target.mkdir(parents=True, exist_ok=True)
    page = ["<!doctype html><meta charset=utf-8><title>Additional Japanese glyphs</title>",
            "<style>body{margin:2em;font-family:sans-serif}img{image-rendering:pixelated;display:block;margin:1em 0}figure{overflow:auto}code{overflow-wrap:anywhere}</style>",
            "<h1>𠮷・〱・〲 — FreeType v40</h1><p>横: 吉𠮷野 土圭 〱〲 〳〵〴〵。縦（左から）: あ〱い / あ〳〵い / あ〲い / あ〴〵い / 吉𠮷野。</p>",
            "<p>12・14・16px の元画像と同じ画素の４倍。96px は輪郭の確認用。実寸は DPR 1・ズーム100%。新しい字はヒントなし。自動描画資料であり、アプリ・印刷の目視確認を済ませた記録ではありません。</p>"]
    for family in spec.FAMILIES:
        for weight in spec.WEIGHTS:
            path = ROOT / "fonts" / spec.output_name(family, weight)
            font = TTFont(path)
            em = font["head"].unitsPerEm
            shaper = harfbuzz_shape.Shaper(path)
            renderer = freetype_render.Renderer(path, 40, 0)
            page += [f"<h2>{path.stem}</h2><code>SHA-256 {hashlib.sha256(path.read_bytes()).hexdigest()}</code>"]
            for ppem in (12, 14, 16, 96):
                for direction in ("h", "v"):
                    data = (raster(shaper, renderer, "吉𠮷野 土圭 〱〲 〳〵〴〵", ppem, em) if direction == "h"
                            else vertical_raster(shaper, renderer, ppem, em))
                    name = f"{path.stem}-{ppem}-{direction}"
                    save(target / (name + ".png"), data)
                    page += [f"<figure><figcaption>{ppem}px / {direction}</figcaption><img alt='{html.escape(name)}' src='additions/{name}.png'>"]
                    if ppem != 96:
                        save(target / (name + "-4x.png"), enlarge(*data))
                        page += [f"<img alt='4× {html.escape(name)}' src='additions/{name}-4x.png'>"]
                    page += ["</figure>"]
            renderer.close()
            shaper.close()
            font.close()
    (ROOT / "dist" / "additions.html").write_text("\n".join(page), encoding="utf-8")
    print("dist/additions.html; dist/additions/*.png (4 fonts, 12/14/16px + 4x; 96px)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
