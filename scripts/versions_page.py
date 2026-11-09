"""公開した各版を文字で見比べるページ (dist/versions.html) を作る。

各版のフォントを GitHub のリリースから dist/releases/ に取ってきて、ページで使う字だけのサブセットにして埋め込む。
1 つのファイルで完結するので、ブラウザで直接開ける。fonts/ のフォントは「未公開」の版として最後に並ぶ。
見本ごとに、前の版とこの版を HarfBuzz で組んで比べ、差が出ない見本があれば止める (説明と実物がずれないように)。

    python3 scripts/versions_page.py
"""

import base64
import hashlib
import html
import io
import re
import sys
import urllib.request
from functools import lru_cache
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

import freetype_render
import harfbuzz_shape
import proof_page
import readme_images
import spec

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "dist" / "versions.html"
RELEASES = ROOT / "dist" / "releases"
REPOSITORY = "https://github.com/hayatedayon/dokusho-ud-fonts"
UNRELEASED = "1.007"
BASE = "BIZ UD"
WEIGHTS = ("Regular", "Bold")
FEATURES = ["locl", "ccmp", "mark", "mkmk", "liga", "calt", "kern", "vert", "vrt2", "halt", "vhal", "palt", "vpal",
            "chws", "vchw", "hwid", "fwid", "frac", "numr", "dnom", "sups", "subs", "sinf", "tnum", "pnum", "zero",
            "ss01", "ss02", "ss03"]


class Demo:
    def __init__(self, label, text, note="", language="ja", features=(), vertical=False, markup=None):
        self.label, self.text, self.note, self.language = label, text, note, language
        self.features, self.vertical, self.markup = tuple(features), vertical, markup


class Raster:
    """ブラウザでは差が見えないヒンティングは、FreeType で描いた画素で見せる"""

    def __init__(self, label, text, sizes, note="", features=()):
        self.label, self.text, self.sizes, self.note, self.features = label, text, sizes, note, tuple(features)


