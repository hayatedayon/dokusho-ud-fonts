"""GitHub Pages のトップ (index.html) になる、フォントの紹介のページを作る。

pages_site.py が _site/ に fonts/ と sources/ の TTF を置いたあとに呼ぶ。ページで使う字だけを
WOFF2 のサブセットにして _site/landing/ に置く (フォント全体は読み込まない)。外部の資源は使わない。
版の番号は spec.py の VERSION、使い方の CSS は README.md と README.en.md から取る。

    python3 scripts/landing_page.py   # 先に pages_site.py で _site/ を作っておく
"""

import hashlib
import html
import re
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

import spec

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "_site"
PAGES = "https://hayatedayon.github.io/dokusho-ud-fonts/"
REPOSITORY = "https://github.com/hayatedayon/dokusho-ud-fonts"
RELEASES = f"{REPOSITORY}/releases/latest"
SBOM_JA = f"{REPOSITORY}/blob/main/README.md#sbom-と証明"
SBOM_EN = f"{REPOSITORY}/blob/main/README.en.md#sbom-and-attestations"

TITLE = {"ja": "読書 UD", "en": "Dokusho UD"}
DESCRIPTION = {"ja": "本を読むためのフォントです。縦書きでも横書きでも、印刷された日本語の本と同じ組み方になります。",
               "en": "Fonts for reading books. Text is set the way printed Japanese books are, both horizontally and vertically."}

# パブリックドメイン (夏目漱石は 1916 年没)。『草枕』の冒頭。60 字なので、1 行 10 字で 6 行にぴったり収まる
KUSAMAKURA = ("山路を登りながら、こう考えた。智に働けば角が立つ。情に棹させば流される。"
              "意地を通せば窮屈だ。とかくに人の世は住みにくい。")
CHARS_PER_LINE = 10
# 縦組で見せる文。ビルドのときに、サブセットが元のフォントと同じに組めることを確かめる
VERTICAL_TEXTS = [KUSAMAKURA, "彼は“本当”だと言った。"]


def bi(tag: str, ja: str, en: str, cls: str = "", extra: str = "") -> str:
    """日本語と英語の 2 つの要素。表示する言語は html の lang で切り替える"""
    def one(lang: str, body: str) -> str:
        c = f"t-{lang}" + (f" {cls}" if cls else "")
        return f'<{tag} class="{c}" lang="{lang}"{extra}>{body}</{tag}>'
    return one("ja", ja) + one("en", en)


def sample(label_ja: str, label_en: str, body: str, kind: str, style: str = "") -> str:
    """見本の 1 行 (左にラベル)。kind が ud なら元の BIZ UD で組み、読み上げからは外す"""
    hidden = ' aria-hidden="true"' if kind == "ud" else ""
    st = f' style="{style}"' if style else ""
    return (f'<div class="row"{hidden}>{bi("span", label_ja, label_en, "lab")}'
            f'<div class="smp {kind}" lang="ja"{st}>{body}</div></div>')


def tate_sample(label_ja: str, label_en: str, body: str, kind: str) -> str:
    """縦組の見本。1 列に収まる高さの版面に置く"""
    hidden = ' aria-hidden="true"' if kind == "ud" else ""
    return (f'<div class="pg"{hidden}><div class="frame"><div class="smp {kind} tate" lang="ja">{body}</div></div>'
            f'{bi("span", label_ja, label_en, "lab")}</div>')


