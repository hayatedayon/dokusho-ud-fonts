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

検査は `scripts/checks/` に、対象ごとのモジュールで置いてあります。`scripts/check.py` はどの検査をどの順に実行するかだけを持つ入口です。

| モジュール | 検査する内容 |
| --- | --- |
| `charset`・`names` | 文字の割り当てとグリフの並び、和文の字が BIZ UD のままか、name 表・版・OS/2、ライセンス |
| `latin` | 欧字と欧文の中の記号が BIZ UDP と同じか（置き換え・合字・`aalt`・`hwid`） |
| `hinting` | FreeType で描いた画素（ヒンティング） |
| `spacing`・`vertical` | 約物の詰め（`halt`・`palt`・`chws` など）、縦組（`vert`・`vpal`・縦組の引用符） |
| `digits`・`additions`・`marks` | 分数・`tnum`・コロン、足した文字・行メトリクス・はみ出し、結合用の記号と濁点 |
| `kerning`・`styles`・`smalltype` | `kern`、`ss01`〜`ss03`、小さい字（ルビ・小さい数字） |
| `shaping`・`references`・`woff2`・`native` | HarfBuzz で組んだ結果の比較、元のフォントに依らない基準、WOFF2、実環境の比較ツール |

引数なしの `python scripts/check.py` が全検査で、CI とリリースはこれを実行します。`--list` でモジュールの名前と中身の検査を見られ、`--only kerning,vertical` のように指定すると、そのモジュールの検査だけを実行します（作業中の確認用です）。HarfBuzz で組む検査は、いくつかのモジュールに分かれています。`shaping` は元のフォントとの組み方の比較だけで、縦組や詰めなどの組み方の検査はそれぞれのモジュールにあります。

リリースは後から変えられません（GitHub の immutable releases）。公開したリリースのファイルとタグは差し替えも削除もできないので、同じ版のファイルはいつダウンロードしても同じです。各ファイルの SHA-256 はリリースのページに出ており、GitHub が作るリリースの証明（attestation）で確かめられます。

## 読書・印刷用の見本

```sh
.venv/bin/python scripts/specimen_page.py
.venv/bin/python scripts/proof_page.py
.venv/bin/python scripts/ruby_proof.py
python3 -m http.server 8000
```

`http://localhost:8000/dist/specimen.html` は機能を切り替える見本、`dist/proof.html` は１行32字分・行送り1.75の固定版面です。画面用12・14・16px、印刷用9〜12pt、縦横組、元の BIZ UD・BIZ UDP を比較できます。印刷・PDF保存は倍率100%で使います（縦組はA4横向き）。`dist/small-type.html` は数字のヒント有無を、FreeType の実寸・拡大画像で並べます。`scripts/ruby_proof.py` が作る `dist/ruby-trial.html` はルビ仮名の試作（`ss03`）を、通常・ヒントあり、通常・ヒントなし、試作・ヒントなし、試作・ヒントありの4つで6〜10ppem に並べ、gasp を守る・守らない環境と補強量の組も比べます（約40秒。見方は [docs/RUBY.md](RUBY.md)）。

`.venv/bin/python scripts/versions_page.py` は、公開した各版を同じ文で見比べる `dist/versions.html` を作ります（ファイルを直接開けます。各版のフォントはリリースから取得します）。README の画像は `scripts/readme_images.py` で `docs/images/` に作ります。

CI も見本を生成し、比較に必要なフォントと一緒に `DokushoUD-proof` 成果物へ保存します。フォントの検証・保存を先に行い、見本の生成やアップロードの失敗はリリースを止めません。展開したルートで HTTP サーバーを起動してください。検証手順と確認済みの範囲は [docs/PROOFING.md](PROOFING.md) にあります。元フォントとの組み方の比較では新しい `kern` を切り、その効果・等幅を保つこと・文字同士が接触しないことは別に検査します。

## GitHub Pages

`.github/workflows/pages.yml` は最新のリリースのフォントから文章の見本と版の比較を作り、公開します。リリースを公開すると `release.yml` が最後にこのワークフローを起動し、手動でも実行できます。版の比較に載せる版は `scripts/versions_page.py` の `VERSIONS` に書きます。ページをまとめる処理は `scripts/pages_site.py` です。

## 追加字・行送り・実環境の比較

