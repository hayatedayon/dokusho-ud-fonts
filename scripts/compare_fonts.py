#!/usr/bin/env python3
"""2 つのフォルダの読書 UD (fonts/*.ttf と fonts/*.woff2) を比べ、違いをテーブルごとに Markdown で出す。

    python scripts/compare_fonts.py <前のフォルダ> <後のフォルダ>

同じなら 0、違いがあれば 1、比べられなければ 2 で終わる。
ファイルの SHA-256 が同じなら同じ。違うファイルは、テーブルごとに
  - バイト列が同じか
  - 違えば、TTX (XML) に書き出した中身が同じか (同じなら並びや圧縮だけの違い、違えば意味が変わっている)
を調べ、中身の違う行の数と最初のいくつかを示す。
CI の font-diff.yml (プルリクエストごと) と scripts/deps_update.py (手元の依存の更新) が使う。
"""
import difflib
import hashlib
import io
import sys
from pathlib import Path

from fontTools.ttLib import TTFont

SHOWN_LINES = 6


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def table_xml(font: TTFont, tag: str) -> list[str]:
    buffer = io.StringIO()
    font.saveXML(buffer, tables=[tag], newlinestr="\n")
    return buffer.getvalue().splitlines()


def compare_tables(before: Path, after: Path) -> list[str]:
    a, b = TTFont(before), TTFont(after)
    lines = []
    tags_a, tags_b = set(a.reader.keys()), set(b.reader.keys())
    for tag in sorted(tags_a - tags_b):
        lines.append(f"- `{tag}`: 後に無い")
    for tag in sorted(tags_b - tags_a):
        lines.append(f"- `{tag}`: 後で増えた")
    for tag in sorted(tags_a & tags_b):
        raw_a, raw_b = a.reader[tag], b.reader[tag]
        if raw_a == raw_b:
            continue
        xml_a, xml_b = table_xml(a, tag), table_xml(b, tag)
        size = f"{len(raw_a)} → {len(raw_b)} バイト"
        if xml_a == xml_b:
            lines.append(f"- `{tag}`: バイト列だけ違う (中身は同じ。並びや圧縮の違い。{size})")
            continue
        diff = [d for d in difflib.unified_diff(xml_a, xml_b, lineterm="", n=0) if d[:1] in "+-" and d[:3] not in ("+++", "---")]
        lines.append(f"- `{tag}`: **中身が違う** ({size}、違う行 {len(diff)})")
        for d in diff[:SHOWN_LINES]:
            lines.append(f"  - `{d.strip()[:160]}`")
    return lines


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    before_dir, after_dir = Path(argv[1]), Path(argv[2])
    names = sorted({p.name for d in (before_dir, after_dir) for p in d.glob("*") if p.suffix in (".ttf", ".woff2")})
    if not names:
        print(f"比べるフォントが {before_dir} と {after_dir} にありません", file=sys.stderr)
        return 2
    differs = False
    out = []
    for name in names:
        a, b = before_dir / name, after_dir / name
        if not a.exists() or not b.exists():
            out.append(f"### {name}\n\n片方にしかありません ({'前' if a.exists() else '後'}のみ)\n")
            differs = True
            continue
        if sha256(a) == sha256(b):
            continue
        differs = True
        out.append(f"### {name}\n\nSHA-256 が違います。サイズ {a.stat().st_size} → {b.stat().st_size} バイト\n")
        if name.endswith(".woff2"):
            ttf_a, ttf_b = a.with_suffix(".ttf"), b.with_suffix(".ttf")
            if ttf_a.exists() and ttf_b.exists() and sha256(ttf_a) == sha256(ttf_b):
                out.append("同名の TTF は同じなので、WOFF2 の圧縮だけが違います。\n")
                continue
        out.append("\n".join(compare_tables(a, b) or ["- テーブルのバイト列はすべて同じ (ファイルの並びなどだけ違う)"]) + "\n")
    print(f"{len(names)} ファイルを比べました。" + ("違いがあります。\n" if differs else "すべて SHA-256 まで同じです。\n"))
    print("\n".join(out))
    return 1 if differs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