def features() -> list[dict]:
    """README の「読書と組版のための調整」から選んだ 6 項目と、実際のフォントで組んだ見本"""
    mixed = "画面に“Hello”と書いた。It’s a book. Alice’s Adventures in Wonderland を読む。"
    quote = "彼は“本当”だと言った。"
    punct = "「『春』。」と彼は言った。（それは二月のこと。）"
    kern = "AVATAR　Wave　Tokyo　T.　P,"
    frac = "1/2　3/4　10/25"
    ruby = "<ruby>山路<rt>やまみち</rt></ruby>を<ruby>登<rt>のぼ</rt></ruby>りながら"
    ud_ja, ours_ja = "元の BIZ UD", "読書 UD"
    ud_en, ours_en = "Original BIZ UD", "Dokusho UD"
    return [
        {"ja": "和文と欧文の混植",
         "en": "Japanese and Latin together",
         "p_ja": "仮名・漢字・約物は全角のマス目に並び（ベタ組）、欧字は字ごとの幅で組みます。和文の中の英語も、語の途中が空きません。"
                 "欧文の中の記号は BIZ UDP の字にして、<code>It’s</code> や <code>“Hello”</code> の前後が全角ぶん空かないようにしています。",
         "p_en": "Kana, kanji and punctuation sit on a full-width grid (solid setting), and Latin letters have their own widths, "
                 "so English words inside Japanese text are not split by gaps. Symbols in Latin text take BIZ UDP's glyphs, "
                 "so <code>It’s</code> and <code>“Hello”</code> have no full-width gaps around them.",
         "demo": sample(ud_ja, ud_en, mixed, "ud") + sample(ours_ja, ours_en, mixed, "ours")},
        {"ja": "縦組の引用符",
         "en": "Quotation marks in vertical text",
         "p_ja": "縦組では、引用符を縦組の括弧類である 〝 〟 の形で組みます。文字は変わらないので、コピーや検索に影響しません。",
         "p_en": "In vertical text, quotation marks take the forms of the vertical quotes 〝 〟. "
                 "The text itself does not change, so copying and searching are not affected.",
         "demo": '<div class="pair">' + tate_sample(ud_ja, ud_en, quote, "ud")
                 + tate_sample(ours_ja, ours_en, quote, "ours") + "</div>"},
        {"ja": "続いた約物の詰め",
         "en": "Trimming consecutive punctuation",
         "p_ja": "続いた括弧や句読点の間を、本と同じように詰められます（<code>halt</code>・<code>vhal</code>・<code>chws</code>・<code>vchw</code>）。"
                 "見出し向けの詰め組（<code>palt</code>・<code>vpal</code>）もあります。",
         "p_en": "Consecutive brackets and punctuation can be trimmed as in printed books (<code>halt</code>, <code>vhal</code>, "
                 "<code>chws</code>, <code>vchw</code>), and headings can use proportional setting (<code>palt</code>, <code>vpal</code>).",
         "demo": sample(ud_ja, ud_en, punct, "ud", "text-spacing-trim:space-all")
                 + sample(ours_ja + "（chws）", ours_en + " (chws)", punct, "ours",
                          'text-spacing-trim:space-all;font-feature-settings:&quot;chws&quot; 1')},
        {"ja": "欧字のカーニング",
         "en": "Latin kerning",
         "p_ja": "欧字の頻出ペアを控えめに詰めるカーニングが、既定で有効です。<code>T.</code>・<code>P,</code> のような、欧字と句読点の間も詰めます。",
         "p_en": "Latin kerning for frequent pairs is on by default. It also tightens letters before punctuation, as in <code>T.</code> and <code>P,</code>.",
         "demo": sample(ud_ja, ud_en, kern, "ud", "font-size:1.35em") + sample(ours_ja, ours_en, kern, "ours", "font-size:1.35em")},
        {"ja": "分数・上付き・下付き・等幅の数字",
         "en": "Fractions, scripts and tabular figures",
         "p_ja": "分数、上付き、下付き、等幅の数字、縦中横に使える半角の英数字（<code>hwid</code>）を組めます。"
                 "下は <code>frac</code> を指定した分数と、上付き・下付きの字です。",
         "p_en": "Fractions, superscripts, subscripts, tabular figures and half-width alphanumerics for tate-chu-yoko (<code>hwid</code>) "
                 "are available. Below are fractions with <code>frac</code>, and superscripts and subscripts.",
         "demo": sample(ud_ja + "（frac）", ud_en + " (frac)", frac, "ud", 'font-size:1.6em;font-feature-settings:&quot;frac&quot; 1')
                 + sample(ours_ja + "（frac）", ours_en + " (frac)", frac, "ours", 'font-size:1.6em;font-feature-settings:&quot;frac&quot; 1')
                 + sample(ours_ja, ours_en, "H₂O　10⁻³　x²　m³", "ours", "font-size:1.6em")},
        {"ja": "ルビ仮名の試作",
         "en": "A ruby kana trial",
         "p_ja": "和文引用符（<code>ss01</code>）、欧文記号（<code>ss02</code>）、ルビ仮名の試作（<code>ss03</code>）を、必要なときだけ選べます。"
                 "<code>ss03</code> は実寸で比較するための試作です。",
         "p_en": "Japanese quotation marks (<code>ss01</code>), Latin symbols (<code>ss02</code>) and a ruby kana trial (<code>ss03</code>) "
                 "can be selected when needed. <code>ss03</code> is a trial for comparing at actual sizes.",
         "demo": sample("通常", "Default", ruby, "ours", "font-size:1.9em") + sample("<code>ss03</code>（試作）", "<code>ss03</code> (trial)", ruby, "ours",
                                                                                "font-size:1.9em;font-feature-settings:&quot;ss03&quot; 1")},
    ]


