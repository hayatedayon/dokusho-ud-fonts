"""文章の見た目を確かめる HTML (dist/specimen.html) を作る。

日本語の本文 (夏目漱石『吾輩は猫である』の冒頭)、英語の本文 (Lewis Carroll『不思議の国のアリス』の
冒頭。どちらも著作権の切れた文章)、和欧混植・約物・縦中横・ルビ・数字・結合用の記号の見本を、読書 UD と、
比べるための BIZ UD・BIZ UDP で並べる。両端揃え (text-align: justify) も切り替えられる。節ごとに 1 行にして書体を横に並べるので、どの列でも同じ節が
同じ位置から始まる。横組と縦組、大きさと行送り、約物の詰め (text-spacing-trim)、和欧間のアキ
(text-autospace)、palt を切り替えられ、tnum は、なし・あり・並べる (書体ごとに、なしとありの列) を選べる。

フォントを読むには、リポジトリの一番上で python3 -m http.server を動かし、
http://localhost:8000/dist/specimen.html を開く (ファイルを直接開くと、ブラウザによっては fonts/ と
sources/ を読まない)。

    python3 scripts/specimen_page.py
"""

import json
import sys
from pathlib import Path

import spec

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "dist" / "specimen.html"


def fonts() -> list[dict]:
    """ページで選べるフォント (CSS の名前, 見出し, ファイル)"""
    result = []
    for family in spec.FAMILIES:
        for weight in spec.WEIGHTS:
            result.append({"id": family["postscript"], "label": f"{family['name_ja']} {weight}",
                           "url": f"../fonts/{spec.output_name(family, weight)}", "family": family["key"],
                           "weight": weight, "kind": "ours"})
            for kind, source in (("ud", family["ud"]), ("udp", family["udp"])):
                name = family["source_name"].replace("BIZ UD", "BIZ UDP") if kind == "udp" else family["source_name"]
                result.append({"id": source, "label": f"{name} {weight}",
                               "url": f"../sources/{source}-{weight}.ttf", "family": family["key"],
                               "weight": weight, "kind": kind})
    return result


