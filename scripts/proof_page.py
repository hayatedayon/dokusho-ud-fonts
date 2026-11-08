"""固定版面の校正ページと、小さい字の FreeType ラスタ比較を dist/ に作る。

python3 scripts/proof_page.py

依存は build/check と同じ。PNG は標準ライブラリで作り、ブラウザに埋め込む。実寸と４倍を
並べるので、ブラウザの描画によらず、ビルド済みフォントのヒントあり・なしを比較できる（１画像ピクセルを１画面ピクセルに対応させるには DPR 1・ズーム100%）。
OS 固有の描画や実際の印刷結果は proof.html を各環境で開いて確認する。
"""

import base64
import hashlib
import html
import json
import struct
import sys
import unicodedata
import zlib
from pathlib import Path

from fontTools.ttLib import TTFont

import freetype_render
import harfbuzz_shape
import small_type
import spec
from specimen_page import FEATURE_SETTINGS, font_faces, fonts

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "dist"

TEXT = """<h1>雨の日の読書</h1>
<p>　窓の外では、朝から静かな雨が降っている。机の上に一冊の本を開くと、昨日まで気づかなかった一文が目に留まった。「急がなくていい。『読む』という時間を、もう少し楽しもう」。私は栞を抜き、物語の続きへ戻った。</p>
<p>　<ruby>雨<rt>あめ</rt></ruby>に<ruby>濡<rt>ぬれ</rt></ruby>た<ruby>客<rt>きゃく</rt></ruby>が、扉を三度たたいた。小さな<ruby>葉<rt>はっぱ</rt></ruby>を肩に載せて、「この手紙を届けてください」と言う。時計は<span class="tcy">12</span>時<span class="tcy">24</span>分を指していた――そのとき、遠くで汽笛が鳴った……。</p>
<p>　彼女は“本当？”と聞き返した。Alice’s Adventures in Wonderland の一節に似ている。ページには「（注）」「『引用』」、疑問符！？、二倍ダッシュ⸺、三倍ダッシュ⸻が並んでいた。</p>
<p lang="en">To read is to travel. AVATAR, WA, Tu, Tũ, Tų, Te, LT, Tó and ÁV test the spacing of Latin letters. “Take your time,” Alice said. Fine flowers filled the valley.</p>
<p>　資料の刊行年は2011年、改訂は2026年。比率は<span class="frac">1/2</span>、温度は35°C、変化率は−3.5%。指数10<span class="sups">−3</span>、化学式H<span class="subs">2</span>O、時刻11:11を、本文と同じ大きさで組む。</p>
<p class="tabular">　目次の数字　1　17　111　1081<br>　pnum で戻す　<span class="pnum">1　17　111　1081</span></p>
<p>　読点の次に（括弧）が来る所、句点の後に「会話」が始まる所も確かめる。行末・行頭の禁則、和欧間のアキ、ルビの配置は、使用する組版環境の結果を比較する。</p>"""