def usage_css(readme: str, heading: str) -> str:
    """README の「使い方」の最初の CSS のコードブロック"""
    start = readme.index(heading)
    match = re.search(r"```css\n(.*?)```", readme[start:], flags=re.S)
    if not match:
        raise SystemExit(f"{heading}: the CSS example was not found")
    return match.group(1).rstrip("\n")


STYLE = """
:root{--bg:#f3f6f5;--ink:#17201f;--muted:#44595b;--rule:#c5d0cf;--accent:#1d5675;--btn-bg:#1d5675;--btn-ink:#f4faff;--code:#e3ebea;--gridimg:GRIDLIGHT;
--ours:"Dokusho UD Mincho",serif;--ud:"BIZ UD Mincho",serif;--head:"Dokusho UD Gothic",sans-serif;color-scheme:light}
:root[data-face=gothic]{--ours:"Dokusho UD Gothic",sans-serif;--ud:"BIZ UD Gothic",sans-serif}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#10181a;--ink:#e3ebea;--muted:#a5b8b9;--rule:#2b3b3d;--accent:#8cc4e0;
--btn-bg:#8cc4e0;--btn-ink:#0b171c;--code:#1a272a;--gridimg:GRIDDARK;color-scheme:dark}}
:root[data-theme=dark]{--bg:#10181a;--ink:#e3ebea;--muted:#a5b8b9;--rule:#2b3b3d;--accent:#8cc4e0;--btn-bg:#8cc4e0;--btn-ink:#0b171c;
--code:#1a272a;--gridimg:GRIDDARK;color-scheme:dark}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--ours);font-size:1rem;line-height:1.95;overflow-wrap:anywhere;line-break:strict}
a{color:var(--accent);text-underline-offset:.25em;text-decoration-thickness:1px}
a:focus-visible,button:focus-visible{outline:3px solid var(--accent);outline-offset:3px}
code,pre{font-family:ui-monospace,"SFMono-Regular",Menlo,Consolas,monospace;font-size:.86em;line-height:1.6}
code{background:var(--code);padding:.05em .35em;white-space:nowrap}
h1,h2,h3,.btn,.lab,.bar,.mark,.note{font-family:var(--head)}
h1,h2,h3{text-wrap:balance}
.wrap{max-width:70rem;margin:0 auto;padding-inline:max(16px,env(safe-area-inset-left,0px)) max(16px,env(safe-area-inset-right,0px))}
.skip{position:absolute;left:-999px;top:0;background:var(--bg);padding:.5rem 1rem;z-index:3}
.skip:focus{left:0}
.t-en{display:none}
html[lang=en] .t-en{display:revert}
html[lang=en] .t-ja{display:none}
.top{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:.5rem 2rem;padding-top:1.25rem}
.mark{font-weight:700;font-size:.95rem;letter-spacing:.04em}
.bar{display:none;flex-wrap:wrap;gap:.25rem 1.75rem;font-size:.85rem;line-height:1.4}
.js .bar{display:flex}
.grp{display:flex;gap:.25rem}
.grp button{font:inherit;color:var(--muted);background:none;border:0;border-bottom:2px solid transparent;padding:.55rem .6rem;min-height:2.5rem;cursor:pointer}
.grp button[aria-pressed=true]{color:var(--ink);border-bottom-color:var(--accent)}
.hero{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:3rem 5rem;align-items:start;padding:5rem 0 6rem}
h1{margin:0 0 2rem;font-size:clamp(1.9rem,4vw,3rem);line-height:1.35;font-weight:700;letter-spacing:.01em}
html[lang=en] h1{font-size:clamp(1.7rem,3.2vw,2.4rem)}
h1 span{display:inline-block}
.lead{font-size:clamp(1.2rem,2vw,1.5rem);line-height:1.8;margin:0 0 1rem}
.sub{color:var(--muted);margin:0 0 2.5rem;font-size:.95rem;line-height:1.95;max-width:36em}
.actions{display:flex;flex-wrap:wrap;gap:1rem 2rem;align-items:center}
.btn{display:inline-flex;flex-direction:column;background:var(--btn-bg);color:var(--btn-ink);text-decoration:none;padding:.9rem 1.6rem;font-weight:700;font-size:1.1rem;line-height:1.5}
.btn small{font-weight:400;font-size:.78rem}
.btn:hover{filter:brightness(1.1)}
figure{margin:0}
.tate-fig{width:12em;max-width:100%;justify-self:end;font-size:26px}
.tate-body{writing-mode:vertical-rl;font-feature-settings:"vert" 1;line-height:2;height:10em;width:12em;
background-image:var(--gridimg);
background-size:2em 1em;background-position:right top;box-shadow:inset 0 -1px 0 var(--rule)}
.tate-body p{margin:0}
figcaption{color:var(--muted);font-size:.85rem;margin-top:1.25rem;line-height:1.8;width:min(30rem,100%)}
section{padding:0 0 6rem}
h2{font-size:clamp(1.4rem,2.6vw,1.9rem);font-weight:700;margin:0 0 1rem;line-height:1.5}
.intro{color:var(--muted);margin:0 0 3.5rem;max-width:38em;font-size:.95rem}
.list{display:flex;flex-direction:column;gap:4rem;list-style:none;margin:0;padding:0}
.card{display:grid;grid-template-columns:minmax(0,5fr) minmax(0,7fr);gap:1.25rem 4rem;align-items:start}
h3{font-size:1.15rem;margin:0 0 .75rem;line-height:1.6;font-weight:700}
.card p{margin:0;font-size:.95rem;line-height:1.95;max-width:38em}
.demo{min-width:0}
.row{display:grid;grid-template-columns:7.5rem minmax(0,1fr);gap:0 1rem;align-items:baseline;padding:.55rem 0}
.lab{font-size:.8rem;color:var(--muted);line-height:1.7}
.smp{font-size:1.15rem;line-height:1.9;min-width:0}
.smp.ud{font-family:var(--ud)}
.smp.ours{font-family:var(--ours)}
.smp rt{font-size:.5em}
.pair{display:flex;gap:2.5rem}
.pg{display:flex;flex-direction:column;gap:.75rem;align-items:flex-start}
.pg .frame{border:1px solid var(--rule);padding:.9rem .6rem}
.smp.tate{writing-mode:vertical-rl;font-feature-settings:"vert" 1;height:12em;font-size:1.5rem;line-height:1.9;margin:0}
.usage{display:grid;grid-template-columns:minmax(0,5fr) minmax(0,7fr);gap:1.25rem 4rem;align-items:start}
.usage p{margin:0;color:var(--muted);font-size:.95rem}
pre{margin:0;background:var(--code);padding:1.1rem 1.25rem;overflow-x:auto;max-width:100%;white-space:pre}
pre code{background:none;padding:0;white-space:pre;font-size:.82rem}
.links{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(15rem,1fr));gap:1.25rem 3rem}
.links a{display:block;color:var(--ink);text-decoration:none;line-height:1.8;font-family:var(--head);font-weight:700}
.links a:hover{color:var(--accent);text-decoration:underline}
.links a.t-en{display:none}
html[lang=en] .links a.t-en{display:block}
html[lang=en] .links a.t-ja{display:none}
.links small.t-en{display:none}
html[lang=en] .links small.t-en{display:block}
html[lang=en] .links small.t-ja{display:none}
.links small{display:block;color:var(--muted);font-size:.78rem;line-height:1.7;font-weight:400;font-family:var(--ours)}
footer{padding:0 0 4rem;color:var(--muted);font-size:.85rem;line-height:1.9;max-width:44em}
footer p{margin:0 0 .4rem}
@media (min-width:24rem){.tate-fig{font-size:28px}}
@media (min-width:28rem){.tate-fig{font-size:32px}}
@media (min-width:36rem){.tate-fig{font-size:36px}}
@media (min-width:52rem){.tate-fig{font-size:28px}}
@media (min-width:64rem){.tate-fig{font-size:32px}}
@media (min-width:70rem){.tate-fig{font-size:36px}}
@media (min-width:76rem){.tate-fig{font-size:40px}}
@media (max-width:52rem){
.hero{grid-template-columns:minmax(0,1fr);padding:2.5rem 0 4rem;gap:3rem}
.tate-fig{justify-self:start}
.row{grid-template-columns:minmax(0,1fr);gap:0}
.card,.usage{grid-template-columns:minmax(0,1fr)}
.list{gap:3rem}
section{padding-bottom:4rem}
.pair{gap:1.5rem}
}
"""



