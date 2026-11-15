"""実環境の描画比較ツール (scripts/native_proof.py) の読み取り部分。"""

from pathlib import Path

from fontTools.ttLib import TTFont

import spec

from .common import check


def check_native_proof_tools() -> None:
    """OS 非依存の資料・読み取り部分だけをダミーで検査する。ネイティブ描画の実施ではない。"""
    import base64
    import contextlib
    import io
    import json
    import tempfile
    import native_proof
    from proof_page import png
    with tempfile.TemporaryDirectory(prefix="dokusho-native-") as temporary:
        root = Path(temporary)
        fonts = native_proof.prepare(root)
        manifest = json.loads((root / "manifest.json").read_text())
        cases = (root / "cases.tsv").read_text(encoding="utf-8").splitlines()
        check(len(cases) == len(native_proof.CASES), "native corpus lost cases")
        symbols = next(c[-1] for c in native_proof.CASES if c[0] == "always-udp")
        check(all(chr(c) in symbols for c in spec.ALWAYS_UDP), "native corpus omits ALWAYS_UDP symbols")
        for path in fonts:
            with TTFont(path) as font:
                missing = {c for case in native_proof.CASES for c in case[-1] if ord(c) not in font.getBestCmap()}
                check(not missing, f"native corpus needs fallback in {path.name}: {missing}")
        for engine in ("coretext", "directwrite"):
            for name, data in manifest["fonts"].items():
                folder = root / engine / name
                folder.mkdir(parents=True)
                for case in native_proof.CASES:
                    advance = data["pairWidths"].get(case[0], 24)
                    record = {"engine": engine, "sample": case[0], "emSize": 24, "vertical": case[2],
                              "runs": [{"font": name, "glyphs": [1], "advances": [advance]}]}
                    (folder / (case[0] + ".json")).write_text(json.dumps(record))
                    (folder / (case[0] + ".png")).write_bytes(base64.b64decode(png(16, 16, bytes(range(256))).split(",")[1]))
            with contextlib.redirect_stdout(io.StringIO()):
                native_proof.validate(root, engine)
            native_proof.gallery(root, engine)
            check((root / "index.html").exists(), "native gallery missing")
            path = root / engine / next(iter(manifest["fonts"])) / "ja.json"
            record = json.loads(path.read_text())
            for bad in ({"font": "fallback.ttf", "glyphs": [1], "advances": [24]},
                        {"font": next(iter(manifest["fonts"])), "glyphs": [0], "advances": [24]},
                        {"font": next(iter(manifest["fonts"])), "glyphs": [1], "advances": []}):
                path.write_text(json.dumps(record | {"runs": [bad]}))
                try:
                    native_proof.validate(root, engine)
                except ValueError:
                    pass
                else:
                    check(False, f"native validator accepts malformed run: {bad}")
            path.write_text(json.dumps(record))