PROOF = """<!doctype html><html lang="ja"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>読書 UD 固定版面</title>
<style>__FACES__
body { margin:0; background:#eee; color:#222; font-family:system-ui,sans-serif; }
header { padding:1rem; background:white; display:flex; flex-wrap:wrap; gap:.8rem; }
label { white-space:nowrap; } .note { padding:0 1rem; font-size:13px; }
main { overflow:auto; padding:1rem; }
.proof { font-family:var(--family); font-weight:var(--weight,400); font-size:var(--size,14px);
  inline-size:32em; block-size:50em; padding:1.5em; background:white; line-height:1.75;
  text-align:justify; text-spacing-trim:normal; text-autospace:normal; overflow:auto;
  --chws:1; --vchw:0; }
.proof.vertical { page:vertical-proof; writing-mode:vertical-rl; --chws:0; --vchw:1; }
.proof, .proof :is(h1,.tcy,.frac,.sups,.subs,.pnum,rt) {
  __FEATURE_SETTINGS__ }
h1 { font-size:1.4em; font-weight:inherit; margin:0; margin-block-end:1em; --palt:1; --chws:0; --vchw:0;
  text-spacing-trim:space-all; }
.vertical h1 { --palt:0; --vpal:1; }
p { margin:0; margin-block-end:.7em; } rt { font-size:.5em; --ss03:var(--ruby-trial,0); }
.vertical .tcy { text-combine-upright:all; --hwid:1; } .frac { --frac:1; }
.sups { --sups:1; } .subs { --subs:1; } .tabular { font-variant-numeric:tabular-nums; }
.pnum { --pnum:1; }
@page { size:A4; margin:12mm; }
@page vertical-proof { size:A4 landscape; margin:12mm; }
@media print { body, main { background:white; margin:0; padding:0; }
  main { overflow:visible; }
  header,.note { display:none; } .proof { padding:0; overflow:visible; } }
</style>
<header>
<label>書体 <select id="font">__OPTIONS__</select></label>
<label>大きさ <select id="size"><option>12px</option><option selected>14px</option><option>16px</option>
<option>9pt</option><option>10pt</option><option>11pt</option><option>12pt</option></select></label>
<label><input id="vertical" type="checkbox">縦組</label>
<label><input id="kern" type="checkbox" checked>カーニング</label>
<label><input id="ss01" type="checkbox">和文引用符</label>
<label><input id="ss02" type="checkbox">欧文記号</label>
<label><input id="ruby-trial" type="checkbox">ルビ仮名の試作</label>
<button id="print">印刷・PDF保存</button>
</header>
<p class="note">１行32字分・50emの奥行き・行送り1.75の固定版面。バージョン __VERSION__。
横組・縦組と大きさを切り替えて比較してください。印刷は倍率100%を選びます（縦組はA4横向き）。
ルビ仮名の試作は20字だけに適用されます。<a href="small-type.html">ラスタ比較</a> ／ <a href="specimen.html">文章の見本</a></p>
<main><article id="proof" class="proof">__TEXT__</article></main>
<script>
const fonts = __FONTS__;
function update() {
 const box=document.getElementById('proof'), font=fonts[document.getElementById('font').selectedIndex];
 box.style.setProperty('--family', `'${font.id}'`);
 box.style.setProperty('--weight', font.weight === 'Bold' ? 700 : 400);
 box.style.setProperty('--size', document.getElementById('size').value);
 box.classList.toggle('vertical', document.getElementById('vertical').checked);
 for (const id of ['kern','ss01','ss02','ruby-trial'])
   box.style.setProperty('--'+id, document.getElementById(id).checked ? 1 : 0);
}
document.querySelectorAll('input,select').forEach(e=>e.addEventListener('change',update));
document.getElementById('print').addEventListener('click',()=>window.print());
update();
</script></html>"""


def proof() -> str:
    available = fonts()
    options = "".join(f"<option>{html.escape(font['label'])}</option>" for font in available)
    return (PROOF.replace("__FACES__", font_faces(available)).replace("__FEATURE_SETTINGS__", FEATURE_SETTINGS).replace("__OPTIONS__", options)
            .replace("__FONTS__", json.dumps(available, ensure_ascii=False)).replace("__TEXT__", TEXT)
            .replace("__VERSION__", spec.VERSION))


def png(width: int, height: int, pixels: bytes) -> str:
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    scanlines = b"".join(b"\0" + pixels[y * width:(y + 1) * width] for y in range(height))
    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(scanlines)) + chunk(b"IEND", b""))
    return "data:image/png;base64," + base64.b64encode(data).decode()


def raster(shaper, renderer, text: str, ppem: int, em: int, features=()) -> tuple[int, int, bytes]:
    shaped = shaper.shape(text, "ja", features=features)
    width = max(1, round(sum(r[2] for r in shaped) * ppem / em) + 2 * ppem)
    height = 2 * ppem
    canvas = bytearray([255] * (width * height))
    x = ppem
    for gid, _c, advance, _ya, dx, dy in shaped:
        left, top, _a, cols, rows, bitmap = renderer.render(gid, ppem)
        stride = len(bitmap) // rows if rows else 0
        for by in range(rows):
            yy = round(ppem * 1.15 - dy * ppem / em) - top + by
            if not 0 <= yy < height:
                continue
            for bx in range(cols):
                xx = round(x + dx * ppem / em) + left + bx
                if 0 <= xx < width:
                    i = yy * width + xx
                    canvas[i] = min(canvas[i], 255 - bitmap[by * stride + bx])
        x += advance * ppem / em
    return width, height, bytes(canvas)


def raster_figure(shaper, renderer, text: str, ppem: int, em: int, features=(), *, figure_id: str, caption: str = "") -> str:
    """PNG を一度だけ埋め込み、SVG の参照で実寸と４倍を並べる。figure_id はページ内で一意。"""
    width, height, data = raster(shaper, renderer, text, ppem, em, features)
    uri = png(width, height, data)
    alt = html.escape(f"{text} {ppem}px 実寸", quote=True)
    image_id = html.escape(figure_id, quote=True)
    label = f'<figcaption>{html.escape(caption)}</figcaption>' if caption else ""
    return (f'<figure>{label}<svg xmlns="http://www.w3.org/2000/svg" width="{width*4}" height="{height*5+8}" '
            f'role="img" aria-label="{alt}、下段は同じ画素を4倍で表示">'
            f'<defs><image id="{image_id}" href="{uri}" width="{width}" height="{height}" '
            f'style="image-rendering:pixelated" /></defs>'
            f'<use href="#{image_id}" />'
            f'<path d="M0 {height+4} H{width*4}" stroke="#ddd" />'
            f'<use href="#{image_id}" transform="translate(0 {height+8}) scale(4)" />'
            '</svg></figure>')


