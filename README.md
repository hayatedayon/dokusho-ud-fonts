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

縦書きの字形（`vert`・`vrt2`）と縦の字送り、JIS 第 1・第 2 水準の漢字は BIZ UD のままです。

## 変えたところ

- 欧字（U+0020–007E、U+00C0–00D6、U+00D8–00F6、U+00F8–017F）の形・字幅・縦の字送りを BIZ UDP のものにしました。× と ÷ は和文で全角として使うので、BIZ UD のままです。
- その欧字からの置き換え（`frac`・`numr`・`sups`・`zero`・`vrt2`。縦組で横に倒した欧字など）を BIZ UDP と同じにしました。
- BIZ UDP から持ってきた字（欧字・欧文の中の記号など）には、BIZ UDP のヒンティングを付けています。BIZ UD と BIZ UDP は cvt（ヒンティングに使う値の表）と prep が違うので、BIZ UDP の cvt と prep を BIZ UD のものの後ろに付け足し、命令が指す cvt の番号をずらしています。小さな文字の欧字も、BIZ UDP と同じ命令と値で描かれます（1.003 までは命令を外していたため、Windows の小さな文字では、欧字だけが少し薄く、ぼやけて見えました）。ただし、ハイフン・下線・ソフトハイフン・マクロン・エンダッシュ・エムダッシュ・上線の 7 字は、これまでどおりヒンティングを付けていません。細い横線だけの字で、BIZ UDP のヒンティングは、ある大きさで線を消してしまうためです（BIZ UDP そのものでも同じです）。
- 約物の詰め（`halt`・`vhal`）を足しました。元の BIZ UD にはありません。ブラウザの `text-spacing-trim`（Chromium は既定で働きます）で、「『 や 。」 のように続いた括弧や句読点の間のアキが、本と同じように詰まります。
- 欧文の中の記号（引用符・アポストロフィ `‘ ’ “ ”`、ダッシュ `—`、`†`・`©`・`€` など、BIZ UD と BIZ UDP で形か幅が違うもの）は、欧字の用字系の中でだけ BIZ UDP の字にしました（`locl`）。BIZ UD の `’` は全角なので、そのままでは英語の Alice’s の前後が全角ぶん空きます。日本語の文書（`lang="ja"`）の中では、英語の部分も含めてこれまでどおり BIZ UD の字（引用符は全角）で、和文の中の “ ” も全角のままです。
- 名前を「読書 UD」にしました。BIZ UD明朝・BIZ UDゴシックはモリサワの商標です。等幅の印（`post.isFixedPitch`）も外しました。

くわしくは [FONTLOG.txt](FONTLOG.txt) にあります。

## 元のフォントから受け継いだこと

次のことは BIZ UD・BIZ UDP のどちらも同じで、読書 UD でも変えていません。

- ギリシャ文字とキリル文字は全角です。日本語の文章で使う幅（α波・β版など）で、BIZ UDP にもプロポーショナルな字がないため、欧文の中でも全角のままです。ギリシャ語・ロシア語などの文章や、英語の文の中の π・Ω などは、字の間が広く空きます。
- 拡張のラテン文字は、ほとんど入っていません（ラテン文字拡張 B は 208 字のうち 16 字、ベトナム語などに使うラテン文字拡張追加は 256 字のうち 2 字）。入っていない字は、ブラウザなどが次に並べたフォントで出すので、その字だけ形が変わります。

こうした文章には、ほかの欧文書体と組み合わせて使ってください。

## ライセンス

[SIL Open Font License 1.1](OFL.txt) です。個人でも商用でも無料で使え、アプリや文書に同梱して配れます。フォント単体での販売はできません。元のフォントの著作権表示は OFL.txt にあります。

リリースで配るのはフォントのファイルだけです。OFL が配るフォントの 1 つ 1 つに求める著作権表示と使用許諾の全文は、フォントの中（name テーブルの著作権表示とライセンスの欄）に入れてあります。フォントを再配布するときも、ファイルだけで足ります。

このフォントはモリサワとは関係がありません。不具合はこのリポジトリの Issue に報告してください。

## 作り方

[fontTools](https://github.com/fonttools/fonttools) で作ります。元のフォントは Google Fonts のものを、`scripts/sources.json` のコミットと SHA-256 に固定して取ってきます。同じ元からは同じファイルができます。

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/fetch_sources.py   # sources/ に元のフォント
.venv/bin/python scripts/build.py           # fonts/ に読書 UD
.venv/bin/python scripts/check.py           # 元のフォントと突き合わせる
```

`scripts/check.py` は、欧字が BIZ UDP と、和文が BIZ UD と同じ形と字幅か、FreeType でヒンティングを動かして描いた字の画素が、欧字と欧文の中の記号は BIZ UDP と、和文は BIZ UD と同じか（libfreetype が要ります。Debian・Ubuntu は libfreetype6）、欧文の中の記号が欧字の用字系の中でだけ BIZ UDP の字になるか、縦書きの機能と名前が正しいかを確かめます。CI は push のたびに作って確かめ、`vX.Y.Z` のタグを付けるとリリースを作ります。タグ `vX.Y.Z` はフォントの版 `X.YYZ` です（`v1.0.0` は 1.000）。

リリースは後から変えられません（GitHub の immutable releases）。公開したリリースのファイルとタグは差し替えも削除もできないので、同じ版のファイルはいつダウンロードしても同じです。各ファイルの SHA-256 はリリースのページに出ており、GitHub が作るリリースの証明（attestation）で確かめられます。