VERSIONS = [
    ("1.001", "2026-11-03", "BIZ UD の欧字を、同じデザインの BIZ UDP の字に", [
        Demo("欧文の本文", "Alice was beginning to get very tired", "BIZ UD の欧字は半角の等幅で、i も W も同じ幅でした。", "en"),
        Demo("和欧混植", "画面にHello, worldと出た午後3時", "仮名と漢字は全角のまま、欧字だけが字ごとの幅になります。"),
    ]),
    ("1.002", "2026-11-03", "続く約物を詰める halt・vhal を追加", [
        Demo("約物の半角 (halt)", "「（はい）」、「いいえ」。",
             "ブラウザの text-spacing-trim や組版アプリは、この機能で括弧の余分なアキを取ります。", features=["halt"]),
    ]),
    ("1.003", "2026-11-04", "欧文の中の記号を BIZ UDP の字に", [
        Demo("欧文の中の引用符", "“It’s alive!” she said.", "全角だった引用符とアポストロフィが、欧文の幅になりました。", "en"),
        Demo("欧文の中の記号", "© 2026 † €100 – ‘quoted’", "", "en"),
    ]),
    ("1.004", "2026-11-04", "欧字に BIZ UDP のヒンティングを付与", [
        Raster("小さい欧字の画素", "Typography 2026", (11, 13),
               "FreeType (v40) の描画です。Windows など、ヒンティングが効く環境で差が出ます。高解像度の画面では差はほとんど見えません。"),
    ]),
    ("1.005", "2026-11-08", "和文の記号の修正、分数・上付き・下付き・tnum・palt など多数", [
        Demo("ダッシュ", "彼は——そう言った", "BIZ UD の — は半角で、—— が全角 1 字分にしかなりませんでした。"),
        Demo("度とマイナス", "気温は35°C、昨日は−5°C", "° の後の空きと、+ より短かった − を直しました。"),
        Demo("感嘆符と分数の字", "本当‼ 約½か¾", "半角に押し込まれていた ‼ や分数が、本来の幅になりました。"),
        Demo("和文の中の引用符", "画面に“Hello”と出た", "開きと閉じで別の幅になる問題を避けるため、和文の中でも欧文の字にしました。"),
        Demo("ピンインと IPA", "nǐ hǎo ə ƒ ﬁ", "語の途中で全角・半角に分かれていた字が、続いて読めるようになりました。", "en"),
        Demo("分数 (frac)", "1/2 10/25 3/8", "1.004 までは 1 2 3 が上がるだけで、4/5 などは変わりませんでした。", features=["frac"]),
        Demo("上付きと下付き", "10⁻³ x⁵ H₂O", "点線の枠は、その版に無かった字です。"),
        Demo("等幅の数字 (tnum)", "1111 2026", "BIZ UDP の 1 は他の数字より狭いので、揃える機能を足しました。", features=["tnum"]),
        Demo("数字の間のコロン", "午後11:11", "数字の間で低く見えたコロンを、数字の中央に上げます。"),
        Demo("結合用の記号", "q̃ あ゙ か゚", "記号が次の字の位置にずれていたのを、前の字の上に置きます。"),
        Demo("縦中横 (hwid)", "12月24日",
             "点線が 1 字の枠です。1.005 の hwid は半角の数字になり、2 桁がちょうど収まります。1.004 は幅の広い数字のままで、はみ出します。"
             "text-combine-upright はブラウザが字を自動で詰めるので、この見本では枠にそのまま組んでいます。",
             features=["hwid"], vertical=True, markup='<span class="tcy">12</span><span>月</span><span class="tcy">24</span><span>日</span>'),
        Demo("見出しの詰め (palt)", "「読書」のためのフォント", "本文はベタ組のまま、見出しだけ字ごとの幅にできます。", features=["palt"]),
        Demo("新しい字", "〝読書〟 〝読書〞 ⸺ ⸻",
             "日本語の二重引用符の通常の閉じは右下の 〟 で、前の版にもありました。追加した U+301E の 〞 は右上に置く字です。"
             "2 倍・3 倍のダッシュも追加しました。点線の枠は、その版に無かった字です。"),
    ]),
    ("1.006", "2026-11-08", "WOFF2 の配布を追加 (字は変更なし)", []),
    (UNRELEASED, "未公開", "欧字のカーニング、スタイルセット、小さい数字のヒンティング", [
        Demo("カーニング", "AVATAR To Te WAVE You", "頻出のペアを控えめに詰めます。既定で有効です。", "en"),
        Demo("二重引用符 〞 の向き", "〝読書〞", "〞 を 〝 と左右対称の向きに直しました。位置と幅は変わりません。"),
        Demo("縦組の引用符", "字“読”字と‘本’", "縦組では “ ” を 〝 〟 の形、‘ ’ をその 1 画の形で全角の枠に組みます。文字は変わりません。",
             vertical=True, markup='<span class="vtext">字“読”字と‘本’</span>'),
        Demo("等幅の解除 (pnum)", "1111 2026", "tnum と併用しても、字ごとの幅に戻せます。", features=["tnum", "pnum"]),
        Demo("和文引用符 (ss01)", "“読書”と‘本’", "引用符を BIZ UD の全角の字に戻します。任意の機能です。", features=["ss01"]),
        Demo("欧文記号 (ss02)", "© † € ×", "日本語の文書でも、対象の記号を BIZ UDP の字にします。任意の機能です。", features=["ss02"]),
        Demo("ルビ仮名の試作 (ss03)", "あめぬれゃゅょっがぱ", "線をわずかに強め、小書きの字を 12% 大きくした試作です。任意の機能です。", features=["ss03"]),
        Raster("小さい分数の画素", "1/2 3/8 10/25", (12, 14), "生成した数字の上下を揃えるヒンティングの差です。FreeType (v40) の描画です。", features=["frac"]),
    ]),
]

SAMPLES = [
    ("和欧混植", "彼女は「It’s alive!」と叫んだ", "ja", ()),
    ("欧文の本文", "Alice was very tired", "en", ()),
    ("欧文の記号", "“Hello” © 2026 † €100", "en", ()),
    ("和文の記号", "彼は——35°Cと言った‼", "ja", ()),
    ("分数", "1/2 10/25", "ja", ("frac",)),
    ("カーニング", "AVATAR To You", "en", ()),
    ("約物の半角", "「（はい）」、", "ja", ("halt",)),
]

ORDER = [BASE] + [version for version, *_ in VERSIONS]


def tag_of(version: str) -> str:
    return f"v{version[0]}.{version[2]}.{int(version[3:])}" if len(version) == 5 else version


