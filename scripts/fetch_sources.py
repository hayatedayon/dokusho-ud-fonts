"""元のフォント (Google Fonts の BIZ UD・BIZ UDP) を sources/ に取ってくる。

版は sources.json のコミットに固定し、SHA-256 が合わなければ止める。既にあって
SHA-256 が合うものは取り直さない。
"""

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "sources"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    spec = json.loads((Path(__file__).parent / "sources.json").read_text(encoding="utf-8"))
    SOURCES.mkdir(exist_ok=True)
    base = spec["repository"].replace("https://github.com/", "https://raw.githubusercontent.com/")
    for name, entry in spec["files"].items():
        target = SOURCES / name
        if target.exists() and sha256(target) == entry["sha256"]:
            continue
        url = f"{base}/{spec['commit']}/{entry['path']}"
        print(f"fetch {url}")
        with urllib.request.urlopen(url) as response:
            data = response.read()
        digest = hashlib.sha256(data).hexdigest()
        if digest != entry["sha256"]:
            print(f"{name}: SHA-256 {digest}, expected {entry['sha256']}", file=sys.stderr)
            return 1
        target.write_bytes(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