def _grid(color: str) -> str:
    """字の格子 (1 字 = 1 em の升目。升の左右の線は列の中央から 0.5 em ずつ) の SVG。色は CSS の変数に使えないので、明暗で別に作る"""
    return ("url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 100' preserveAspectRatio='none'%3E"
            f"%3Cpath d='M50 .5H150M50 0V100M150 0V100' fill='none' stroke='%23{color}' vector-effect='non-scaling-stroke'/%3E%3C/svg%3E\")")


STYLE = STYLE.replace("GRIDLIGHT", _grid("a9bbbb")).replace("GRIDDARK", _grid("405557"))

SCRIPT_HEAD = """(function(){var d=document.documentElement;d.classList.add('js');try{var s=localStorage,f=s.getItem('dud-face'),l=s.getItem('dud-lang'),
t=s.getItem('dud-theme');if(f==='gothic')d.dataset.face='gothic';if(l==='en')d.lang='en';if(t==='light'||t==='dark')d.dataset.theme=t}catch(e){}
if(location.hash==='#en')d.lang='en'})();"""

SCRIPT_BODY = """(function(){var d=document.documentElement,T=%s;
function save(k,v){try{localStorage.setItem('dud-'+k,v)}catch(e){}}
function theme(){return d.dataset.theme||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light')}
function sync(){var cur={face:d.dataset.face||'mincho',lang:d.lang==='en'?'en':'ja',theme:theme()};
document.querySelectorAll('.bar button').forEach(function(b){b.setAttribute('aria-pressed',String(cur[b.dataset.set]===b.dataset.value))});
document.title=T[cur.lang]}
document.querySelectorAll('.bar button').forEach(function(b){b.addEventListener('click',function(){var k=b.dataset.set,v=b.dataset.value;
if(k==='face'){if(v==='gothic')d.dataset.face='gothic';else delete d.dataset.face}
else if(k==='lang')d.lang=v;else d.dataset.theme=v;save(k,v);sync()})});
sync()})();"""


