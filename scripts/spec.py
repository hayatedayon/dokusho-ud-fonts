"""読書 UD明朝・読書 UDゴシックの決まり。build.py と check.py が使う。"""

# フォントの版 (head.fontRevision と name の Version)。リリースのタグ vX.Y.Z は X.YYZ に対応する
# (v1.0.0 は 1.000、v1.2.3 は 1.023)。.github/workflows/release.yml が突き合わせる
VERSION = "1.003"
REPOSITORY = "https://github.com/hayatedayon/dokusho-ud-fonts"
COPYRIGHT = "Copyright 2026 The Dokusho UD Project Authors (https://github.com/hayatedayon/dokusho-ud-fonts)"

# 欧字 (ASCII の字と、アクセントの付いたラテン文字)。この字だけを BIZ UDP の字にする。
# × (U+00D7)・÷ (U+00F7) は和文で全角として使うので、BIZ UD のままにする
LATIN_RANGES = [(0x0020, 0x007E), (0x00C0, 0x00D6), (0x00D8, 0x00F6), (0x00F8, 0x017F)]
LATIN = [code for start, end in LATIN_RANGES for code in range(start, end + 1)]

# 欧文の中でだけ BIZ UDP の字にする記号 (latin_symbols.py)。文字の割り当ては BIZ UD のままで、
# 欧字の用字系 (latn) の中で、日本語の文書 (lang="ja") でなければ置き換える。引用符・
# アポストロフィ (‘ ’ “ ”) は BIZ UD では全角で、欧文の中では前後が全角ぶん空く。この範囲の
# うち、BIZ UD と BIZ UDP で形か幅が違うものだけを選ぶ
LATIN_SYMBOL_RANGES = [
    (0x00A0, 0x00BF),  # ラテン 1 補助の記号 (« » · © など)
    (0x00D7, 0x00D7),  # ×
    (0x00F7, 0x00F7),  # ÷
    (0x2010, 0x205E),  # 一般句読点 (‐ — ‘ ’ “ ” † • など)
    (0x20A0, 0x20C0),  # 通貨記号 (€ など)
    (0x2100, 0x214F),  # 文字様記号 (™ など)
]
LATIN_SYMBOLS = [code for start, end in LATIN_SYMBOL_RANGES for code in range(start, end + 1)]

# 欧字から置き換える GSUB の機能。BIZ UDP は、ここで欧字を自分の幅のグリフにつなぐ
# (vrt2 は縦組で横に倒した欧字、zero は斜線の 0、frac・numr は分数の斜線、sups は上付き)。
# fwid (全角の欧字) は BIZ UD と同じなので触らない
LATIN_FEATURES = ["frac", "numr", "sups", "zero", "vrt2"]

WEIGHTS = ["Regular", "Bold"]

FAMILIES = [
    {
        "key": "Mincho",
        "ud": "BIZUDMincho",
        "udp": "BIZUDPMincho",
        "source_name": "BIZ UDMincho",
        "name_en": "Dokusho UD Mincho",
        "name_ja": "読書 UD明朝",
        "postscript": "DokushoUDMincho",
    },
    {
        "key": "Gothic",
        "ud": "BIZUDGothic",
        "udp": "BIZUDPGothic",
        "source_name": "BIZ UDGothic",
        "name_en": "Dokusho UD Gothic",
        "name_ja": "読書 UDゴシック",
        "postscript": "DokushoUDGothic",
    },
]


def output_name(family: dict, weight: str) -> str:
    return f"{family['postscript']}-{weight}.ttf"