def source_path(version: str, family: dict, weight: str) -> Path:
    if version == BASE:
        return ROOT / "sources" / f"{family['ud']}-{weight}.ttf"
    if version == UNRELEASED:
        return ROOT / "fonts" / spec.output_name(family, weight)
    tag = tag_of(version)
    name = spec.output_name(family, weight)
    target = RELEASES / tag / name
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        url = f"{REPOSITORY}/releases/download/{tag}/{name}"
        print(f"fetch {url}")
        with urllib.request.urlopen(url) as response:
            target.write_bytes(response.read())
    return target


def cell_shape(shaper: harfbuzz_shape.Shaper, font: TTFont, demo) -> list[tuple]:
    """字形と配置の比較用。グリフの番号は版で変わるので輪郭のハッシュにする"""
    order, glyf, result = font.getGlyphOrder(), font["glyf"], []
    language, vertical = getattr(demo, "language", "ja"), getattr(demo, "vertical", False)
    for part, script in readme_images.runs(demo.text):
        for gid, _c, xa, ya, dx, dy in shaper.shape(part, language, vertical, demo.features, script):
            glyph = glyf[order[gid]]
            coordinates = glyph.getCoordinates(glyf)[0]
            result.append((hashlib.sha256(repr(list(coordinates)).encode()).hexdigest()[:10], xa, ya, dx, dy))
    return result


def face_css(name: str, path: Path, weight: str, text: str) -> tuple[str, int]:
    options = subset.Options()
    options.layout_features = FEATURES
    options.flavor = "woff2"
    options.hinting = False
    options.notdef_outline = True
    options.name_IDs = [1, 2]
    options.ignore_missing_unicodes = True
    options.ignore_missing_glyphs = True
    font = subset.load_font(str(path), options)
    subsetter = subset.Subsetter(options)
    subsetter.populate(text=text)
    subsetter.subset(font)
    buffer = io.BytesIO()
    subset.save_font(font, buffer, options)
    data = buffer.getvalue()
    encoded = base64.b64encode(data).decode()
    bold = 700 if weight == "Bold" else 400
    return (f"@font-face{{font-family:'{name}';font-weight:{bold};font-display:block;"
            f"src:url(data:font/woff2;base64,{encoded}) format('woff2')}}"), len(data)


def css_features(features) -> str:
    return ",".join(f'"{feature}" 1' for feature in features)


@lru_cache(maxsize=None)
def coverage(version: str) -> frozenset[int]:
    """全ウェイトに共通して収録されている字"""
    maps = [TTFont(source_path(version, f, w)).getBestCmap().keys() for f in spec.FAMILIES for w in WEIGHTS]
    return frozenset(set.intersection(*map(set, maps)))


def marked(version: str, text: str) -> str:
    """その版に無い字は、環境の別のフォントで出ないように点線の枠にする"""
    return "".join('<span class="missing" role="img" aria-label="この版に無い字" title="この版に無い字"></span>'
                   if ord(char) not in coverage(version) else html.escape(char) for char in text)


def cell(version: str, demo, extra: str = "") -> str:
    style = f' style="font-feature-settings:{html.escape(css_features(demo.features))}"' if demo.features else ""
    vertical = getattr(demo, "vertical", False)
    classes = "sample vertical" if vertical else "sample"
    if vertical:
        extra += " vrow"
    body = demo.markup if getattr(demo, "markup", None) else marked(version, demo.text)
    return (f'<div class="row{extra}"><span class="version-tag">{version}</span>'
            f'<div class="{classes}" data-v="{version}" lang="{demo.language}"{style}>{body}</div></div>')


def raster_block(item: Raster, before: str, after: str, serial: list[int]) -> str:
    groups = []
    for family in spec.FAMILIES:
        rows = []
        for size in item.sizes:
            for version in (before, after):
                path = source_path(version, family, "Regular")
                font = TTFont(path)
                shaper = harfbuzz_shape.Shaper(path)
                renderer = freetype_render.Renderer(path, 40, 0)
                serial[0] += 1
                figure = proof_page.raster_figure(shaper, renderer, item.text, size, font["head"].unitsPerEm, item.features,
                                                  figure_id=f"raster-{serial[0]}", caption=f"{version}・{size}px")
                rows.append(figure)
                renderer.close()
                shaper.close()
        groups.append(f'<div class="raster" data-family="{family["key"]}">{"".join(rows)}</div>')
    return "".join(groups)