def controls() -> str:
    def group(key: str, ja_label: str, en_label: str, items: list[tuple[str, str, str]]) -> str:
        buttons = "".join(f'<button type="button" data-set="{key}" data-value="{value}" aria-pressed="false">'
                          f'<span class="t-ja" lang="ja">{ja}</span><span class="t-en" lang="en">{en}</span></button>'
                          for value, ja, en in items)
        return f'<div class="grp" role="group" aria-label="{ja_label} / {en_label}">{buttons}</div>'
    return ('<div class="bar">'
            + group("face", "本文の書体", "Body typeface", [("mincho", "明朝", "Mincho"), ("gothic", "ゴシック", "Gothic")])
            + group("lang", "言語", "Language", [("ja", "日本語", "日本語"), ("en", "English", "English")])
            + group("theme", "表示", "Theme", [("light", "明", "Light"), ("dark", "暗", "Dark")])
            + "</div>")


def body_html() -> str:
    readme_ja = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_en = (ROOT / "README.en.md").read_text(encoding="utf-8")
    css_ja = html.escape(usage_css(readme_ja, "## 使い方"))
    css_en = html.escape(usage_css(readme_en, "## Usage"))
    version = spec.VERSION
    cards = "".join(
        f'<li class="card"><div>{bi("h3", f["ja"], f["en"])}{bi("p", f["p_ja"], f["p_en"])}</div><div class="demo">{f["demo"]}</div></li>'
        for f in features())
    assert len(KUSAMAKURA) % CHARS_PER_LINE == 0
    tate = f"<p>{KUSAMAKURA}</p>"
    links = [
        ("specimen.html", "文章の見本", "Text specimen", "書体・大きさ・縦横を切り替えて見比べる", "Switch typefaces, sizes and directions (Japanese)"),
        ("versions.html", "版ごとの変化", "Changes by version", "公開した各版を同じ文で見比べる", "Compare every release on the same text (Japanese)"),
        (REPOSITORY, "GitHub", "GitHub", "ソースとリリース、Issue", "Source, releases and issues"),
        ("OFL.txt", "ライセンス（OFL）", "License (OFL)", "SIL Open Font License 1.1", "SIL Open Font License 1.1"),
    ]
    link_items = "".join(
        f'<li><a href="{url}">{bi("span", ja, en)}{bi("small", sja, sen)}</a></li>' for url, ja, en, sja, sen in links)
    sbom = (f'<li><a class="t-ja" lang="ja" href="{SBOM_JA}">SBOM と証明<small>配布物の材料と、ビルドの証明を確かめる</small></a>'
            f'<a class="t-en" lang="en" href="{SBOM_EN}">SBOM and attestations<small>Verify what the files are made of and how they were built</small></a></li>')
    return f"""
<a class="skip" href="#main">{bi("span", "本文へ", "Skip to content")}</a>
<div class="wrap">
<div class="top"><span class="mark">{bi("span", "読書 UD", "Dokusho UD")}</span>{controls()}</div>
<main id="main">
<div class="hero">
<div>
{bi("h1", '<span>読書 UD明朝</span>・<span>読書 UDゴシック</span>', '<span>Dokusho UD Mincho</span> and <span>Dokusho UD Gothic</span>')}
{bi("p", "本を読むためのフォントです。", "Fonts for reading books.", "lead")}
{bi("p", "縦書きでも横書きでも、印刷された日本語の本と同じ組み方になります。モリサワの BIZ UD明朝・BIZ UDゴシックを元に、欧字だけを同じデザインのプロポーショナルな BIZ UDP の字にしました。",
    "Text is set the way printed Japanese books are, both horizontally and vertically. They are Morisawa's BIZ UDMincho and BIZ UDGothic with only the Latin letters taken from BIZ UDP, the proportional version of the same design.", "sub")}
<div class="actions">
<a class="btn" href="{RELEASES}">{bi("span", f"ダウンロード（{version}）", f"Download ({version})")}<small>{bi("span", "最新のリリースのページが開きます", "Opens the latest release on GitHub")}</small></a>
<a href="specimen.html">{bi("span", "文章の見本を見る", "Text specimen")}</a>
</div>
</div>
<figure class="tate-fig">
<div class="tate-body" lang="ja" role="group" aria-label="夏目漱石『草枕』の冒頭">{tate}</div>
{bi("figcaption", "夏目漱石『草枕』の冒頭。ベタ組で、1 行 10 字、字送りは 1 em、行送りは 2 em", "Opening of Natsume Sōseki's Kusamakura (public domain). Solid setting: 10 characters per line, 1 em between characters, 2 em between lines")}
</figure>
</div>

<section>
{bi("h2", "読書と組版のための調整", "Tuned for reading and typesetting")}
{bi("p", "下の見本は、このページで読み込んだ読書 UD で組んでいます。元の BIZ UD と違うところは並べて見比べられます。",
    "The samples below are set in Dokusho UD loaded by this page. Where it differs from the original BIZ UD, the two are shown side by side.", "intro")}
<ul class="list">{cards}</ul>
</section>

<section>
{bi("h2", "使い方", "Usage")}
<div class="usage">
{bi("p", "フォントをインストールするか、Web では次のように読み込みます。", "Install the fonts, or load them on the web like this:")}
<div><pre class="t-ja" lang="en"><code>{css_ja}</code></pre><pre class="t-en" lang="en"><code>{css_en}</code></pre></div>
</div>
</section>

<section>
{bi("h2", "リンク", "Links")}
<ul class="links">{link_items}{sbom}</ul>
</section>
</main>
<footer>
{bi("p", "ライセンスは <a href=\"OFL.txt\">SIL Open Font License 1.1</a> です。個人でも商用でも無料で使え、アプリや文書に同梱して配れます。フォント単体での販売はできません。",
    "Licensed under the <a href=\"OFL.txt\">SIL Open Font License 1.1</a>. Free for personal and commercial use, and free to bundle with apps and documents; the fonts may not be sold by themselves.")}
{bi("p", "このフォントはモリサワとは関係がありません。", "These fonts are not affiliated with Morisawa.")}
</footer>
</div>
"""


