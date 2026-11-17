"""ブラウザ（Safari・Microsoft Edge など）で、確認用のページを開いて測り、結果とスクリーンショットを残す。

標準ライブラリだけで W3C WebDriver (HTTP + JSON) を話す。Selenium・Playwright は使わない。GitHub Actions の
macOS のランナーには safaridriver、Windows のランナーには msedgedriver が入っている。ページは手元の
127.0.0.1 の HTTP サーバーから配る。期待値は native_proof.py と同じく、フォントの表から求める。

  python scripts/browser_proof.py --browser safari --fonts fonts --output dist/browser/safari
  python scripts/browser_proof.py --browser edge --fonts fonts --output dist/browser/edge
  python scripts/browser_proof.py --serve --fonts fonts --output dist/browser/page   # 手で開く (WebDriver 無し)
  python scripts/browser_proof.py --validate                                         # 道具の整合 (ブラウザ無し)

--serve で開いたページは、測った結果を /result に POST して output/result.json に残す。
"""

import argparse
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

CELLS = {"〱": 2, "〲": 2, "⸺": 2, "⸻": 3}  # 縦組の 2 セル・3 セルの字 → 送り (em)
HORIZONTAL_CELLS = {"〱": 1, "〲": 1, "⸺": 2, "⸻": 3}  # 横組の送り (em)
ORIENTATIONS = ("mixed", "upright", "sideways")
FEATURES = ("normal", '"vert" 1')
SYMBOLS = "‘’“”—−¼½¾⅓⅔⅕°‼⁇⁈⁉"  # ALWAYS_UDP。native_proof の always-udp の確認文と同じ
KERN_TEXT = "T. V, W. Y, P. F, r. y, v. w,"
SIZE = 64  # px。小さいと字の送りの丸めが目立つので大きく測る

PAGE = """<!doctype html>
<meta charset="utf-8">
<title>Browser proof</title>
<style>
%(faces)s
body { margin: 8px; font: 14px sans-serif; background: #fff; color: #000; }
.row { display: flex; gap: 16px; align-items: flex-start; margin: 4px 0; }
.v { writing-mode: vertical-rl; height: 6em; font-size: 28px; line-height: 1.5; }
.cell { display: flex; flex-direction: column; align-items: flex-start; width: 92px; margin: 2px; border: 1px solid #ccc; }
.cell small { width: 90px; white-space: normal; word-break: break-all; }
#vgrid { display: flex; flex-wrap: wrap; }
.h { font-size: %(size)spx; white-space: nowrap; line-height: 1.5; }
.hidden { position: absolute; left: 0; top: 0; visibility: hidden; }
.vp { writing-mode: vertical-rl; display: inline-block; font-size: 28px; line-height: 1.5; white-space: nowrap; }
small { display: block; font: 11px monospace; }
</style>
<body>
<div id="info"></div>
<div id="stage"></div>
<div id="vgrid"></div>
<script>
const CONFIG = %(config)s;
%(script)s
</script>
"""