def changes(previous: str, current: str) -> list[str]:
    """Mincho Regular の表から、この版で変わった量を数える"""
    family = spec.FAMILIES[0]
    old, new = TTFont(source_path(previous, family, "Regular")), TTFont(source_path(current, family, "Regular"))
    old_map, new_map = old.getBestCmap(), new.getBestCmap()
    tags = lambda font, table: {r.FeatureTag for r in font[table].table.FeatureList.FeatureRecord} if table in font else set()
    added = sorted((tags(new, "GSUB") | tags(new, "GPOS")) - (tags(old, "GSUB") | tags(old, "GPOS")))
    shape_changed = 0
    for code in old_map.keys() & new_map.keys():
        a, b = old_map[code], new_map[code]
        if (old["hmtx"][a][0] != new["hmtx"][b][0]
                or list(old["glyf"][a].getCoordinates(old["glyf"])[0]) != list(new["glyf"][b].getCoordinates(new["glyf"])[0])):
            shape_changed += 1
    facts = []
    if new_map.keys() - old_map.keys():
        facts.append(f"追加した字 {len(new_map.keys() - old_map.keys())}")
    if shape_changed:
        facts.append(f"形か幅が変わった字 {shape_changed}")
    if added:
        facts.append("新しい機能 " + " ".join(added))
    return facts or ["字と機能の変更なし"]


def matrix(shaped: dict) -> str:
    blocks = []
    for index, (label, text, language, features) in enumerate(SAMPLES):
        demo = Demo(label, text, language=language, features=features)
        rows, previous = [], None
        for version in ORDER:
            signature = shaped[(index, version)]
            changed = previous is not None and signature != previous
            rows.append(cell(version, demo, " changed" if changed else ""))
            previous = signature
        hidden = "" if index == 0 else " hidden"
        blocks.append(f'<div class="matrix" data-sample="{index}"{hidden}>{"".join(rows)}</div>')
    options = "".join(f'<option value="{i}">{html.escape(s[0])}</option>' for i, s in enumerate(SAMPLES))
    return f'<label class="control">見本 <select id="sample">{options}</select></label>{"".join(blocks)}'