欧字とピリオド・コンマのカーニングは `scripts/kerning.py` で書体別に定めます。句読点は ASCII の比例幅グリフだけを右クラスへ入れ、欧字同士とは別の lookup にします。同じ lookup の先にある Class Pair サブテーブルのゼロ値に遮られないようにするためです。`check.py` は追加ペアとアクセント付きの字も、宣言値・HarfBuzz の実効値・1% em以上の輪郭間隔で照合します。`hhea` と typo の行間は1024、ほかの行メトリクスと `fsSelection` は BIZ UD と一致することを検査します。

`extra_glyphs.py` は「圭」の上部の土を平行移動し、「吉」の下部の口と組み合わせて `𠮷` を作ります。`〱 〲` は `〳/〴` と `〵` の接合辺を除いて輪郭をつなぎます。[Unicode §6.2](https://www.unicode.org/versions/Unicode17.0.0/core-spec/chapter-6/) の２セルの字という規定と、手元の Noto Serif CJK JP の横1 em・縦2 emのメトリクスを参考にしました。Noto の輪郭は使いません。

横組の見本は半分の大きさで１セル内に収め、`vert`・`vrt2` では元の線の太さと2 emの送りを使い、`split_vertical_cells` が最後に適用する複数の字への置き換えの lookup（`vert` 用と `vrt2` 用。ほかの lookup より後）を足して、その字（と `⸺` `⸻` の縦組の字）を、輪郭・縦送り・縦の原点が同じ字と空白の字に置き換えます。縦組の送りの決め方が環境で違うためです（HarfBuzz と DirectWrite は `vmtx`、CoreText と WebKitGTK は横の送り）。

DirectWrite は `vert` だけを使い、1 つの文字から出た字の縦送りの最大を最後の字の送りにして、横の送り（`hmtx` と GPOS）の合計の半分だけ字を左にずらします。CoreText は `vrt2` だけを使い、`hmtx` を足します。WebKitGTK は `hmtx` と、GPOS の `curs`（DirectWrite は使いません）の横の送りを足します。そのため `vert` の空白は縦送り0・横の送り0にして、GPOS の `curs` で横の送り1 em を足し、`vrt2` の空白は縦送り0・横の送り1 em にします。複数の字への置き換えに対応しない環境は、1 段目で止まります。

縦組専用字の上下はダッシュと同様に１行のクリップ枠ではなく２セルの縦枠で検査します。追加字にはヒントを付けません。非 BMP の `𠮷` は既存の割り当てを保った format 12 cmap に追加し、Unicode 範囲の Non-Plane 0（bit 57）は元の４書体すべてに設定済みなので、そのまま引き継ぎます。

```sh
.venv/bin/python scripts/additions_proof.py  # dist/additions.html と dist/additions/*.png
.venv/bin/python scripts/native_proof.py --prepare  # OS 非依存の資料だけを作る
```

追加字のページは４書体の12・14・16pxの FreeType 実寸・４倍画像と96px画像を保存します。既存の上下部品と並べて接合・太さ・２セルの送りを見比べられます。

`.github/workflows/native-proof.yml` は既存の build・release・pages と独立した補助 CI です（`release.yml` は `build.yml` だけを呼び、これには依存しません）。macOS の CoreText（`scripts/native/coretext.swift`）、Windows の DirectWrite（`scripts/native/directwrite.cpp`）が、同じ53条件×４書体を24pxで組みます。横縦の和英混植、句読点のペア、アクセント付きの字、追加字、17記号の `locl` 有効・無効、`ss03` の有効・無効（仮名194字、横組・縦組）を記録します。フォントはファイルから直接読みます。成果物 `DokushoUD-coretext`・`DokushoUD-directwrite` の `dist/native/index.html`、各 PNG・JSON（グリフ ID・送り・配置）、`checks-<engine>.json`（検査の結果）、フォント SHA-256、OS情報（`platform.txt`）を保存します。同じ SHA-256 の２成果物を比較し、`locl-off` の違いは後の cmap 変更の判断材料にします。`locl` 無効時も同じ字になることは合格条件にしません。CoreText と DirectWrite のどちらでも、`locl=0` を指定した結果は字形 ID と字幅が通常と同じで、`locl` が効かない環境の再現にはなりません。

実行の仕方は次の 2 つです。

| 実行 | 確かめるフォント | OS | 検査が外れたとき |
| --- | --- | --- | --- |
| 手動実行（`workflow_dispatch`） | 既定はそのブランチでビルドしたフォント。入力 `fonts=release`（と `release_tag`。空なら最新）で公開済みのリリースの TTF | 固定（`macos-15`・`windows-2025`） | advisory（ジョブは失敗しますが、実行全体は成功） |
| 定期実行（`schedule`。毎週日曜 19:17 UTC = 月曜 04:17 JST。`main` でだけ動く） | 公開中の最新のリリースの TTF（`gh release download --pattern '*.ttf'`） | `macos-latest`・`windows-latest`（最新の OS で崩れを早く見つけるため） | ジョブと実行が失敗になり、GitHub が失敗をメールで知らせる |

定期実行は、「公開中のフォントが、今の OS でまだ正しく組まれるか」を見るものなので、`main` をビルドせず、リリースのフォントを使います。実行した OS の版とフォントの出所（リリースのタグ、またはコミット）は、ジョブのログと成果物の `platform.txt` に残ります。`permissions` は `contents: read` のままで、Issue の作成や外部への通知はしません。

合否を見る検査（`scripts/native_proof.py`。期待値は、フォントの `hmtx`・`cmap`・GSUB・GPOS から求めます）は次のとおりです。

- 縦組の `〱 〲 ⸺ ⸻` の送りが、2・2・2・3 em であること。
- 17字（`ALWAYS_UDP`）の字形 ID と字幅が、横組で `locl` の後の字（BIZ UDP）と同じであること。
- カーニング（`T. V, W. Y, P. F, r. y, v. w,`）の幅と、句読点の単独ペアの幅が、GPOS の実効値と同じであること。CoreText は `kern=0` で詰めが外れ、DirectWrite は外れない（`kern` と同じ幅）ことも、環境の期待として明示しています。
- `𠮷 〱 〲` と `ja` の文の字が、cmap の字形 ID・`hmtx` の送りで出ること。
- 縦組の `〱 〲 ⸺ ⸻` の字形の並びが、CoreText は `vrt2`、DirectWrite は `vert`（`〱 〲`）と cmap の字（`⸺ ⸻`）と同じであること。
- `ss03` を指定した仮名194字（横組・縦組）が、フォントの `ss03` の置き換えどおりの字形で組まれ（縦組は CoreText が `vrt2`、DirectWrite が `vert` の後。公開済みのフォントを確かめるときは、その版の `ss03` の対象だけが変わる）、横組の送りが原字と同じであること。`ss03=0` を指定した同じ文字列は、通常の字形のままであること。
- 確認文のすべての字がこのフォントにあり、別のフォントへのフォールバックと欠落グリフ（字形 ID 0）が無いこと。

検査はギャラリー（画像と JSON）を出した後に、外れた項目をすべて集めてから失敗にします。外れた項目は、確認文・書体・字（コードポイント）・期待・実際の形で、ジョブのログ（`::error::` の注釈と、末尾の件数）と、成果物の `checks-<engine>.json` に出ます。環境で違うと分かっている縦組の `ALWAYS_UDP`（DirectWrite は `“ ”` を横組の半角の字形のまま回す）などは、合否にせず [PROOFING.md](PROOFING.md) に記録しています。

GitHub は、公開リポジトリで 60 日間アクティビティ（コミットなど）が無いと、定期実行を自動で止めます（GitHub のドキュメントによる）。止まったときは実行が来なくなるだけで、メールなどで知らされることはありません。気づくには、Actions の画面で最後の定期実行の日付を見るしかありません。この対策は入れていません。

Safari と Microsoft Edge は、同じワークフローの `browser-proof` ジョブ（advisory。定期実行でも失敗にしません）が測ります。`scripts/browser_proof.py` が、標準ライブラリだけで W3C WebDriver（HTTP + JSON）を話し、ランナーに入っている `safaridriver`（`sudo safaridriver --enable` が要ります）と `msedgedriver`（ヘッドレス）を動かします。確認用のページは手元の 127.0.0.1 から配り、`Range.getBoundingClientRect()` と縮めた箱の高さで、縦組・横組の送り、17字の字幅、カーニング、`𠮷` の収録を測ります。成果物 `DokushoUD-safari`・`DokushoUD-edge` に、測った値（`result.json`・`summary.json`）、スクリーンショット、WebDriver のログを保存します。手元では `scripts/browser_proof.py --validate`（ブラウザ無しで道具の整合を確かめる）と、`--serve`（ページを配るだけ。手や WebKitGTK で開く）が使えます。

ローカルで各 OS を使う場合は、ワークフローのコンパイル手順を実行してから `scripts/native_proof.py --renderer <実行ファイル>` を実行します。Linux で実行できるのは `--prepare` までです。

## 候補版を試してからリリースする

リリースは取り消せないので、公開前のフォントを実際の環境で試してから版を切ります。[AGENTS.md](../AGENTS.md) のリリースの手順の 1 番がこの節の内容で、推敲や `VERSION` を上げる前に済ませます。CI の成果物は既定で 1 日しか残らないため、手動実行のときだけ保存日数を延ばせます。

1. GitHub の Actions で `Build` を手動実行し（`gh workflow run build.yml --ref <ブランチ> -f retention_days=14`）、保存日数に 14 などを指定します。既定は 1 日で、`push`・`pull_request`・`release.yml` からの呼び出しは変わりません。上限は 90 日です。
2. 成果物 `DokushoUD`（フォントと SBOM）と `DokushoUD-proof`（見本）を取り、フォントを Hayate Reader などで数日読んで試します。Reader の手順は [PROOFING.md](PROOFING.md#hayate-reader-で確かめる) にあります。成果物のフォントの版番号はまだ公開済みの版のままです（`VERSION` はリリースの手順で上げます）。候補版のファイルは公開せず、配りません。公開するのはタグから作るリリースのファイルだけです。
3. `.github/workflows/native-proof.yml` を手動実行し、CoreText と DirectWrite の結果（合否の検査とギャラリー）と、Safari・Edge の測定値を見ます。定期実行もありますが、`main` でしか動かず、公開済みのフォントを確かめるものなので、候補版では手動実行します。
4. 問題が無ければ、[AGENTS.md](../AGENTS.md) のリリースの手順の 2 番（推敲）へ進みます。問題があれば直し、1 からやり直します。

## 依存の更新

依存は `requirements.txt` の 2 つ（`fonttools`、`brotli`）と、ワークフローが使う GitHub Actions（コミットの SHA で固定し、コメントに版）です。月に 1 度、Dependabot（`.github/dependabot.yml`）が更新のプルリクエストを開きます。`pip` は `fonttools` と `brotli` を 1 つに、Actions も 1 つにまとめます。公開から 7 日たった版だけを対象にします（セキュリティの更新はこの待ちの対象外です）。月に 1 度にしたのは、フォントを配るのがリリースのときだけで、早く取り込んでも利用者には届かないためです。`fonttools` 4.68 は `brotli` 1.2.1 以上を要求するので、2 つは組で上げます。

`fonttools` の更新は、できるフォントのバイトを変えうるので、取り込む前に必ず前後で比べます。

- **プルリクエストごと** `.github/workflows/font-diff.yml` が、変更の前（`main`）と後を、同じ `SOURCE_DATE_EPOCH` でそれぞれの `requirements.txt` からビルドし、4 書体の TTF と WOFF2 を比べます。違いはテーブルごとに、ジョブの要約に出ます（`scripts/compare_fonts.py`。中身が同じでバイトだけ違う（並びや圧縮だけの違い）のか、中身が違うのかも分けます）。`requirements.txt` と `.github` のほかに変更の無いプルリクエスト（依存の更新だけ）でフォントが変わると、**ジョブを失敗にします**。次のリリースのフォントが変わるので、違いを読んで人が決めます。作るスクリプトを変えるプルリクエスト（フォントの改良）では、違いは意図した変更なので、注意（notice）と要約に出すだけで、失敗にしません。権限は `contents: read` だけです。手動実行（`gh workflow run font-diff.yml --ref <ブランチ>`、`-f base=<比べる前>`）もできます。
- **手元** `.venv/bin/python scripts/deps_update.py` が、PyPI の最新を調べ、一時フォルダに前の版と最新の版の venv とリポジトリの写しを作り、同じ日時でビルドして比べ、最新の版で全検査（`scripts/check.py`）を回し、`requirements.txt` の案を出します。`--no-check` で全検査を飛ばし、`--write` で、フォントが同じで検査が通ったときだけ書き換えます。リポジトリの `.venv`・`fonts/`・`dist/` には触りません。

更新を取り込む手順です。

1. 比べた結果を読みます。フォントが同じなら、2 へ進みます。変わっていれば、どのテーブルのどこかを読み、フォントとしての意味が変わる違い（輪郭、メトリクス、GSUB・GPOS の中身）は、更新を入れず、利用者が決めます。WOFF2 の圧縮や並びだけの違いなら、そのことを記録して取り込めます。
2. 各パッケージの CHANGELOG（[fontTools の NEWS](https://github.com/fonttools/fonttools/blob/main/NEWS.rst)）で、このリポジトリが使う機能（`glyf` の組み立て、`feaLib`・`otTables` による GSUB・GPOS、WOFF2 の圧縮、`subset`、`ttLib`）に関わる変更を読みます。
3. 全検査と、見本の生成（`specimen_page.py`、`proof_page.py`、`ruby_proof.py`、`additions_proof.py`、`overflow_page.py`）、`native_proof.py --prepare` が動くことを、最新の版の venv で確かめます。
4. Actions の更新は、Dependabot のプルリクエストで、SHA とコメントの版が一緒に変わることと、リリースノートの入力や既定の動きの変更を確かめます。
5. 手元の `.venv` は、`.venv/bin/pip install -r requirements.txt` で上書きします（作り直しは要りません。CI は毎回 `requirements.txt` から作ります）。

FreeType・HarfBuzz・unicode-data（検査が使う、CI では apt で入れる外部のライブラリ）は、版を固定していません。更新のたびに、CI の `dpkg-query` の出力の版を見ます。

## 秘密情報の検査

`secrets.yml` は push・プルリクエスト・毎週日曜の定期実行で betterleaks v1.10.0 を実行します。作業ツリーと push/PR のコミット範囲を検査し、定期・手動実行は取得した全履歴を検査します。検出すると失敗し、ログでは値を伏せます。外部 API に秘密情報を送る検証は行いません。

Linux x86-64 では、リポジトリの外の空の作業フォルダを用意して次のように実行できます。公式 GitHub リリースだけから取得し、`scripts/supply_chain_tools.json` の SHA-256 と照合します。公式のチェックサムファイルがある道具は、そのファイル自体も固定した SHA-256 で確認してから照合します。ファイルが無い道具はダウンロードの SHA-256 を同じマニフェストに固定しています。既存の異なる実行ファイルは上書きしません。

```sh
python3 scripts/install_supply_chain_tools.py betterleaks \
  --bin-dir /path/to/work/bin --download-dir /path/to/work/downloads
export PATH="/path/to/work/bin:$PATH"
python3 scripts/scan_secrets.py
# 全履歴を調べる前に、全リモートブランチも取得する
git fetch origin '+refs/heads/*:refs/remotes/origin/*' --no-tags
python3 scripts/scan_secrets.py --all-history
```

`.betterleaks.toml` は組み込みの検出規則を継承します。許可するのは `tests/fixtures/widths-1.006.json` の `shaping_sha256`（組んだ字の検査結果の SHA-256）が generic-api-key として検出された場合だけです。同じファイルのほかの値や、プロバイダ固有の規則は除外しません。新たな検出は値を共有せず場所と種類を確認し、秘密情報なら削除や履歴の書き換えをせず管理者に連絡します。

## ワークフローの検査

`workflow-lint.yml` は `.github/`・道具の入手スクリプトが変わった push・プルリクエストと、週1回に actionlint 1.7.12（ShellCheck 0.11.0 も使用）と zizmor 1.32.0 を実行します。全ワークフローと Dependabot の設定を検査します。Action は完全なコミット SHA と版のコメントで固定し、Dependabot が両方を更新できる書き方を保ちます。更新後の Action を検査から外す設定はありません。

```sh
python3 scripts/install_supply_chain_tools.py actionlint shellcheck zizmor \
  --bin-dir /path/to/work/bin --download-dir /path/to/work/downloads
export PATH="/path/to/work/bin:$PATH"
actionlint
zizmor --persona pedantic --strict-collection --cache-dir /path/to/work/zizmor-cache \
  .github/workflows .github/dependabot.yml
```

`GH_TOKEN` があれば GitHub API を使う検査も実行します。手元で通信しないときは `--offline` を足します。zizmor は公式の実行ファイルを使い、フォントのビルド環境に検査用の Python 依存を混ぜません。`.github/zizmor.yml` には除外の理由を書いてあります。actionlint が新しい `$/` の自リポジトリ表記を受け付けないため、release の同じコミットの `./` 呼び出しを保ちます。native proof の全実行とリリースの各タグを独立して完走させる従来の同時実行の方針も保ちます。

## SBOM と証明

`build.yml` は `fonts/DokushoUD-<版>.cdx.json` を1つ作り、成果物 `DokushoUD` に8つのフォントと並べて保存します。`release.yml` は、後から変えられないリリースを公開する前に、その JSON も下書きに添えます。過去のリリースには追加しません。

syft 1.57.2 は、ビルドに使った venv の Python パッケージを調べます。`scripts/build_sbom.py` が `requirements.txt` の固定した依存と、そこからたどれる依存だけを残し、pip など無関係な道具を外します。`scripts/font_sbom.py` は、元の BIZ UD・BIZ UDP の8ファイル（フォント内の版、Google Fonts のコミット・URL、照合した SHA-256、OFL-1.1）と、配る4書体の TTF・WOFF2（SHA-256・版・OFL-1.1）を別々に記述します。cyclonedx-cli 0.33.1 の `merge` で3つを統合した後、リリースの主体と材料の関係を書き、参照の欠落を検査して、`validate --fail-on-errors` で CycloneDX 1.6 の形式を確かめます。

今の依存では18部品とリリースの主体、19の依存記録になります。リリースから8つの配布ファイルへ、各配布ファイルから対応する UD・UDP とビルド用の Python 依存へ関係を張ります。WOFF2 は対応する TTF にも、fonttools は brotli にもつながります。これは作るときの材料を表すもので、フォントを使うときに Python が要るという意味ではありません。

手元では、別の clean な worktree の専用 venv でビルドしてから実行します。中間ファイルのディレクトリと出力は毎回新しい場所にし、既存のファイルは上書きしません。

```sh
python3 scripts/install_supply_chain_tools.py syft cyclonedx-cli \
  --bin-dir /path/to/work/bin --download-dir /path/to/work/downloads
export PATH="/path/to/work/bin:$PATH"
SOURCE_DATE_EPOCH="$(git log -1 --format=%ct)"
export SOURCE_DATE_EPOCH
.venv/bin/python scripts/build_sbom.py --work-dir /path/to/work/sbom
cyclonedx validate --input-file fonts/DokushoUD-1.009.cdx.json --fail-on-errors
```

例の版は `scripts/spec.py` に合わせます。固定した Python 依存の未検出、元フォントの SHA-256 の不一致、出力の不足や版の不一致、統合時の部品の欠落、参照の欠落、形式の不正があると止まります。

証明には公式の `actions/attest` v4.2.2（完全な SHA で固定）を2回使います。公式の入力に従い、`subject-path` だけを渡すと全フォントと SBOM のビルドの来歴（SLSA）になり、フォントの `subject-path` と `sbom-path` を渡すと CycloneDX の SBOM の証明になります。`id-token: write` と `attestations: write` は release ジョブだけに付け、build・PR は読み取り権限を保ちます。証明は公開前に作り、証明用の束を別のリリースファイルとして配ることはしません。

同じ版のフォントと JSON をダウンロードし、`gh attestation` が使える GitHub CLI で、ビルドの来歴・各フォントの SBOM の証明・JSON 自体の来歴を確かめます。

```sh
# 1.009 は例です。ダウンロードした版のファイル名に置き換えます。
gh attestation verify DokushoUDMincho-Regular.ttf --repo hayatedayon/dokusho-ud-fonts \
  --signer-workflow hayatedayon/dokusho-ud-fonts/.github/workflows/release.yml
gh attestation verify DokushoUDMincho-Regular.ttf --repo hayatedayon/dokusho-ud-fonts \
  --signer-workflow hayatedayon/dokusho-ud-fonts/.github/workflows/release.yml \
  --predicate-type https://cyclonedx.org/bom
gh attestation verify DokushoUD-1.009.cdx.json --repo hayatedayon/dokusho-ud-fonts \
  --signer-workflow hayatedayon/dokusho-ud-fonts/.github/workflows/release.yml
```

`--signer-workflow` は、このリポジトリの試験用など、別のワークフローが作った証明を受け付けないための指定です。証明の検証はファイルのハッシュとビルド元を結び付けます。フォントに不具合が無いことや SBOM に漏れが無いことまで保証するものではありません。