SCRIPT = r"""
const SIZE = CONFIG.size;
function rects(node) {
  const out = [];
  let index = 0;
  for (const ch of node.textContent) {
    const range = document.createRange();
    range.setStart(node, index); range.setEnd(node, index + ch.length);
    const r = range.getBoundingClientRect();
    out.push({c: ch, left: r.left, top: r.top, width: r.width, height: r.height});
    index += ch.length;
  }
  return out;
}
function make(parent, cls, family, text, style, label) {
  const show = label.visible && (cls === 'v' || location.hash !== '#grid');  // #grid: 縦組の一覧だけを見せる
  const box = document.createElement('div'); box.className = (cls === 'v' ? 'cell' : 'row') + (show ? '' : ' hidden');
  if (cls === 'v') parent = document.getElementById('vgrid');
  const el = document.createElement('div'); el.className = cls; el.lang = 'ja';
  el.style.fontFamily = `"${family}", serif`; el.style.cssText += style;
  el.textContent = text; box.appendChild(el);
  if (show) { const s = document.createElement('small'); s.textContent = label.text; box.appendChild(s); }
  parent.appendChild(box); return el.firstChild;
}
function inkBox(family, ch, fallback) {
  // 字の輪郭の範囲。getImageData は Safari の指紋対策で使えないので、measureText の範囲で比べる
  const g = document.createElement('canvas').getContext('2d');
  g.font = `64px "${family}", ${fallback}`;
  const m = g.measureText(ch);
  return [m.actualBoundingBoxLeft, m.actualBoundingBoxRight, m.actualBoundingBoxAscent, m.actualBoundingBoxDescent];
}
async function run() {
  const stage = document.getElementById('stage');
  const result = {userAgent: navigator.userAgent, platform: navigator.platform, dpr: devicePixelRatio, size: SIZE, fonts: {}};
  document.getElementById('info').textContent = navigator.userAgent;
  await Promise.all(CONFIG.fonts.map(f => document.fonts.load(`32px "${f.family}"`, 'あ𠮷〱')));
  await document.fonts.ready;
  const faces = {};
  document.fonts.forEach(face => { faces[face.family.replace(/"/g, '')] = face.status; });
  result.faceStatus = faces;
  CONFIG.fonts.forEach((font, index) => {
    const visible = index === CONFIG.visibleIndex, out = {};
    const fam = font.family, row = (cls, text, style, label) => make(stage, cls, fam, text, style, {visible, text: cls === 'v' ? label : `${font.name} ${label}`});
    // 横組: 2 セル・3 セルの字の送り
    out.horizontalCells = rects(row('h', 'あ' + Object.keys(CONFIG.cells).join('') + 'い', '', 'horizontal あ〱〲⸺⸻い'));
    // 横組: 17 字の字幅 (lang=ja。locl の後の BIZ UDP の字幅)
    out.symbols = rects(row('h', '文' + CONFIG.symbols + '文', '', 'ALWAYS_UDP (horizontal)'));
    // カーニング: 既定と font-kerning: none
    const widthOf = node => { const r = document.createRange(); r.selectNodeContents(node.parentNode); return r.getBoundingClientRect().width; };
    const kernOn = row('h', CONFIG.kernText, '', 'kerning (default)');
    const kernOff = row('h', CONFIG.kernText, 'font-kerning: none', 'kerning: none');
    out.kern = {on: widthOf(kernOn), off: widthOf(kernOff)};
    // 縦組: 向き × font-feature-settings × 字
    out.vertical = [];
    for (const orientation of CONFIG.orientations) for (const feature of CONFIG.features) for (const ch of Object.keys(CONFIG.cells)) {
      const node = row('v', 'あ' + ch + 'い', `text-orientation: ${orientation}; font-feature-settings: ${feature}`, `${orientation} ${feature} あ${ch}い`);
      // Safari は縦組の Range の位置が崩れる (3 字目が 0) ので、全体の長さも測る: 縮める箱 (inline-block) の高さ
      const probe = document.createElement('div'); probe.className = 'vp hidden'; probe.lang = 'ja';
      probe.style.cssText = `font-family: "${fam}", serif; text-orientation: ${orientation}; font-feature-settings: ${feature}`;
      probe.textContent = 'あ' + ch + 'い'; stage.appendChild(probe);
      out.vertical.push({orientation, feature, char: ch, rects: rects(node), extent: probe.getBoundingClientRect().height});
    }
    // 追加字 𠮷: 自分の字形が出ているか (𠮷 を持たない面 = 代わりのフォントの輪郭の範囲との違い)
    const probe = CONFIG.fonts[index].noGlyphFamily;
    const own = inkBox(fam, '𠮷', 'serif'), other = inkBox(probe, '𠮷', 'serif');
    out.kichi = {width: rects(row('h', '𠮷', '', '𠮷 (horizontal)'))[0].width, differsFromFallback: own.some((v, i) => Math.abs(v - other[i]) > 0.5), box: own, fallbackBox: other};
    result.fonts[font.name] = out;
  });
  result.faces = {};
  return result;
}
run().then(r => {
  window.__result = r;
  document.title = 'done';
  if (new URLSearchParams(location.search).get('post')) {
    fetch('/result', {method: 'POST', body: JSON.stringify(r)}).then(() => { document.title = 'posted'; });
  }
}).catch(e => { window.__result = {error: String(e && e.stack || e)}; document.title = 'error'; });
"""


def font_files(fonts: Path) -> list[Path]:
    files = sorted(fonts.glob("*.ttf"))
    if len(files) != 4:
        raise SystemExit(f"{fonts}: need four TTF files")
    return files