class TextCollector(HTMLParser):
    """body の中の文字を、太字の要素・元の BIZ UD で組む要素・それ以外に分けて集める"""
    VOID = {"meta", "link", "br", "img", "input", "hr"}
    BOLD = {"h1", "h2", "h3", "strong", "b"}

    def __init__(self):
        super().__init__()
        self.stack: list[tuple[str, bool, bool, bool]] = []
        self.text = {"all": set(), "bold": set(), "ud": set()}
        self.in_body = False

    def handle_starttag(self, tag, attrs):
        if tag == "body":
            self.in_body = True
        if tag in self.VOID:
            return
        classes = (dict(attrs).get("class") or "").split()
        parent = self.stack[-1] if self.stack else ("", False, False, False)
        bold = parent[1] or tag in self.BOLD or "btn" in classes
        ud = parent[2] or "ud" in classes
        skip = parent[3] or tag in ("script", "style", "pre", "title")
        self.stack.append((tag, bold, ud, skip))

    def handle_endtag(self, tag):
        if tag in self.VOID or not self.stack:
            return
        self.stack.pop()

    def handle_data(self, data):
        if not self.in_body or not self.stack:
            return
        _, bold, ud, skip = self.stack[-1]
        if skip:
            return
        chars = {c for c in data if not c.isspace()}
        (self.text["ud"] if ud else self.text["bold"] if bold else self.text["all"]).update(chars)