CONTENT = """
<section class="block">
<h2 class="label">日本語の本文</h2>
<h3 class="heading">吾輩は猫である</h3>
<p>　吾輩は猫である。名前はまだ無い。</p>
<p>　どこで生れたかとんと見当がつかぬ。何でも薄暗いじめじめした所でニャーニャー泣いていた事だけは記憶している。吾輩はここで始めて人間というものを見た。しかもあとで聞くとそれは書生という人間中で一番<ruby>獰悪<rt>どうあく</rt></ruby>な種族であったそうだ。この書生というのは時々我々を<ruby>捕<rt>つかま</rt></ruby>えて<ruby>煮<rt>に</rt></ruby>て食うという話である。しかしその当時は何という考もなかったから別段恐しいとも思わなかった。ただ彼の<ruby>掌<rt>てのひら</rt></ruby>に載せられてスーと持ち上げられた時何だかフワフワした感じがあったばかりである。</p>
<p class="source">夏目漱石『吾輩は猫である』（1905年）より</p>
</section>

<section class="block">
<h2 class="label">和欧混植</h2>
<p>　画面に“Hello, world”と出たのは、2026年11月6日の午後3時だった。彼女は「It’s alive!」と叫んで、iPhone 17 と MacBook を見比べた――どちらも、ちゃんと動いている。</p>
<p class="aside">同じ文の、和文と欧文の間に空白を入れない書き方（和欧間のアキを入れると、ブラウザが和文と欧文の間を空けます）:</p>
<p>　画面に“Hello, world”と出たのは、2026年11月6日の午後3時だった。彼女は「It’s alive!」と叫んで、iPhone 17とMacBookを見比べた――どちらも、ちゃんと動いている。</p>
<p class="aside">引用符とアポストロフィ（‘ ’ “ ”）は、横組では、日本語の文書（lang="ja"）の中でも BIZ UDP の字です。ダッシュなどほかの記号は、日本語の文書では BIZ UD の字のままです。</p>
<p>　この本は、JIS X 0213:2004 と Unicode 16.0 に沿って組んだ。<span class="em">傍点</span>を付けた語や、「『入れ子の括弧』」、（丸括弧）、句読点の続く所……どれも、本と同じアキになるはずだ。</p>
<p>　縦書きでは、<span class="tcy">12</span>月<span class="tcy">24</span>日や<span class="tcy">!?</span>のように、2 桁の数字を縦中横にする。</p>
</section>

<section class="block">
<h2 class="label">約物</h2>
<p>彼は“本当”と言った。‘一重’の引用符も同じ。</p>
<p>「『括弧』の中の『括弧』」。（注）、「です。」と、・中点・、！？ ‼ ⁉、――ダッシュ――と……三点リーダー、〜波ダッシュ〜。</p>
<p>⸺ 2 倍ダッシュ ⸺、⸻ 3 倍ダッシュ ⸻。「ああ」と、彼は言った――。</p>
</section>

<section class="block">
<h2 class="label">英語の本文</h2>
<p lang="en" class="latin">Alice was beginning to get very tired of sitting by her sister on the bank, and of having nothing to do: once or twice she had peeped into the book her sister was reading, but it had no pictures or conversations in it, ‘and what is the use of a book,’ thought Alice ‘without pictures or conversations?’</p>
<p lang="en" class="latin">So she was considering in her own mind (as well as she could, for the hot day made her feel very sleepy and stupid), whether the pleasure of making a daisy-chain would be worth the trouble of getting up and picking the daisies, when suddenly a White Rabbit with pink eyes ran close by her.</p>
<p class="source">Lewis Carroll, <i>Alice’s Adventures in Wonderland</i> (1865)</p>
</section>

<section class="block">
<h2 class="label">欧文の細部</h2>
<p lang="en" class="latin">Ligatures: fine, flower, office, affluent. Quotes: “double” and ‘single’, Alice’s, ’90s. Dashes: 1990–2000, wait—what? Minus: 3 − 2 = 1, ±0.5, 2 × 3 ÷ 6.</p>
<p lang="en" class="latin">Accents: café, naïve, façade, Ångström, Dvořák, Łódź, Øresund, smörgåsbord. Pinyin: nǐ hǎo, lǜ chá. IPA: [ˈfəʊnəˌtɪk].</p>
<p lang="de" class="latin narrow">Soft hyphens: Donau&shy;dampf&shy;schiff&shy;fahrts&shy;gesell&shy;schafts&shy;kapitän, Rind&shy;fleisch&shy;etikettierungs&shy;überwachungs&shy;aufgaben&shy;übertragungs&shy;gesetz.</p>
<p lang="en" class="latin">Combining marks: q̃ x̄ ŋ̊ p̰ i̋ ó́ — моло́ко, за́мок, замо́к. Kana: あ゙ え゙ ㇰ゚ か゚ — ゔ が ぱ.</p>
</section>

<section class="block">
<h2 class="label">数字</h2>
<table class="toc">
<tr><td>第一章　吾輩は猫である</td><td class="page">1</td></tr>
<tr><td>第二章　名前はまだ無い</td><td class="page">17</td></tr>
<tr><td>第三章　書生という人間</td><td class="page">111</td></tr>
<tr><td>第十一章　ニャーニャー</td><td class="page">1081</td></tr>
</table>
<table class="figures">
<tr><th>年</th><th>部数</th><th>前年比</th></tr>
<tr><td>2011</td><td>1,111,111</td><td>+11.1%</td></tr>
<tr><td>2018</td><td>987,654</td><td>−3.5%</td></tr>
<tr><td>2026</td><td>10,001</td><td>+0.1%</td></tr>
</table>
<p>時刻: 11:11、21:07、10:01。日付: 2011年1月11日、2026年11月6日。電話: 03-1111-2468。</p>
<p class="aside">tnum をかけると、1 がほかの数字と同じ幅になり、表や目次の桁がそろいます（上の「tnum」で、なし・あり・並べるを選べます）。</p>
<p>分数（<code>frac</code>）: <span class="frac">1/2 3/4 10/25 1 1/2</span>　上付き: 10<sup class="sups">−3</sup>、x<sup class="sups">2</sup>、E = mc²　下付き: H₂O、CO<sub class="subs">2</sub>　⁰¹²³⁴⁵⁶⁷⁸⁹ ₀₁₂₃₄₅₆₇₈₉</p>
<p>全角と半角（<code>hwid</code>）: ２０２６年 → <span class="hwid">２０２６</span>年、<span class="hwid">ＡＢＣ</span>　斜線の 0（<code>zero</code>）: <span class="zero">0123</span></p>
</section>

<section class="block">
<h2 class="label">見出し（palt）</h2>
<h3 class="heading palt">プロポーショナルに詰めた見出し「ラ・カンパネラ」</h3>
<h3 class="heading">ベタ組の見出し「ラ・カンパネラ」</h3>
<p class="aside">縦書きでは palt ではなく vpal をかけます（palt は字を左右にずらすので、縦書きでかけると字が揺れます）。読書 UD には、まだ vpal がありません。</p>
</section>
"""