def build_site(fonts: Path, site: Path, visible: str = "DokushoUDMincho-Regular") -> dict:
    """ページとフォントのコピーを site に置く。戻り値はページが使う設定"""
    (site / "fonts").mkdir(parents=True, exist_ok=True)
    entries, faces = [], []
    for path in font_files(fonts):
        shutil.copyfile(path, site / "fonts" / path.name)
        # 同じファイルを、unicode-range が U+0020 だけの面でも読む。𠮷 を持たない面の描画 (= 代わりのフォント) との比較に使う
        family, empty = "DUD-" + path.stem, "DUDEmpty-" + path.stem
        for name, extra in ((family, ""), (empty, "unicode-range: U+0020;")):
            faces.append(f"@font-face {{ font-family: '{name}'; src: url('fonts/{path.name}') format('truetype'); {extra} }}")
        entries.append({"name": path.stem, "family": family, "noGlyphFamily": empty})
    config = {"fonts": entries, "visibleIndex": next(i for i, e in enumerate(entries) if e["name"] == visible),
              "cells": CELLS, "symbols": SYMBOLS, "kernText": KERN_TEXT, "size": SIZE,
              "orientations": ORIENTATIONS, "features": FEATURES}
    (site / "index.html").write_text(PAGE % {"faces": "\n".join(faces), "size": SIZE,
                                             "config": json.dumps(config, ensure_ascii=False), "script": SCRIPT}, encoding="utf-8")
    return config


class Handler(http.server.SimpleHTTPRequestHandler):
    result_path: Path | None = None

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("content-length", 0)))
        if self.path == "/result" and self.result_path:
            self.result_path.write_bytes(body)
        self.send_response(204)
        self.end_headers()


def start_server(site: Path, result_path: Path | None = None):
    handler = type("H", (Handler,), {"result_path": result_path})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), lambda *a, **k: handler(*a, directory=str(site), **k))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class WebDriver:
    """W3C WebDriver の最小のクライアント (HTTP + JSON)"""

    def __init__(self, port: int):
        self.base, self.session = f"http://127.0.0.1:{port}", None

    def call(self, method: str, path: str, body=None, timeout: float = 60):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.base + path, data=data, method=method, headers={"content-type": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read() or b"{}").get("value")

    def start(self, capabilities: dict):
        value = self.call("POST", "/session", {"capabilities": {"alwaysMatch": capabilities}}, timeout=120)
        self.session = value["sessionId"]
        self.capabilities = value.get("capabilities", {})

    def s(self, path: str) -> str:
        return f"/session/{self.session}{path}"

    def stop(self):
        if self.session:
            try:
                self.call("DELETE", self.s(""))
            except Exception:
                pass


def wait_for(port: int, seconds: float = 30):
    end = time.time() + seconds
    while time.time() < end:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=2).read()
            return
        except Exception:
            time.sleep(.3)
    raise SystemExit("the WebDriver did not start")


def free_port() -> int:
    import socket
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def driver_command(browser: str, port: int) -> tuple[list[str], dict]:
    if browser == "safari":
        return ["safaridriver", "-p", str(port)], {"browserName": "safari"}
    folder = os.environ.get("EDGEWEBDRIVER", "")
    exe = shutil.which("msedgedriver") or str(Path(folder) / ("msedgedriver.exe" if sys.platform == "win32" else "msedgedriver"))
    return [exe, f"--port={port}"], {"browserName": "MicrosoftEdge",
                                     "ms:edgeOptions": {"args": ["--headless=new", "--window-size=1400,1000", "--hide-scrollbars"]}}