def collect(page: str) -> dict[str, set[str]]:
    parser = TextCollector()
    parser.feed(page)
    return parser.text


def make_subset(source: Path, chars: set[str], out: Path) -> bytes:
    """chars だけを収めた WOFF2 のサブセット。組版の機能 (GSUB・GPOS) と name 表は残す"""
    options = subset.Options()
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    options.name_languages = ["*"]
    options.name_legacy = True
    options.notdef_outline = True
    options.glyph_names = False
    options.hinting = True
    options.flavor = "woff2"
    options.drop_tables += ["meta"]
    font = TTFont(source, recalcTimestamp=False)
    subsetter = subset.Subsetter(options)
    subsetter.populate(text="".join(sorted(chars)))
    subsetter.subset(font)
    out.parent.mkdir(parents=True, exist_ok=True)
    font.flavor = "woff2"
    font.save(out)
    return out.read_bytes()


def verify_shaping(source: Path, subset_font: Path, chars: set[str], texts: list[str]) -> None:
    """サブセットが元のフォントと同じに組めることを HarfBuzz で確かめる (縦組の字形 (vert・vrt2)、約物、小書きの仮名を含む)。
    字ごと・用字系ごとと、ページの縦組の文を、字形の輪郭と送り・ずれが一致するまで比べる。違えばビルドを止める"""
    from harfbuzz_shape import Shaper

    def outline(font: TTFont, name: str) -> str:
        glyf = font["glyf"]
        glyph = glyf[name]
        coords = list(glyph.getCoordinates(glyf)[0]) if glyph.numberOfContours else []
        return hashlib.sha256(repr(coords).encode()).hexdigest()[:12]

    with tempfile.TemporaryDirectory() as tmp:
        plain = Path(tmp) / "subset.ttf"
        font = TTFont(subset_font)
        font.flavor = None
        font.save(plain)
        ours, reference = TTFont(plain), TTFont(source)
        sub_shaper, ref_shaper = Shaper(plain), Shaper(source)

        def shaped(shaper, font, text, script, vertical):
            order = font.getGlyphOrder()
            return [(outline(font, order[g]), *rest) for g, _, *rest in shaper.shape(text, "ja", vertical=vertical, script=script)]

        cases = [(text, None) for text in texts if set(text) <= chars]  # 収めていない字を含む文は、そのフォントでは使わない
        for char in sorted(chars):
            cases += [(char, script) for script in (None, "Hira", "Kana", "Hani", "Latn")]
        try:
            for text, script in cases:
                for vertical in (True, False):
                    if shaped(sub_shaper, ours, text, script, vertical) != shaped(ref_shaper, reference, text, script, vertical):
                        raise SystemExit(f"{subset_font.name}: the subset shapes {text[:12]!r} (script {script}, vertical {vertical}) "
                                         f"differently from {source.name}")
        finally:
            sub_shaper.close()
            ref_shaper.close()


