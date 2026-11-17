#!/usr/bin/env python3
"""Python の依存 (requirements.txt) を、手元で最新にしてみて、フォントが変わるかを確かめる。

    python scripts/deps_update.py                 PyPI の最新を調べ、前後でビルドして比べ、全検査を回す
    python scripts/deps_update.py --no-check      全検査 (約 2 分) を飛ばす
    python scripts/deps_update.py --write         最後に requirements.txt を書き換える (フォントが同じときだけ)
    python scripts/deps_update.py --keep          作業用のフォルダを残す (場所を表示する)

月に 1 度の更新の道具で、Dependabot のプルリクエスト (font-diff.yml が同じ比較をする) を使わない
ときに使う。リポジトリの .venv・fonts/・dist/ には触らず、一時フォルダに前の版と最新の版の venv と
リポジトリの写しを作って、同じ SOURCE_DATE_EPOCH でビルドし、TTF と WOFF2 のバイトを比べる
(scripts/compare_fonts.py)。フォントが変わるときは、書き換えずに止まる (次のリリースのフォントが
変わるので、違いを読んで人が決める)。
新しい依存は使わない。標準ライブラリと、実行した Python の pip・venv だけで動く。
Actions の更新は Dependabot (月 1 回) に任せるので、ここでは扱わない。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = ROOT / "requirements.txt"
PIN = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s#;]+)\s*$")
IGNORE = shutil.ignore_patterns(".git", ".venv", ".yomiyasu", "fonts", "dist", "_site", "__pycache__")


def read_pins() -> list[tuple[str, str]]:
    pins = []
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = PIN.match(line)
        if not match:
            sys.exit(f"requirements.txt の行を読めません (name==version の形だけ扱います): {line!r}")
        pins.append((match[1], match[2]))
    return pins


def version_key(version: str):
    # 安定版 (数字とドットだけ) だけを比べる
    return tuple(int(part) for part in version.split("."))


def latest_on_pypi(name: str) -> str:
    with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/json", timeout=30) as response:
        data = json.load(response)
    stable = [
        v for v, files in data["releases"].items()
        if re.fullmatch(r"\d+(\.\d+)*", v) and files and not all(f.get("yanked") for f in files)
    ]
    return max(stable, key=version_key)


def run(cmd, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run([str(c) for c in cmd], check=True, **kwargs)


def make_tree(work: Path, label: str, pins: list[tuple[str, str]]) -> Path:
    """リポジトリの写しと、pins だけを入れた venv を作る。返すのは写しのフォルダ"""
    tree = work / label
    shutil.copytree(ROOT, tree, ignore=IGNORE)
    venv = tree / ".venv"
    # この Python の pip で入れる (venv に pip を入れる ensurepip が無い環境でも動かすため)
    run([sys.executable, "-m", "venv", "--without-pip", venv])
    requirements = work / f"{label}-requirements.txt"
    requirements.write_text("".join(f"{n}=={v}\n" for n, v in pins), encoding="utf-8")
    run([sys.executable, "-m", "pip", "--python", venv / "bin" / "python", "install", "--quiet",
         "--disable-pip-version-check", "-r", requirements])
    return tree


def python_of(tree: Path) -> Path:
    return tree / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def build(tree: Path, epoch: str) -> None:
    env = {**os.environ, "SOURCE_DATE_EPOCH": epoch}
    if not (tree / "sources").is_dir() or not any((tree / "sources").glob("*.ttf")):
        run([python_of(tree), tree / "scripts" / "fetch_sources.py"], cwd=tree, env=env)
    run([python_of(tree), tree / "scripts" / "build.py"], cwd=tree, env=env, stdout=subprocess.DEVNULL)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-check", action="store_true", help="全検査 (scripts/check.py) を飛ばす")
    parser.add_argument("--write", action="store_true", help="フォントが同じなら requirements.txt を書き換える")
    parser.add_argument("--keep", action="store_true", help="作業用のフォルダを残す")
    args = parser.parse_args()
    sys.stdout.reconfigure(line_buffering=True)

    pins = read_pins()
    print("==> PyPI の最新を調べる")
    new_pins = []
    for name, current in pins:
        latest = latest_on_pypi(name)
        new_pins.append((name, latest))
        print(f"  {name}: {current} -> {latest}" + ("" if latest != current else " (最新)"))
    if new_pins == pins:
        print("\nすべて最新です。")
        return 0

    work = Path(tempfile.mkdtemp(prefix="dokusho-deps-"))
    print(f"\n作業用のフォルダ: {work}")
    try:
        epoch = os.environ.get("SOURCE_DATE_EPOCH") or subprocess.run(
            ["git", "log", "-1", "--format=%ct"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
        print(f"==> 前の版と最新の版の venv・写しを作る (SOURCE_DATE_EPOCH={epoch})")
        before = make_tree(work, "before", pins)
        after = make_tree(work, "after", new_pins)
        print("==> 同じ日時でビルドする (約 1 分)")
        with ThreadPoolExecutor(2) as pool:
            for future in [pool.submit(build, t, epoch) for t in (before, after)]:
                future.result()

        print("\n==> フォントを比べる")
        compare = subprocess.run([python_of(after), after / "scripts" / "compare_fonts.py",
                                  before / "fonts", after / "fonts"], text=True)
        same = compare.returncode == 0
        if compare.returncode not in (0, 1):
            print("比べられませんでした。", file=sys.stderr)
            return 2

        checked = None
        if not args.no_check:
            print("\n==> 最新の版で全検査 (約 2 分。FreeType・HarfBuzz・unicode-data が要ります)")
            checked = subprocess.run([python_of(after), after / "scripts" / "check.py"], cwd=after).returncode == 0

        print("\n==> requirements.txt の案")
        proposal = "".join(f"{n}=={v}\n" for n, v in new_pins)
        print(proposal, end="")
        print()
        print("フォントのバイト: " + ("同じ" if same else "**違う** (上の差を読んで、更新を入れるか決める)"))
        print("全検査: " + {None: "飛ばした", True: "通った", False: "落ちた"}[checked])
        print("このほかの確認 (手で): 各パッケージの CHANGELOG で、glyf・GSUB/GPOS・otlLib・WOFF2・subset に関わる変更を読む。")
        print("見本の生成 (specimen_page.py・proof_page.py・ruby_proof.py・additions_proof.py・overflow_page.py) と")
        print("`native_proof.py --prepare` が動くことも、最新の版の venv で確かめる (docs/DEVELOPMENT.md の「依存の更新」)。")

        ok = same and checked is not False
        if args.write:
            if ok:
                REQUIREMENTS.write_text(proposal, encoding="utf-8")
                print("\nrequirements.txt を書き換えました。差分を見てコミットしてください。")
            else:
                print("\n書き換えません (フォントが違うか、全検査が落ちました)。")
        return 0 if ok else 1
    finally:
        if args.keep:
            print(f"\n作業用のフォルダを残しました: {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