STYLE = """
/* 校正刷りのように、同じ文を上下に重ねて差を読むページ。 */
[hidden]{display:none!important}
:root{--paper:#f3f6f9;--sheet:#ffffff;--ink:#17212c;--muted:#566474;--rule:#d3dbe3;--accent:#a8322a;--wash:#fbeeec;
--ui:'UI Gothic',system-ui,sans-serif;--title:'UI Mincho',serif}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--paper:#10161d;--sheet:#18212b;--ink:#e6edf3;--muted:#9fadbb;--rule:#303d4a;--accent:#f0907f;--wash:#35211f;color-scheme:dark}}
:root[data-theme="dark"]{--paper:#10161d;--sheet:#18212b;--ink:#e6edf3;--muted:#9fadbb;--rule:#303d4a;--accent:#f0907f;--wash:#35211f;color-scheme:dark}
body{background:var(--paper);color:var(--ink);font-family:var(--ui);font-size:15px;line-height:1.7;margin:0;
padding-block:0 4rem;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
main,header.top{max-width:60rem;margin-inline:auto}
header.top{padding-block:2.5rem 1rem;display:grid;gap:.6rem}
h1{font-family:var(--title);font-weight:700;font-size:2.1rem;line-height:1.3;margin:0;text-wrap:balance}
.lead{margin:0;max-width:40em;color:var(--muted)}
nav.toc{display:flex;flex-wrap:wrap;gap:.25rem .9rem;font-variant-numeric:tabular-nums}
a{color:var(--accent)}
.controls{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;background:var(--paper);padding-block:.6rem;display:flex;flex-wrap:wrap;gap:1rem;border-bottom:1px solid var(--rule);max-width:60rem;margin-inline:auto}
body::before{content:"";position:fixed;inset:0 0 auto;height:env(safe-area-inset-top,0px);z-index:10;background:var(--paper)}
.control{display:inline-flex;align-items:center;gap:.4rem;color:var(--muted)}
select{font:inherit;color:var(--ink);background:var(--sheet);border:1px solid var(--rule);padding:.15rem .4rem}
select:focus-visible,a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
section{padding-top:2.5rem;display:grid;gap:1rem;scroll-margin-top:3.5rem}
.version-head{display:grid;grid-template-columns:auto 1fr;column-gap:1rem;align-items:baseline;border-bottom:2px solid var(--ink);padding-bottom:.4rem}
h2{font-family:var(--title);font-size:2rem;margin:0;font-variant-numeric:tabular-nums}
.date{color:var(--muted);font-variant-numeric:tabular-nums;justify-self:end}
.summary{grid-column:1/-1;margin:0;font-size:1.1rem}
.facts{grid-column:1/-1;margin:.2rem 0 0;color:var(--muted);font-size:.87rem;overflow-wrap:anywhere}
.demo{background:var(--sheet);padding:.9rem 1rem;display:grid;gap:.4rem;min-width:0}
h3{font-size:.95rem;margin:0;font-weight:700}
.note{margin:0;color:var(--muted);font-size:.88rem}
.row{display:grid;grid-template-columns:3.6rem minmax(0,1fr);align-items:baseline;gap:.5rem;padding-block:.15rem}
.row.after .version-tag,.row.changed .version-tag{color:var(--accent);font-weight:700}
.row.changed{background:var(--wash)}
.version-tag{font-size:.8rem;color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}
.sample{font-size:1.9rem;line-height:1.5;overflow-x:auto;white-space:nowrap;min-width:0;font-weight:var(--weight,400)}
.vertical{display:flex;flex-direction:column;align-items:center;width:1em;overflow:visible;line-height:1.2}
.vpair{display:flex;flex-wrap:wrap;gap:3.5rem;padding-block:.3rem}
.row.vrow{display:grid;grid-template-columns:none;justify-items:center;gap:.4rem}
.vtext{writing-mode:vertical-rl;text-orientation:mixed;white-space:nowrap}
.tcy{display:flex;justify-content:center;align-items:center;width:1em;height:1.2em;line-height:1;white-space:nowrap;outline:1px dashed var(--muted);outline-offset:-1px}
.missing{display:inline-block;width:.8em;height:.8em;margin-inline:.1em;border:1.5px dashed var(--muted);vertical-align:-.05em;box-sizing:border-box}
.raster{display:none;gap:.5rem;flex-wrap:wrap}
.raster figure{margin:0;background:#fff;color:#333;padding:.4rem;overflow-x:auto;max-width:100%}
.raster figcaption{font-size:.8rem;margin-bottom:.2rem;font-variant-numeric:tabular-nums}
.raster svg{display:block}
.matrix{display:grid;gap:.1rem;background:var(--sheet);padding:.6rem 1rem}
.empty{margin:0;color:var(--muted);background:var(--sheet);padding:.9rem 1rem}
footer{max-width:60rem;margin:3rem auto 0;color:var(--muted);font-size:.85rem}
.mincho .raster[data-family="Mincho"],.gothic .raster[data-family="Gothic"]{display:flex}
@media (max-width:480px){.sample{font-size:1.45rem}.row{grid-template-columns:3.1rem minmax(0,1fr)}h1{font-size:1.6rem}}
"""

SCRIPT = """
const root=document.documentElement;
const family=document.getElementById('family'),weight=document.getElementById('weight'),sample=document.getElementById('sample');
function apply(){root.classList.toggle('mincho',family.value==='Mincho');root.classList.toggle('gothic',family.value==='Gothic');
root.style.setProperty('--weight',weight.value)}
family.addEventListener('change',apply);weight.addEventListener('change',apply);
sample.addEventListener('change',()=>document.querySelectorAll('.matrix').forEach(m=>{m.hidden=m.dataset.sample!==sample.value}));
apply();
"""


