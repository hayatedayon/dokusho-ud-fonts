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
                    advance = data["expected"]["pairWidths"].get(case[0], 24)
                    glyphs, advances = [1], [advance]
                    expected = data["expected"]
                    if case[0] in ("always-udp", "ja"):
                        glyphs, advances = zip(*(expected["horizontal"][c] for c in case[-1]))
                    elif case[0] in ("kern", "kern-off"):
                        kern = expected["kernTotals"]
                        advances = [kern["off"] if case[0] == "kern-off" and engine == "coretext" else kern["on"]]
                    elif case[0].startswith("cell-"):
                        glyphs = expected["vertical"][case[0][5:]][engine]
                        advances = [24] * len(glyphs)
                    elif case[0].startswith("ss03"):
                        ss03 = expected["ss03"]
                        trial = not case[0].startswith("ss03-off")
                        if case[2]:
                            glyphs = ss03["vertical"][engine] if trial else ss03["defaultVertical"][engine]
                            advances = [24] * len(glyphs)
                        elif trial:
                            glyphs, advances = zip(*ss03["horizontal"])
                        else:
                            glyphs = ss03["default"]
                            advances = [advance for _, advance in ss03["horizontal"]]
                    record = {"engine": engine, "sample": case[0], "emSize": 24, "vertical": case[2],
                              "runs": [{"font": name, "glyphs": list(glyphs), "advances": list(advances)}]}
                    (folder / (case[0] + ".json")).write_text(json.dumps(record))
                    (folder / (case[0] + ".png")).write_bytes(base64.b64decode(png(16, 16, bytes(range(256))).split(",")[1]))
            with contextlib.redirect_stdout(io.StringIO()):
                native_proof.validate(root, engine)
            check(native_proof.check_expectations(root, engine) == [], f"native expectations reject results computed from the font: {engine}")
            for case, change in (("always-udp", lambda r: r["runs"][0]["advances"].__setitem__(2, 13)),
                                 ("always-udp", lambda r: r["runs"][0]["glyphs"].__setitem__(5, 99)),
                                 ("ja", lambda r: r["runs"][0]["glyphs"].__setitem__(25, 99)),
                                 ("kern", lambda r: r["runs"][0]["advances"].__setitem__(0, 700)),
                                 ("kern-off", lambda r: r["runs"][0]["advances"].__setitem__(0, 700)),
                                 ("cell-3031", lambda r: r["runs"][0]["glyphs"].__setitem__(1, 99)),
                                 ("ss03", lambda r: r["runs"][0]["glyphs"].__setitem__(7, 99)),
                                 ("ss03", lambda r: r["runs"][0]["advances"].__setitem__(7, 13)),
                                 ("ss03-v", lambda r: r["runs"][0]["glyphs"].__setitem__(150, 99)),
                                 ("ss03-off", lambda r: r["runs"][0]["glyphs"].__setitem__(7, 99))):
                path = root / engine / next(iter(manifest["fonts"])) / f"{case}.json"
                original = path.read_text()
                record = json.loads(original)
                change(record)
                path.write_text(json.dumps(record))
                check(native_proof.check_expectations(root, engine), f"native expectations accept a changed {case}: {engine}")
                path.write_text(original)
            native_proof.gallery(root, engine)
            check((root / "index.html").exists(), "native gallery missing")
            path = root / engine / next(iter(manifest["fonts"])) / "ja.json"
            record = json.loads(path.read_text())
            first = next(iter(manifest["fonts"]))
            for bad, fails in (({"font": "fallback.ttf", "glyphs": [1], "advances": [24]}, "check"),
                               ({"font": first, "glyphs": [0], "advances": [24]}, "check"),
                               ({"font": first, "glyphs": [1], "advances": []}, "validate"),
                               ({"font": first, "glyphs": [1], "advances": [float("inf")]}, "validate")):
                path.write_text(json.dumps(record | {"runs": [bad]}))
                if fails == "validate":
                    try:
                        native_proof.validate(root, engine)
                    except ValueError:
                        pass
                    else:
                        check(False, f"native validator accepts malformed run: {bad}")
                else:
                    check(any("ja:" in line for line in native_proof.check_expectations(root, engine)),
                          f"native checks accept a fallback or missing glyph: {bad}")
            path.write_text(json.dumps(record))