def drive(browser: str, url: str, output: Path) -> dict:
    port = free_port()
    command, capabilities = driver_command(browser, port)
    process = subprocess.Popen(command, stdout=open(output / "driver.log", "wb"), stderr=subprocess.STDOUT)
    client = WebDriver(port)
    try:
        wait_for(port)
        client.start(capabilities)
        info = {"browserName": client.capabilities.get("browserName"), "browserVersion": client.capabilities.get("browserVersion"),
                "platformName": client.capabilities.get("platformName")}
        try:  # 縦組の一覧が全部入る大きさ。変えられないブラウザでは今の大きさのまま
            client.call("POST", client.s("/window/rect"), {"width": 1400, "height": 1300})
        except Exception as error:
            print(f"window size not changed: {error}")
        client.call("POST", client.s("/url"), {"url": url})
        for _ in range(100):
            title = client.call("GET", client.s("/title"))
            if title in ("done", "error"):
                break
            time.sleep(.3)
        result = client.call("POST", client.s("/execute/sync"), {"script": "return window.__result;", "args": []})
        shot = client.call("GET", client.s("/screenshot"))
        import base64
        (output / "screenshot.png").write_bytes(base64.b64decode(shot))
        result["webdriver"] = info
        return result
    finally:
        client.stop()
        process.terminate()


def compute_expected(fonts: Path) -> dict:
    """フォントの表から、ブラウザの測定値の期待値 (em) を求める"""
    import native_proof
    from fontTools.ttLib import TTFont
    expected = {}
    for path in font_files(fonts):
        with TTFont(path) as font:
            data = native_proof.expectations(font)
            from checks.fonttables import kerning_pairs
            pairs = kerning_pairs(font)
            expected[path.stem] = {
                "symbols": {c: data["horizontal"][c][1] / 24 for c in SYMBOLS},
                "kernDelta": (native_proof.kern_total(font, pairs, KERN_TEXT, False) - native_proof.kern_total(font, pairs, KERN_TEXT, True)) / 24,
            }
    return expected


def check_result(result: dict, expected: dict) -> list[str]:
    """測った値 (em) を期待と比べて、外れた項目の一覧を返す"""
    problems = []
    if "error" in result:
        return [f"page error: {result['error']}"]
    for family, status in result["faceStatus"].items():
        if status != "loaded" and not family.startswith("DUDEmpty-"):
            problems.append(f"font face {family}: status {status}")
    size = result["size"]
    for name, data in result["fonts"].items():
        for rect, (char, want) in zip(data["horizontalCells"][1:5], HORIZONTAL_CELLS.items()):
            if abs(rect["width"] / size - want) > .03:
                problems.append(f"{name} horizontal U+{ord(char):04X}: {rect['width'] / size:.3f} em, expected {want} em")
        for rect, (char, want) in zip(data["symbols"][1:-1], expected[name]["symbols"].items()):
            if abs(rect["width"] / size - want) > .03:
                problems.append(f"{name} ALWAYS_UDP U+{ord(char):04X}: {rect['width'] / size:.3f} em, expected {want:.3f} em")
        delta = (data["kern"]["off"] - data["kern"]["on"]) / size
        if abs(delta - expected[name]["kernDelta"]) > .06:
            problems.append(f"{name} kerning: {delta:.3f} em tighter than font-kerning: none, expected {expected[name]['kernDelta']:.3f} em")
        # 輪郭の範囲で代わりのフォントと見分ける方法は、Safari では効かなかった (同じ値になる)。Chromium 系だけで見る
        strict = "Chrome/" in result["userAgent"]
        if abs(data["kichi"]["width"] / size - 1) > .03 or (strict and not data["kichi"]["differsFromFallback"]):
            problems.append(f"{name} U+20BB7: width {data['kichi']['width'] / size:.3f} em, own glyph drawn: {data['kichi']['differsFromFallback']}")
        for item in data["vertical"]:
            if item["orientation"] == "mixed" and item["feature"] == "normal":
                char, unit = item["char"], size * 28 / 64  # 縦組の見本は 28px
                length = item["extent"] / unit  # あ + 字 + い の長さ。前後の仮名 1 em ずつと字の送り
                if abs(length - (CELLS[char] + 2)) > .08:
                    problems.append(f"{name} vertical (mixed) U+{ord(char):04X}: あ+字+い is {length:.3f} em long, expected {CELLS[char] + 2} em")
    return problems