def main() -> int:
    missing = [p for f in spec.FAMILIES for w in WEIGHTS for p in [source_path(BASE, f, w), source_path(UNRELEASED, f, w)] if not p.exists()]
    if missing:
        raise SystemExit(f"run fetch_sources.py and build.py first: {missing[0]}")
    # 本文を組み立てる前に、見本の差を確かめる
    fonts = {v: TTFont(source_path(v, spec.FAMILIES[0], "Regular")) for v in ORDER}
    shapers = {v: harfbuzz_shape.Shaper(source_path(v, spec.FAMILIES[0], "Regular")) for v in ORDER}
    failures = []
    sections, serial = [], [0]
    for position, (version, date, summary, demos) in enumerate(VERSIONS):
        previous = ORDER[position]
        items = []
        for demo in demos:
            if isinstance(demo, Raster):
                body = raster_block(demo, previous, version, serial)
            else:
                if cell_shape(shapers[previous], fonts[previous], demo) == cell_shape(shapers[version], fonts[version], demo):
                    failures.append(f"{version} {demo.label}: no difference from {previous}")
                body = cell(previous, demo) + cell(version, demo, " after")
                if demo.vertical:
                    body = f'<div class="vpair">{body}</div>'
            note = f'<p class="note">{html.escape(demo.note)}</p>' if demo.note else ""
            items.append(f'<div class="demo"><h3>{html.escape(demo.label)}</h3>{body}{note}</div>')
        if not demos:
            items.append('<p class="empty">文字の形と組み方は前の版と同じです。配布物に WOFF2 が加わりました。</p>')
        heading = f"{version}（未公開）" if version == UNRELEASED else version
        facts = "　".join(changes(previous, version))
        anchor = "v" + version.replace(".", "")
        release = "" if version == UNRELEASED else f' <a href="{REPOSITORY}/releases/tag/{tag_of(version)}">リリース</a>'
        sections.append(f'<section id="{anchor}"><div class="version-head"><h2>{heading}</h2>'
                        f'<span class="date">{date}{release}</span><p class="summary">{html.escape(summary)}</p>'
                        f'<p class="facts">{html.escape(facts)}（明朝 Regular の表より）</p></div>{"".join(items)}</section>')
    if failures:
        raise SystemExit("\n".join(failures))
    shaped = {}
    for index, (label, text, language, features) in enumerate(SAMPLES):
        demo = Demo(label, text, language=language, features=features)
        for version in ORDER:
            shaped[(index, version)] = cell_shape(shapers[version], fonts[version], demo)
    for shaper in shapers.values():
        shaper.close()
    toc = "".join(f'<a href="#v{v.replace(".", "")}">{v}</a>' for v, *_ in VERSIONS)
    content = (f'<header class="top"><h1>読書 UD 版ごとの変化</h1>'
               '<p class="lead">同じ文を、前の版とその版で上下に並べました。下の赤い番号の行が、その版の表示です。点線の枠は、その版に無かった字です。</p>'
               f'<nav class="toc">{toc}</nav></header>'
               '<div class="controls"><label class="control">書体 <select id="family"><option value="Mincho">読書 UD明朝</option>'
               '<option value="Gothic">読書 UDゴシック</option></select></label>'
               '<label class="control">太さ <select id="weight"><option value="400">Regular</option><option value="700">Bold</option></select></label></div>'
               f'<main><section id="all"><div class="version-head"><h2>全版の並び</h2><p class="summary">同じ文を、元の BIZ UD から順に並べました。色の付いた行は、すぐ上の行と字形か配置が違います。</p></div>{matrix(shaped)}</section>'
               f'{"".join(sections)}</main>'
               '<footer>各版のフォントはリリースのファイルから、ページで使う字だけを取り出して埋め込んでいます。ヒンティングは除いています（ヒンティングの差は画素の画像で示しています）。'
               '色の付いた行の判定と各見本の差は、明朝 Regular を HarfBuzz で組んで確かめています。ライセンスは SIL Open Font License 1.1 です。</footer>')
    # サブセットに含める字: 見本と画面の文字すべて
    plain = re.sub(r"<[^>]+>", "", content) + "".join(d.text for *_x, ds in VERSIONS for d in ds)
    plain = html.unescape(plain) + "".join(s[1] for s in SAMPLES)
    faces, total = [], 0
    rules = []
    for version in ORDER:
        key = "biz" if version == BASE else version.replace(".", "")
        for family in spec.FAMILIES:
            name = f"f{key}-{family['key']}"
            for weight in WEIGHTS:
                css, size = face_css(name, source_path(version, family, weight), weight, plain)
                faces.append(css)
                total += size
            rules.append(f".{family['key'].lower()} [data-v=\"{version}\"]{{font-family:'{name}',serif}}")
    ui = spec.FAMILIES
    for name, family, weight in (("UI Gothic", ui[1], "Regular"), ("UI Gothic", ui[1], "Bold"), ("UI Mincho", ui[0], "Bold")):
        css, size = face_css(name, source_path(UNRELEASED, family, weight), weight, plain)
        faces.append(css)
        total += size
    page = ('<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<meta name="claude:viewport-fit-sides" content="cover"><title>読書 UD 版ごとの変化</title>'
            f'<style>{"".join(faces)}{STYLE}{"".join(rules)}</style></head><body>{content}<script>{SCRIPT}</script></body></html>\n')
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(page, encoding="utf-8")
    print(f"{OUTPUT}: {len(page) // 1024} KiB, fonts {total // 1024} KiB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