PAGE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>読書 UD: 文章の見本</title>
<style>
__FACES__
:root { --size: 18px; --leading: 1.8; }
body { margin: 0; font-family: system-ui, sans-serif; color: #222; background: #f6f5f1; }
header { position: sticky; top: 0; z-index: 1; background: #fff; border-bottom: 1px solid #ddd; padding: 0.6rem 1rem;
         display: flex; flex-wrap: wrap; gap: 0.4rem 1.2rem; align-items: center; font-size: 0.85rem; }
header h1 { font-size: 1rem; margin: 0 0.5rem 0 0; }
header label { white-space: nowrap; }
header fieldset { border: 0; padding: 0; margin: 0; display: flex; gap: 0.6rem; align-items: center; }
header legend { float: left; color: #666; margin-right: 0.3rem; }
.note { font-size: 0.8rem; color: #666; padding: 0.4rem 1rem; margin: 0; }
/* 節ごとに 1 行。比べる書体を横に並べるので、どの列でも同じ節が同じ位置から始まる */
#grid { display: grid; gap: 0 1rem; padding: 0 1rem 1rem; align-items: stretch; }
#grid > .name { position: sticky; top: var(--header, 0); z-index: 1; font-size: 0.8rem; color: #fff; background: #555;
                padding: 0.25rem 0.6rem; margin-top: 1rem; }
#grid > .name.ours { background: #1d6fd8; }
#grid > .cell { min-width: 0; background: #fff; border: 1px solid #ddd; border-top: 0; padding: 1.2rem 1.5rem; }
.text { font-size: var(--size); line-height: var(--leading); hanging-punctuation: allow-end; }
.justify .text { text-align: justify; }
.text p { margin: 0 0 0.5em; }
.text .block { margin: 0; }
.text .label { font-family: system-ui, sans-serif; font-size: 11px; font-weight: normal; color: #999; margin: 0 0 0.6em;
               letter-spacing: 0.05em; }
.text .heading { font-size: 1.5em; font-weight: bold; margin: 0 0 0.6em; line-height: 1.4; }
.text .aside { font-family: system-ui, sans-serif; font-size: 11px; color: #999; line-height: 1.5; }
.text .source { font-size: 0.8em; color: #666; text-align: end; }
.text .latin { hyphens: manual; }
.text .narrow { max-inline-size: 12em; }
.text .em { text-emphasis: sesame; }
.text .tcy { text-combine-upright: all; font-feature-settings: "hwid"; }
.text .frac { font-feature-settings: "frac"; }
.text .sups { vertical-align: baseline; font-size: inherit; font-feature-settings: "sups"; }
.text .subs { vertical-align: baseline; font-size: inherit; font-feature-settings: "subs"; }
.text .hwid { font-feature-settings: "hwid"; }
.text .zero { font-feature-settings: "zero"; }
.text .palt { font-feature-settings: "palt"; }
.text code { font-family: system-ui, monospace; font-size: 0.8em; color: #666; }
.text .toc, .text .figures { border-collapse: collapse; margin-bottom: 0.8em; }
.text .toc td { padding: 0 0.5em 0 0; }
.text .toc .page { text-align: end; }
.text .figures th { font-weight: normal; color: #666; font-size: 0.8em; padding: 0 0.8em 0.2em 0; text-align: end; }
.text .figures td { padding: 0 0.8em 0 0; text-align: end; }
/* tnum は font-variant-numeric でかける (font-feature-settings は、frac などを書いた子の要素で上書きされる) */
.text.tnum { font-variant-numeric: tabular-nums; }
.text.palt-all { font-feature-settings: "palt"; }
.vertical #grid > .cell { writing-mode: vertical-rl; height: 26em; overflow-x: auto; }
/* palt は横組で字を左右にずらす機能で、縦書きでかけると字が左右に揺れる。縦書きでは vpal にする */
.vertical .text .palt, .vertical .text.palt-all { font-feature-settings: "vpal"; }
.no-trim .text { text-spacing-trim: space-all; }
.trim .text { text-spacing-trim: normal; }
.autospace .text { text-autospace: normal; }
.no-autospace .text { text-autospace: no-autospace; }
.status { color: #b00; }
</style>
</head>
<body>
<header>
<h1>読書 UD 文章の見本</h1>
<label>書体 <select id="family"><option value="Mincho">明朝</option><option value="Gothic">ゴシック</option></select></label>
<label>太さ <select id="weight"><option>Regular</option><option>Bold</option></select></label>
<fieldset><legend>並べる</legend>
<label><input type="checkbox" id="show-ud"> BIZ UD</label>
<label><input type="checkbox" id="show-udp"> BIZ UDP</label></fieldset>
<label><input type="checkbox" id="vertical"> 縦書き</label>
<label>大きさ <input type="range" id="size" min="10" max="32" value="18"> <span id="size-value">18px</span></label>
<label>行送り <input type="range" id="leading" min="1.2" max="2.4" step="0.05" value="1.8"> <span id="leading-value">1.8</span></label>
<label><input type="checkbox" id="justify" checked> 両端揃え</label>
<label><input type="checkbox" id="trim" checked> 約物の詰め</label>
<label><input type="checkbox" id="autospace"> 和欧間のアキ</label>
<label>tnum <select id="tnum"><option value="off">なし</option><option value="on">あり</option><option value="both">並べる</option></select></label>
<label><input type="checkbox" id="palt"> 全体に palt</label>
<span id="status" class="status"></span>
</header>
<p class="note">両端揃えは、行の長さをそろえるために字の間を広げます。列が狭く、行の中に欧文が多いと、広げる所が少なくて空きが目立ちます。約物の詰めは CSS の <code>text-spacing-trim</code>（Chromium は既定で詰めます。切ると <code>space-all</code>）、和欧間のアキは <code>text-autospace</code>（Chromium 140 から）です。ブラウザが対応していなければ、切り替えても変わりません。BIZ UD・BIZ UDP は、比べるための元のフォントです。</p>
<div id="grid"></div>
<template id="content">__CONTENT__</template>
<script>
const FONTS = __FONTS__;
const $ = (id) => document.getElementById(id);
const content = $("content").content;

function render() {
  const family = $("family").value, weight = $("weight").value;
  const kinds = ["ours"];
  if ($("show-ud").checked) kinds.push("ud");
  if ($("show-udp").checked) kinds.push("udp");
  const tnum = $("tnum").value;
  const variants = tnum === "both" ? [false, true] : [tnum === "on"];
  // 列: 書体 × tnum のなし・あり
  const columns = [];
  for (const kind of kinds) {
    const font = FONTS.find((f) => f.family === family && f.weight === weight && f.kind === kind);
    for (const tabular of variants) {
      columns.push({ font, kind, tabular, label: font.label + (tnum === "both" ? (tabular ? "・tnum あり" : "・tnum なし") : "") });
    }
  }
  const grid = $("grid");
  grid.replaceChildren();
  grid.style.gridTemplateColumns = `repeat(${columns.length}, minmax(0, 1fr))`;
  for (const column of columns) {
    const name = document.createElement("div");
    name.className = `name ${column.kind}`;
    name.textContent = column.label;
    grid.append(name);
  }
  for (const section of [...content.children].filter((e) => e.tagName === "SECTION")) {
    for (const column of columns) {
      const cell = document.createElement("div");
      cell.className = "cell text";
      cell.lang = "ja";
      cell.style.fontFamily = `'${column.font.id}'`;
      cell.style.fontWeight = weight === "Bold" ? "700" : "400";
      cell.classList.toggle("tnum", column.tabular);
      cell.classList.toggle("palt-all", $("palt").checked);
      cell.append(section.cloneNode(true));
      grid.append(cell);
    }
  }
  document.body.classList.toggle("vertical", $("vertical").checked);
  document.body.classList.toggle("justify", $("justify").checked);
  document.body.classList.toggle("trim", $("trim").checked);
  document.body.classList.toggle("no-trim", !$("trim").checked);
  document.body.classList.toggle("autospace", $("autospace").checked);
  document.body.classList.toggle("no-autospace", !$("autospace").checked);
  // 書体の名前は、上の操作の欄の下に貼り付ける
  document.documentElement.style.setProperty("--header", document.querySelector("header").offsetHeight + "px");
}

for (const id of ["family", "weight", "show-ud", "show-udp", "vertical", "justify", "trim", "autospace", "tnum", "palt"]) {
  $(id).addEventListener("change", render);
}
for (const [id, unit, variable] of [["size", "px", "--size"], ["leading", "", "--leading"]]) {
  $(id).addEventListener("input", () => {
    const value = $(id).value + unit;
    document.documentElement.style.setProperty(variable, value);
    $(id + "-value").textContent = value;
  });
}
render();

// フォントを読めたか (ファイルを直接開くと、読めないブラウザがある)
document.fonts.ready.then(async () => {
  const failed = [];
  for (const face of document.fonts) {
    try { await face.load(); } catch { failed.push(face.family); }
  }
  if (failed.length) {
    $("status").textContent = `フォントを読めません（${failed.length} 個）。python3 -m http.server で開いてください`;
  }
});
</script>
</body>
</html>
"""


def page() -> str:
    # 書体ごとに Regular (400) と Bold (700) を 1 つのファミリーにする (太字の見出しは Bold のファイル)
    # URL に更新日時を付ける (フォントを作り直したとき、ブラウザが前のファイルを使わないように)
    faces = "\n".join(f"@font-face {{ font-family: '{font['id']}'; "
                      f"src: url('{font['url']}?v={int((OUTPUT.parent / font['url']).resolve().stat().st_mtime)}'); "
                      f"font-weight: {700 if font['weight'] == 'Bold' else 400}; }}" for font in fonts())
    return (PAGE.replace("__FACES__", faces).replace("__CONTENT__", CONTENT)
            .replace("__FONTS__", json.dumps(fonts(), ensure_ascii=False)))


def main() -> int:
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(page(), encoding="utf-8")
    print(f"{OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