def summary(result: dict) -> dict:
    """結果の主な値 (em)。成果物とログに残す"""
    size, vertical_unit = result["size"], 28
    out = {}
    for name, data in result["fonts"].items():
        out[name] = {
            "horizontalCells": [round(r["width"] / size, 3) for r in data["horizontalCells"]],
            "symbols": [round(r["width"] / size, 3) for r in data["symbols"][1:-1]],
            "kernDelta": round((data["kern"]["off"] - data["kern"]["on"]) / size, 3),
            "kichi": {"width": round(data["kichi"]["width"] / size, 3), "ownGlyph": data["kichi"]["differsFromFallback"]},
            "vertical (あ+字+い の長さ em)": {f"{v['orientation']} {v['feature']} あ{v['char']}い": round(v["extent"] / vertical_unit, 3)
                                        for v in data["vertical"]},
            "vertical (Range の位置から見た字の送り em)": {f"{v['orientation']} {v['feature']} あ{v['char']}い": round((v["rects"][2]["top"] - v["rects"][1]["top"]) / vertical_unit, 3)
                                             for v in data["vertical"]},
        }
    return out


def validate() -> int:
    """ブラウザ無しで、期待値の計算と検査の判定を、作ったとおりの結果と、1 つ変えた結果で確かめる"""
    import tempfile
    fonts = ROOT / "fonts"
    expected = compute_expected(fonts)
    size = SIZE
    result = {"size": size, "userAgent": "Chrome/synthetic", "faceStatus": {}, "fonts": {}}
    for name, exp in expected.items():
        symbols = [{"width": w * size} for w in exp["symbols"].values()]
        cells = [{"width": size}] + [{"width": w * size} for w in HORIZONTAL_CELLS.values()] + [{"width": size}]
        vertical = [{"orientation": "mixed", "feature": "normal", "char": c,
                     "rects": [{"top": 0}, {"top": 28}, {"top": 28 * (1 + n)}], "extent": 28 * (n + 2)} for c, n in CELLS.items()]
        result["fonts"][name] = {"horizontalCells": cells, "symbols": [{"width": size}] + symbols + [{"width": size}],
                                 "kern": {"on": 100, "off": 100 + exp["kernDelta"] * size},
                                 "kichi": {"width": size, "differsFromFallback": True}, "vertical": vertical}
    problems = check_result(result, expected)
    if problems:
        print("\n".join(problems))
        return 1
    broken = json.loads(json.dumps(result))
    first = next(iter(broken["fonts"].values()))
    first["vertical"][0]["extent"] = 28 * 3
    first["symbols"][2]["width"] += size * .2
    first["kern"]["off"] = first["kern"]["on"]
    first["kichi"]["differsFromFallback"] = False
    first["horizontalCells"][3]["width"] = size
    if len(check_result(broken, expected)) != 5:
        print("the browser checks missed a changed value")
        return 1
    with tempfile.TemporaryDirectory(prefix="dokusho-browser-") as temporary:
        config = build_site(fonts, Path(temporary))
        if not (Path(temporary) / "index.html").exists() or len(config["fonts"]) != 4:
            print("the page was not built")
            return 1
    print("ok: browser proof tool (expectations, checks, page)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--browser", choices=("safari", "edge"))
    parser.add_argument("--fonts", type=Path, default=ROOT / "fonts")
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "browser")
    parser.add_argument("--serve", action="store_true", help="WebDriver を使わず、ページを配るだけ (手で開く)")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    if args.validate:
        return validate()
    args.output.mkdir(parents=True, exist_ok=True)
    site = args.output / "site"
    build_site(args.fonts, site)
    if args.serve:
        server = start_server(site, args.output / "result.json")
        print(f"http://127.0.0.1:{server.server_port}/index.html?post=1  (result -> {args.output / 'result.json'})")
        threading.Event().wait()
    if not args.browser:
        parser.error("--browser is required")
    server = start_server(site)
    try:
        result = drive(args.browser, f"http://127.0.0.1:{server.server_port}/index.html", args.output)
    finally:
        server.shutdown()
    expected = compute_expected(args.fonts)
    problems = check_result(result, expected)
    (args.output / "result.json").write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    (args.output / "summary.json").write_text(json.dumps({"webdriver": result.get("webdriver"), "userAgent": result.get("userAgent"),
                                                          "problems": problems, "measured": None if "error" in result else summary(result)},
                                                         indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"webdriver": result.get("webdriver"), "userAgent": result.get("userAgent")}, ensure_ascii=False))
    for line in problems:
        print(f"::error::{line}" if os.environ.get("GITHUB_ACTIONS") else f"FAIL {line}")
    print(f"{len(problems)} browser check(s) failed" if problems else f"ok: {args.browser}: browser checks")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
