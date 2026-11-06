# 読書 UD明朝・読書 UDゴシック

[![Build](https://github.com/hayatedayon/dokusho-ud-fonts/actions/workflows/build.yml/badge.svg)](https://github.com/hayatedayon/dokusho-ud-fonts/actions/workflows/build.yml)
[![Release](https://img.shields.io/github/v/release/hayatedayon/dokusho-ud-fonts?sort=semver&display_name=tag)](https://github.com/hayatedayon/dokusho-ud-fonts/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/hayatedayon/dokusho-ud-fonts/total)](https://github.com/hayatedayon/dokusho-ud-fonts/releases)
[![License: OFL-1.1](https://img.shields.io/badge/license-OFL--1.1-blue)](OFL.txt)
<br>
![Format](https://img.shields.io/badge/format-TrueType-555)
[![Built with fontTools](https://img.shields.io/badge/built%20with-fontTools%204.61-3776AB?logo=python&logoColor=white)](https://github.com/fonttools/fonttools)

[English](README.en.md)

本を読むためのフォントです。モリサワの [BIZ UD明朝](https://github.com/googlefonts/morisawa-biz-ud-mincho)・[BIZ UDゴシック](https://github.com/googlefonts/morisawa-biz-ud-gothic)を元に、欧字だけを同じデザインのプロポーショナルな BIZ UDP の字にしました。縦書きでも横書きでも、印刷された日本語の本と同じ組み方になります。

| | 読書 UD明朝 | 読書 UDゴシック |
| --- | --- | --- |
| 英語名 | Dokusho UD Mincho | Dokusho UD Gothic |
| ウェイト | Regular・Bold | Regular・Bold |
| ファイル | `DokushoUDMincho-Regular.ttf` など | `DokushoUDGothic-Regular.ttf` など |

## なぜ合成したか

日本語の横組の本は、仮名・漢字・約物を全角のマス目に並べ（[日本語組版処理の要件（JLReq）](https://www.w3.org/TR/jlreq/?lang=ja) のベタ組）、欧字はプロポーショナルの欧文書体で組みます。BIZ UD と BIZ UDP は、どちらか一方ではこの組み方になりません。

| | 仮名・約物 | 欧字 |
| --- | --- | --- |
| BIZ UD | 全角（マス目に並ぶ） | 半角の等幅（`i` も `W` も同じ幅） |
| BIZ UDP | 字ごとの幅（句点は全角の 6 割、始め括弧は半分） | 字ごとの幅 |
| **読書 UD** | **全角（BIZ UD と同じ）** | **字ごとの幅（BIZ UDP と同じ）** |

和文（仮名・漢字・約物）の縦書きの字形（`vert`・`vrt2`）と縦の字送り、JIS 第 1・第 2 水準の漢字は BIZ UD のままです。

## 変えたところ

- 欧字（U+0020–007E、U+00C0–00D6、U+00D8–00F6、U+00F8–02FF、U+1E00–1EFF、U+FB00–FB06。拡張のラテン文字・IPA の記号・ﬁ などの合字を含みます）と上付きの ⁴ の形・字幅・縦の字送りを BIZ UDP のものにしました。BIZ UD では、ピンインの `ǎ` `ǐ` などは全角、IPA の記号は半角で、語の途中で字の間が空きます。× と ÷ は和文で全角として使うので、文字の割り当ては BIZ UD のままにし、欧文の中でだけ BIZ UDP の字にします（下の「欧文の中の記号」）。
- その欧字からの置き換え（`zero`・`vrt2`。縦組で横に倒した欧字など）と、欧字から始まる合字（`ccmp`・`liga`。`fi` を `ﬁ` に、IPA の `ə` と結合用のアクセントを 1 つの字につなぐなど）を BIZ UDP と同じにしました。字形の候補（`aalt`。アプリの字形パネルなどに出ます）の欧字の候補も、それに合わせています。全角の英数字（`Ａ` `％` `１` など）を半角にする `hwid` は、BIZ UD の半角の字を別に残してそれにつなぐので、これまでどおり半角（等幅）になります。
- 読書 UD で足した機能：`hwid` は、プロポーショナルの欧字・数字・記号（`A` `1` `%` など）も BIZ UD の半角の字にします（BIZ UD・BIZ UDP にはありません）。縦書きの縦中横などで `hwid` を使えば、`12` のような 2 桁が 1 字の枠にちょうど収まります。字形の候補（`aalt`）にも半角の字を出すので、字形パネルでは、`Ａ` からプロポーショナルの `A` と半角の `A` のどちらも選べます。
- 読書 UD で足した機能：分数（`frac`）を組めるようにしました。`frac` をかけると、`1/2` や `10/25` が、小さな分子、分数の斜線、ベースラインにそろった小さな分母の分数になります（`1 1/2` の整数部や `and/or` の `/` はそのままです）。`⁄`（U+2044 FRACTION SLASH）を使えば、ブラウザなどが機能を指定しなくても分数にします。分子と分母の字は、元のフォントにある上付きの `¹ ² ³ ⁴` を元にし、数字と斜線の間は BIZ UDP の `½` `¾` などの組み方に合わせています。BIZ UD・BIZ UDP の `frac` は `1` `2` `3` を上付きにするだけで、分母の字がありませんでした。
- 読書 UD で足した機能：上付きの数字を 0〜9 そろえ、上付きの記号 `⁺` `⁻` `⁼` `⁽` `⁾` も足しました（`⁰` `⁵`〜`⁹` `⁺`〜`⁾` の文字と、`sups`・`numr`・`dnom`。`10⁻³` などに使えます。`sups` では `+ - − = ( )` も上付きになります）。元のフォントには `¹ ² ³ ⁴` しかありません。足した字は、普通の数字や記号を `¹ ² ³ ⁴` と同じ割合で縮め、同じだけ線を太らせ、同じだけ持ち上げて作りました（ただ縮めると線が細くなります。記号と数字の高さの関係は、本文と同じです）。ヒンティングは付いていません。
- BIZ UDP から持ってきた字（欧字・欧文の中の記号など）には、BIZ UDP のヒンティングを付けています。BIZ UD と BIZ UDP は cvt（ヒンティングに使う値の表）と prep が違うので、BIZ UDP の cvt と prep を BIZ UD のものの後ろに付け足し、命令が指す cvt の番号をずらしています。小さな文字の欧字も、BIZ UDP と同じ命令と値で描かれます（1.003 までは命令を外していたため、Windows の小さな文字では、欧字だけが少し薄く、ぼやけて見えました）。ただし、ハイフン・下線・ソフトハイフン・マクロン・エンダッシュ・エムダッシュ・上線・マイナスの 8 字は、ヒンティングを付けていません。細い横線だけの字で、BIZ UDP のヒンティングは、ある大きさで線を消してしまうためです（BIZ UDP そのものでも同じです）。
- 約物の詰め（`halt`・`vhal`）を足しました。元の BIZ UD にはありません。ブラウザの `text-spacing-trim`（Chromium は既定で働きます）で、「『 や 。」 のように続いた括弧や句読点の間のアキが、本と同じように詰まります。
- 欧文の中の記号（引用符・アポストロフィ `‘ ’ “ ”`、ダッシュ `—`、`†`・`©`・`€`・分数の `½` `⅓`・マイナス `−` など、BIZ UD と BIZ UDP で形か幅が違うもの）は、欧字の用字系の中でだけ BIZ UDP の字にしました（`locl`）。BIZ UD の `’` は全角なので、そのままでは英語の Alice’s の前後が全角ぶん空きます。日本語の文書（`lang="ja"`）の中では、英語の部分も含めてこれまでどおり BIZ UD の字（引用符は全角）で、和文の中の “ ” も全角のままです。BIZ UD の `−` は半角で、`+` `=` より横線が短いので、欧文の中では BIZ UDP の `−` にして `+` とそろえます。和文の中では BIZ UD のままです（macOS の日本語入力は、全角のマイナスにこの字を使います）。
- 名前を「読書 UD」にしました。BIZ UD明朝・BIZ UDゴシックはモリサワの商標です。等幅の印（`post.isFixedPitch`）も外しました。

くわしくは [FONTLOG.txt](FONTLOG.txt) にあります。

## 元のフォントから受け継いだこと

次のことは BIZ UD・BIZ UDP のどちらも同じで、読書 UD でも変えていません。

- ギリシャ文字とキリル文字は全角です。日本語の文章で使う幅（α波・β版など）で、BIZ UDP にもプロポーショナルな字がないため、欧文の中でも全角のままです。ギリシャ語・ロシア語などの文章や、英語の文の中の π・Ω などは、字の間が広く空きます。
- 拡張のラテン文字は、ほとんど入っていません（ラテン文字拡張 B は 208 字のうち 16 字、IPA の記号は 96 字のうち 55 字、ベトナム語などに使うラテン文字拡張追加は 256 字のうち 2 字）。入っていない字（IPA の `ɪ` など）は、ブラウザなどが次に並べたフォントで出すので、その字だけ形が変わります。

こうした文章には、ほかの欧文書体と組み合わせて使ってください。

## ライセンス

[SIL Open Font License 1.1](OFL.txt) です。個人でも商用でも無料で使え、アプリや文書に同梱して配れます。フォント単体での販売はできません。元のフォントの著作権表示は OFL.txt にあります。

リリースで配るのはフォントのファイルだけです。OFL が配るフォントの 1 つ 1 つに求める著作権表示と使用許諾の全文は、フォントの中（name テーブルの著作権表示とライセンスの欄）に入れてあります。フォントを再配布するときも、ファイルだけで足ります。

このフォントはモリサワとは関係がありません。不具合はこのリポジトリの Issue に報告してください。

## 作り方

[fontTools](https://github.com/fonttools/fonttools) で作ります。元のフォントは Google Fonts のものを、`scripts/sources.json` のコミットと SHA-256 に固定して取ってきます。`scripts/build.py` も、作る前に元のフォントの SHA-256 を確かめ、合わなければ止まります。同じ元からは同じファイルができます。

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/fetch_sources.py   # sources/ に元のフォント
.venv/bin/python scripts/build.py           # fonts/ に読書 UD
.venv/bin/python scripts/check.py           # 元のフォントと突き合わせる
```

`scripts/check.py` は、できたフォントを元のフォントと突き合わせます。欧字とその置き換え・合字・字形の候補（`aalt`）が BIZ UDP と同じか、分数（`frac`）が分数の数字だけを置き換え、数字と斜線の間が BIZ UDP の分数と同じか、作った上付きの数字の太さと高さが `¹ ² ³ ⁴` と同じくらいか、代表の和文の字と `hwid` の半角の字が BIZ UD と同じ形と字幅か、FreeType でヒンティングを動かして描いた字の画素が、欧字と欧文の中の記号は BIZ UDP と、代表の和文の字は BIZ UD と同じか（libfreetype が要ります。Debian・Ubuntu は libfreetype6）、欧文の中の記号が欧字の用字系の中でだけ BIZ UDP の字になるか、約物の詰め・縦書きの機能・名前が正しいかを確かめます。CI は push のたびに作って確かめ、`vX.Y.Z` のタグを付けるとリリースを作ります。タグ `vX.Y.Z` はフォントの版 `X.YYZ` です（`v1.0.0` は 1.000）。

リリースは後から変えられません（GitHub の immutable releases）。公開したリリースのファイルとタグは差し替えも削除もできないので、同じ版のファイルはいつダウンロードしても同じです。各ファイルの SHA-256 はリリースのページに出ており、GitHub が作るリリースの証明（attestation）で確かめられます。
