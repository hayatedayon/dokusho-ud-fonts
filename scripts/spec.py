"""読書 UD明朝・読書 UDゴシックの決まり。build.py と check.py が使う。"""

# フォントの版 (head.fontRevision と name の Version)。リリースのタグ vX.Y.Z は X.YYZ に対応する
# (v1.0.0 は 1.000、v1.2.3 は 1.023)。.github/workflows/release.yml が突き合わせる
VERSION = "1.005"
REPOSITORY = "https://github.com/hayatedayon/dokusho-ud-fonts"
COPYRIGHT = "Copyright 2026 The Dokusho UD Project Authors (https://github.com/hayatedayon/dokusho-ud-fonts)"

# 欧字 (ASCII の字と、アクセントの付いたラテン文字)。この字だけを BIZ UDP の字にする。
# × (U+00D7)・÷ (U+00F7) は和文で全角として使うので、BIZ UD のままにする。範囲のうち、BIZ UD と
# BIZ UDP のどちらにも無い字は飛ばす (片方にだけある字があれば、build.py が止まる)
LATIN_RANGES = [
    (0x0020, 0x007E), (0x00C0, 0x00D6), (0x00D8, 0x00F6), (0x00F8, 0x017F),
    # ラテン文字拡張 B (BIZ UD の ǎ ǐ ǒ などピンインの字は全角で、語の途中が大きく空く)・
    # IPA の記号・前進を伴う修飾文字 (ˈ ː、声調の ˥ など)
    (0x0180, 0x02FF),
    (0x1E00, 0x1EFF),  # ラテン文字拡張追加 (Ḿ ḿ)
    (0x2074, 0x2074),  # ⁴ (¹ ² ³ は、sups の置き換え先として BIZ UDP の字になる。⁴ だけ幅が違った)
    (0xFB00, 0xFB06),  # ラテン文字の合字 (ﬁ ﬂ)
]
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
    (0x2150, 0x215F),  # 分数 (⅓ ⅔ ⅕。¼ ½ ¾ はラテン 1 補助にあり、そろえる)
]
LATIN_SYMBOLS = [code for start, end in LATIN_SYMBOL_RANGES for code in range(start, end + 1)]

# BIZ UDP のヒンティングを付けない字 (hinting.py)。細い横線だけの字で、BIZ UDP のヒンティングは、
# ある大きさで線の高さを 0 に丸めて消してしまう (FreeType では何も描かれず、Windows ではごく薄い
# 線になる。BIZ UDP そのものでも同じ)。ハイフン・下線・ソフトハイフン・マクロン・エンダッシュ・
# エムダッシュ・上線。1.003 までと同じく、命令の無いまま描く。check.py が、ヒンティングで消える
# 字がほかに無いことを確かめる
UNHINTED = [0x002D, 0x005F, 0x00AD, 0x00AF, 0x2013, 0x2014, 0x203E]

# 欧字から置き換える GSUB の機能。BIZ UDP は、ここで欧字を自分の幅のグリフにつなぐ
# (vrt2 は縦組で横に倒した欧字、zero は斜線の 0、frac・numr は分数の斜線、sups は上付き)。
# fwid (全角の欧字) は BIZ UD と同じなので触らない
LATIN_FEATURES = ["frac", "numr", "sups", "zero", "vrt2"]

# 欧字から始まる合字 (GSUB の ligature) を置き換える機能。BIZ UDP は、ccmp と liga で、f i を ﬁ に、
# æ ə ɑ などと結合用のアクセントを 1 つの字につなぐ (BIZ UD は f i をつながず、アクセントの付いた
# 字は BIZ UD の幅の字につなぐ)。dlig (!? など) は、欧文の中では locl で BIZ UDP の字になるので
# 触らない
LATIN_LIGATURE_FEATURES = ["ccmp", "liga"]

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
