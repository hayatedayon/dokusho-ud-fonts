# このリポジトリで守るルール

作り方と確認の手順は [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) にあります。

## 版

- `scripts/spec.py` の `VERSION` はその版を公開するまで上げません。
- 未公開の変更は新しい版を作らず `FONTLOG.txt` の次期版の項にまとめます。古くなった記述も直します。

## 文書の参照

- 文書（`README.md`、`docs/`、`FONTLOG.txt`）で指すコミットは、`main` から辿れるものだけにします。作業ブランチの名前と、作業ブランチにしかないコミットは書きません。作業ブランチは消すので、参照が切れるためです。
- 作業ブランチのコミットを `main` に取り込むときは、`git cherry-pick` に `-x` を付けません。`-x` はコミットのメッセージに取り込み元のコミット（作業ブランチにしかないもの）を書き込み、公開した後は消せないためです。どこから取り込んだかを残すときは、作業ブランチの名前やコミットではなく、内容で書きます。

## リリース

リリースは後から変えられません（GitHub の immutable releases）。公開したファイルとタグは、差し替えも削除もできません。リリース文だけは編集できます。次の順で進めます。

1. **候補版で試します。** `build.yml` を手動実行して成果物の保存日数を延ばし（[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) の「候補版を試してからリリースする」）、そのフォントを Hayate Reader などで試して、見つけた問題を直したか、直さないと決めたかを伝えます。あわせて `native-proof.yml` を実行し、CoreText と DirectWrite の合否の検査に加えて、Safari と Edge の測定値も見ます。週 1 回の定期実行が失敗のメールを送ってきたら、公開中のフォントが今の OS で崩れている可能性があるので、内容を確かめます。定期実行が止まっていないかも確かめます（下の「定期実行」）。
2. **`/yomiyasu` でドキュメントを推敲します。** 対象はそのリリースで変えた日本語の文書（`README.md`、`docs/*.md` など）です。この工程は省略できません。「次期版では」のような未公開の版の書き方もここで直し、推敲の結果をコミットします。英語の文書は内容を日本語版に合わせます。
3. `spec.py` の `VERSION` を上げ、`FONTLOG.txt` のその版の日付を実際のリリース日に直します。`scripts/versions_page.py` の `VERSIONS` に、その版の項（日付、概要、見本）を足します。ここまでをコミットして `main` にプッシュし、CI の成功を確かめます。
4. タグのプッシュはやり直せないので、直前に確認を取ります。
5. 注釈付きタグを付けます。版 X.YYZ のタグは vX.Y.Z で（1.005 は `v1.0.5`）、メッセージは `読書 UD明朝・読書 UDゴシック 1.005` の形式です。プッシュすると `release.yml` がビルド、確認、公開まで行います。
6. 自動生成のリリース文は `Full Changelog` だけなので、公開後に `gh release edit --notes-file` で書きます。
   公開したフォントと SBOM の証明を `gh attestation verify` で確かめます（[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) の「SBOM と証明」）。
7. GitHub Pages の版の比較に新しい版が出ていることを確かめます。`release.yml` が公開の最後に `pages.yml` を起動します。起動していなければ `gh workflow run pages.yml --ref main` で実行します。

## リリース文の書式

- 長文にせず、箇条書きにします。
- 日本語、`---`、英語の順に、同じ内容を書きます。
- `FONTLOG.txt` へのリンク（`blob/<tag>/FONTLOG.txt`）と `**Full Changelog**` を残します。
- 変更が多い版は、「欧字」「新しい機能」「修正」などの見出しで分類します。

## 依存の更新

`requirements.txt` を更新するときは、`scripts/deps_update.py` か `font-diff.yml` で、更新の前後のフォントのバイトを比べてから取り込みます。フォントが変わるときは、更新を入れず、利用者が決めます。

## 定期実行

`native-proof.yml`・`secrets.yml`・`workflow-lint.yml` は週 1 回、定期実行で動きます。GitHub は、公開リポジトリで 60 日間コミットなどの動きが無いと、定期実行を自動で止めます。止めたことを知らせるメールは、cron の行を最後に変えた人に届きます。リリースの前と、しばらく変更が無かった後には、`gh workflow list --all -R hayatedayon/dokusho-ud-fonts` でこの 3 つが `active` かを確かめ、`disabled_inactivity` になっていれば `gh workflow enable <ファイル名>` で戻します。