def small_page() -> str:
    rows = []
    ruby_samples = ["".join(char for char in small_type.RUBY_KANA if unicodedata.name(char).startswith(script))
                    for script in ("HIRAGANA", "KATAKANA")]
    for family in spec.FAMILIES:
        for weight in spec.WEIGHTS:
            path = ROOT / "fonts" / spec.output_name(family, weight)
            font = TTFont(path)
            shaper = harfbuzz_shape.Shaper(path)
            em = font["head"].unitsPerEm
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            rows.append(f"<h2>{family['name_ja']} {weight}</h2><p><code>{digest}</code></p>")
            for interpreter in (35, 40):
                hinted = freetype_render.Renderer(path, interpreter, 0)
                plain = freetype_render.Renderer(path, interpreter, freetype_render.NO_HINTING)
                rows.append(f"<h3>FreeType v{interpreter}・数字</h3>")
                for ppem in (12, 14, 16, 18):
                    for text, features in [("¹²³⁴⁵⁶⁷⁸⁹⁰", ()), ("0123456789", ("numr",)),
                                           ("0123456789", ("dnom",)), ("0123456789", ("subs",)),
                                           ("1/2 4/5 10/25", ("frac",))]:
                        cells = []
                        for renderer in (hinted, plain):
                            cells.append(raster_figure(shaper, renderer, text, ppem, em, features,
                                                       figure_id=f"raster-{len(rows)}-{len(cells)}",
                                                       caption="ヒントあり" if renderer is hinted else "ヒントなし"))
                        rows.append(f"<p>{ppem} ppem・{html.escape(text)} {' '.join(features)}</p><div class=pair>{''.join(cells)}</div>")
                hinted.close()
                plain.close()
            renderer = freetype_render.Renderer(path, 40, 0)
            rows.append("<h3>ルビ仮名（通常と ss03 の試作）</h3>")
            for ppem in (6, 7, 8, 10):
                for text in ruby_samples:
                    cells = []
                    for features in ((), ("ss03",)):
                        cells.append(raster_figure(shaper, renderer, text, ppem, em, features,
                                                       figure_id=f"raster-{len(rows)}-{len(cells)}",
                                                       caption="通常（元のヒント）" if not features else "試作（ヒントなし）"))
                    rows.append(f"<p>{ppem} ppem・{html.escape(text)}</p><div class=pair>{''.join(cells)}</div>")
            renderer.close()
            shaper.close()
            font.close()
    return """<!doctype html><html lang=ja><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>読書 UD 小さい字の比較</title><style>
body{font:14px system-ui,sans-serif;margin:2rem;color:#222;background:#f8f7f3}
h2{margin-top:3rem}code{overflow-wrap:anywhere}.pair{display:flex;gap:1rem;flex-wrap:wrap}
figure{margin:0;background:white;padding:8px;overflow:auto;max-width:100%}
figcaption{font-size:12px;color:#666;margin-bottom:6px}
svg{display:block}
</style><h1>小さい数字とルビ仮名</h1><p>__VERSION__。各画像は上が実寸、下が同じ画素の4倍表示です。１画像ピクセルを１画面ピクセルに対応させるにはDPR 1・ズーム100%で見てください。高DPI画面ではCSSピクセルに拡大されます。
数字は描画時のヒント有無を比較します。分子（numr）・分母（dnom）・下付き（subs）と18ppemの例も並べています。上付き¹²³⁴は元のヒントを保っています。ルビの通常字にはヒントがありますが、試作字形にはありません。ルビの比較には字形とヒント有無の両方の差が含まれます。見た目の好ましさや読みやすさは実寸で判断してください。
FreeType の結果であり、Windows・macOS の実機描画とは別です。<a href=proof.html>固定版面</a> ／ <a href=specimen.html>文章の見本</a></p>""".replace("__VERSION__", spec.VERSION) + "\n".join(rows) + "</html>"


def main() -> int:
    OUTPUT.mkdir(exist_ok=True)
    for name, content in (("proof.html", proof()), ("small-type.html", small_page())):
        (OUTPUT / name).write_text(content, encoding="utf-8")
        print(f"dist/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