def font_faces(page_text: dict[str, set[str]]) -> tuple[str, str]:
    """サブセットを _site/landing/ に作り、@font-face と先読みの link を返す"""
    ascii_chars = {chr(c) for c in range(0x20, 0x7F)} - {" "}
    regular = page_text["all"] | ascii_chars
    bold = page_text["bold"] | ascii_chars
    ud = page_text["ud"]
    faces: list[str] = []
    preload = ""
    jobs = []
    # 見出しとボタンは常にゴシックの太字。本文は明朝かゴシックの標準 (切り替え)
    for family in spec.FAMILIES:
        key = family["key"].lower()
        name = f"Dokusho UD {key.capitalize()}"
        jobs.append((name, 400, f"dokusho-{key}-regular", SITE / "fonts" / spec.output_name(family, "Regular"), regular))
        if key == "gothic":
            jobs.append((name, 700, f"dokusho-{key}-bold", SITE / "fonts" / spec.output_name(family, "Bold"), bold))
        jobs.append((f"BIZ UD {key.capitalize()}", 400, f"bizud-{key}-regular", SITE / "sources" / f"{family['ud']}-Regular.ttf", ud))
    folder = SITE / "landing"
    for family_name, weight, stem, source, chars in jobs:
        tmp = folder / f"{stem}.woff2"
        data = make_subset(source, chars, tmp)
        if "dokusho" in stem:
            verify_shaping(source, tmp, chars, VERTICAL_TEXTS)
        digest = hashlib.sha256(data).hexdigest()[:8]
        final = folder / f"{stem}.{digest}.woff2"
        tmp.replace(final)
        faces.append(f'@font-face{{font-family:"{family_name}";font-weight:{weight};font-style:normal;font-display:swap;'
                     f'src:url("landing/{final.name}") format("woff2")}}')
        if stem == "dokusho-gothic-bold":
            preload += f'<link rel="preload" href="landing/{final.name}" as="font" type="font/woff2" crossorigin>'
    return "\n".join(faces), preload


def build() -> list[Path]:
    """_site/index.html と _site/landing/*.woff2 を作る"""
    body = body_html()
    face_css, preload = font_faces(collect(f"<body>{body}</body>"))
    meta = (f'<meta name="description" content="{html.escape(DESCRIPTION["ja"])}">\n'
            f'<meta property="og:type" content="website">\n<meta property="og:site_name" content="読書 UD">\n'
            f'<meta property="og:title" content="{html.escape(TITLE["ja"])}">\n'
            f'<meta property="og:description" content="{html.escape(DESCRIPTION["ja"])}">\n'
            f'<meta property="og:url" content="{PAGES}">\n<meta property="og:locale" content="ja_JP">\n'
            f'<meta property="og:locale:alternate" content="en_US">\n<meta name="twitter:card" content="summary">')
    titles = "{" + ",".join(f'"{k}":"{v}"' for k, v in TITLE.items()) + "}"
    page = f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{TITLE["ja"]}</title>
{meta}
<meta name="color-scheme" content="light dark">
{preload}
<script>{SCRIPT_HEAD}</script>
<style>
{face_css}
{STYLE}</style>
</head>
<body>{body}<script>{SCRIPT_BODY % titles}</script>
</body>
</html>
"""
    (SITE / "index.html").write_text(page, encoding="utf-8")
    return sorted((SITE / "landing").glob("*.woff2"))


def main() -> int:
    files = build()
    total = sum(p.stat().st_size for p in files)
    for path in files:
        print(f"{path.name}: {path.stat().st_size:,} bytes")
    print(f"index.html: {(SITE / 'index.html').stat().st_size:,} bytes, fonts total {total:,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
