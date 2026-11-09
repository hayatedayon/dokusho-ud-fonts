# 読書 UD の作り方と確認

フォントのビルド、検査、見本の作り方です。

## 作り方

[fontTools](https://github.com/fonttools/fonttools) で作ります。元のフォントは Google Fonts のものを、`scripts/sources.json` のコミットと SHA-256 に固定して取ってきます。`scripts/build.py` も、作る前に元のフォントの SHA-256 を確かめ、合わなければ止まります。同じ元からは同じファイルができます。フォント内の版番号（`scripts/spec.py` の `VERSION`）は、その版を公開するまで上げません。未公開の変更は FONTLOG の次期版の項に記録します。

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/fetch_sources.py   # sources/ に元のフォント
.venv/bin/python scripts/build.py           # fonts/ に読書 UD
.venv/bin/python scripts/check.py           # 元のフォントと突き合わせる
```

`scripts/check.py` は、できたフォントを元のフォントと突き合わせます。欧字とその置き換え・合字・字形の候補（`aalt`）が BIZ UDP と同じか、分数（`frac`）が分数の数字だけを置き換え、数字と斜線の間が BIZ UDP の分数と同じか、作った上付きの数字の太さと高さが `¹ ² ³ ⁴` と同じくらいか、代表の和文の字と `hwid` の半角の字が BIZ UD と同じ形と字幅か、FreeType でヒンティングを動かして描いた字の画素が、欧字と欧文の中の記号は BIZ UDP と、代表の和文の字は BIZ UD と同じか（libfreetype が要ります。Debian・Ubuntu は libfreetype6）、欧文の中の記号が欧字の用字系の中でだけ BIZ UDP の字になるか、約物の詰め（`halt`・`vhal`）とプロポーショナル機能（`palt`・`vpal`）・`tnum`・数字の間のコロン・結合用の記号の付く位置・縦書きの機能・足した文字・名前が正しいか、行の上と下（`usWinAscent`・`usWinDescent`。Windows の GDI はその外を描きません）からのはみ出しが元のフォントより増えていないかを確かめます。また、HarfBuzz（Chromium・Firefox・Android などが使う、文字を並べる仕組み）で実際に組んで、字を変えていない文字が和文の中で BIZ UD と同じに、欧字と欧文の中の記号が英語の文の中で BIZ UDP と同じに組まれるか、BIZ UD の合字と異体字（IVS）が同じに組まれるか、見えない文字が隠れるか、結合用の記号が前の字に乗るかを確かめます。足した機能が元の振る舞いを変えてしまうこと（1.002 から結合用の記号が前の字に乗らず、1.003 から英語の文の中のソフトハイフンが隠れていませんでした）を見つけるためです。libharfbuzz と Unicode の文字のデータが要ります（Debian・Ubuntu は libharfbuzz0b と unicode-data）。はみ出す字（`‚` `„` と、明朝 Bold のギリシャ文字のアクセント付きの字。BIZ UD・BIZ UDP と同じ）は、`scripts/overflow_page.py` が `dist/overflow.html` に描きます。CI は push のたびに作って確かめ、`vX.Y.Z` のタグを付けるとリリースを作ります。タグ `vX.Y.Z` はフォントの版 `X.YYZ` です（`v1.0.0` は 1.000）。

リリースは後から変えられません（GitHub の immutable releases）。公開したリリースのファイルとタグは差し替えも削除もできないので、同じ版のファイルはいつダウンロードしても同じです。各ファイルの SHA-256 はリリースのページに出ており、GitHub が作るリリースの証明（attestation）で確かめられます。

## 読書・印刷用の見本

```sh
.venv/bin/python scripts/specimen_page.py
.venv/bin/python scripts/proof_page.py
python3 -m http.server 8000
```

`http://localhost:8000/dist/specimen.html` は機能を切り替える見本、`dist/proof.html` は１行32字分・行送り1.75の固定版面です。画面用12・14・16px、印刷用9〜12pt、縦横組、元の BIZ UD・BIZ UDP を比較できます。印刷・PDF保存は倍率100%で使います（縦組はA4横向き）。`dist/small-type.html` は数字のヒント有無とルビ仮名の試作を、FreeType の実寸・拡大画像で並べます。

`.venv/bin/python scripts/versions_page.py` は、公開した各版を同じ文で見比べる `dist/versions.html` を作ります（ファイルを直接開けます。各版のフォントはリリースから取得します）。README の画像は `scripts/readme_images.py` で `docs/images/` に作ります。

CI も見本を生成し、比較に必要なフォントと一緒に `DokushoUD-proof` 成果物へ保存します。フォントの検証・保存を先に行い、見本の生成やアップロードの失敗はリリースを止めません。展開したルートで HTTP サーバーを起動してください。検証手順と確認済みの範囲は [docs/PROOFING.md](PROOFING.md) にあります。元フォントとの組み方の比較では新しい `kern` を切り、その効果・等幅を保つこと・文字同士が接触しないことは別に検査します。

## GitHub Pages

リリースの公開時と手動実行のとき、`.github/workflows/pages.yml` が最新のリリースのフォントから文章の見本と版の比較を作り、公開します。ページをまとめる処理は `scripts/pages_site.py` です。
