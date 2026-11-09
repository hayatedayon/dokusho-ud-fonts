"""GitHub Pages に載せるページを _site/ に作る。

文章の見本を入口 (index.html) にして、版の比較 (versions.html) へつなぐ。dist/ の見本と比較のページ、
見本が読むフォント、OFL の全文をまとめる。先に specimen_page.py と versions_page.py を実行しておく。

    python3 scripts/pages_site.py
"""

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
SITE = ROOT / "_site"
RELEASES = "https://github.com/hayatedayon/dokusho-ud-fonts/releases/latest"
REPOSITORY = "https://github.com/hayatedayon/dokusho-ud-fonts"

INTRO = ('<p class="note">読書や組版のために調整した日本語フォントです。仮名と漢字は全角のマス目に並び、欧字は字ごとの幅で組みます。'
         f'<a href="{RELEASES}">ダウンロード</a> ／ <a href="versions.html">版ごとの変化</a> ／ '
         f'<a href="{REPOSITORY}">GitHub</a> ／ <a href="OFL.txt">ライセンス</a></p>')
BACK = (f'<p class="lead"><a href="index.html">文章の見本</a> ／ <a href="{RELEASES}">ダウンロード</a> ／ '
        f'<a href="{REPOSITORY}">GitHub</a></p>')


def specimen() -> str:
    page = (DIST / "specimen.html").read_text(encoding="utf-8")
    page = page.replace("../fonts/", "fonts/").replace("../sources/", "sources/")
    page, count = re.subn(r'<p class="note"><a href="proof\.html">.*?</p>', INTRO, page, count=1, flags=re.S)
    if count != 1:
        raise SystemExit("specimen.html: the links to the proofs were not found")
    return page


def versions() -> str:
    page = (DIST / "versions.html").read_text(encoding="utf-8")
    marker = '<nav class="toc">'
    if page.count(marker) != 1:
        raise SystemExit("versions.html: the table of contents was not found")
    return page.replace(marker, BACK + marker)


def main() -> int:
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir()
    (SITE / "index.html").write_text(specimen(), encoding="utf-8")
    (SITE / "versions.html").write_text(versions(), encoding="utf-8")
    shutil.copy(ROOT / "OFL.txt", SITE / "OFL.txt")
    for folder in ("fonts", "sources"):
        (SITE / folder).mkdir()
        for path in (ROOT / folder).glob("*.ttf"):
            shutil.copy(path, SITE / folder / path.name)
    size = sum(p.stat().st_size for p in SITE.rglob("*") if p.is_file())
    print(f"{SITE}: {size // (1024 * 1024)} MiB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
