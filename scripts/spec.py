"""読書 UD明朝・読書 UDゴシックの決まり。build.py と check.py が使う。"""

# フォントの版 (head.fontRevision と name の Version)。リリースのタグ vX.Y.Z は X.YYZ に対応する
# (v1.0.0 は 1.000、v1.2.3 は 1.023)。.github/workflows/release.yml が突き合わせる
# 次の版を公開するまでは、公開済みの版を保つ。未公開の変更は FONTLOG に記録する。
VERSION = "1.008"
REPOSITORY = "https://github.com/hayatedayon/dokusho-ud-fonts"
COPYRIGHT = "Copyright 2026 The Dokusho UD Project Authors (https://github.com/hayatedayon/dokusho-ud-fonts)"

# 欧字 (ASCII の字と、拡張のラテン文字・IPA の記号など)。この字だけを BIZ UDP の字にする。
# × (U+00D7)・÷ (U+00F7) は和文で全角として使うので、ここには入れない (欧文の中でだけ、
# LATIN_SYMBOLS として BIZ UDP の字にする)。範囲のうち、BIZ UD と
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
    (0x2212, 0x2212),  # − (BIZ UD は半角で、+ = より横線が短い)
]
LATIN_SYMBOLS = [code for start, end in LATIN_SYMBOL_RANGES for code in range(start, end + 1)]

# 引用符とアポストロフィ。日本語の文書 (lang="ja") の中の “Hello” や It’s の前後が全角ぶん空かないように、
# いつも BIZ UDP の字にする。和文の中の “本当” も BIZ UDP の字になる (和文の後の “Hello の “ は和文と同じ組に
# 入り、フォントからは “本当” の “ と区別できない)
LATIN_QUOTES = [0x2018, 0x2019, 0x201C, 0x201D]

# ss01 で BIZ UD の縦組の ‘ ’ を選ぶときの入れ替え。BIZ UD の字の向きは一般的な和文フォント (Noto CJK JP) と 180 度
# 逆で、“ ” ともそろわない。hwid の縦組の字はもともと正しい向きなので変えない
VERTICAL_SWAPPED_QUOTES = {0x2018: 0x2019, 0x2019: 0x2018}

# 縦組の引用符は、JLReq の縦組の括弧類であるミニュートの形で全角の枠に組む。文字は変えず vert・vrt2 の出力だけを
# 変える。‘ ’ に当たるシングルミニュートは Unicode に無いので、〝 〟 の 1 画で作る。キーは文字、値は形の元の字
GENERATED_VERTICAL_QUOTES = [f"uni{code:04X}.{kind}" for code in VERTICAL_SWAPPED_QUOTES for kind in ("minute", "sideways")]
VERTICAL_MINUTES = {0x201C: 0x301D, 0x201D: 0x301F, 0x2018: 0x301D, 0x2019: 0x301F}

# どの用字系・言語でも BIZ UDP の字にする記号。引用符とアポストロフィのほかに、
# — (BIZ UD は半角で、—— が 1 em にしかならない)・− (+ = と字幅と線の長さをそろえる)・分数 ¼ ½ ¾ ⅓ ⅔ ⅕・
# ° (BIZ UD は全角で、35°C の後ろが空く)・‼ ⁇ ⁈ ⁉ (BIZ UD は 2 つの記号を半角に詰めた形)。
# ほかの記号 (– ‐ …  など) は、日本語の文書では BIZ UD のまま
ALWAYS_UDP = [*LATIN_QUOTES, 0x2014, 0x2212, 0x00BC, 0x00BD, 0x00BE, 0x2153, 0x2154, 0x2155,
              0x00B0, 0x203C, 0x2047, 0x2048, 0x2049]

# ヒンティングを付けない字 (build.py・hinting.py)。細い横線だけの字で、BIZ UD・BIZ UDP の
# ヒンティングは、ある大きさで線の高さを 0 に丸めて消してしまう (FreeType では何も描かれず、
# Windows ではごく薄い線になる。元のフォントそのものでも同じ)。ハイフン・下線 (hwid の半角の字も)・
# ソフトハイフン・マクロン・結合用のマクロン・エンダッシュ・エムダッシュ・ホリゾンタルバー (つないで
# 作る ⸺・⸻ も)・上線・マイナス。命令を外して描く。check.py が、ヒンティングで消える字がほかに無い
# ことを確かめる
UNHINTED = [0x002D, 0x005F, 0x00AD, 0x00AF, 0x0304, 0x2013, 0x2014, 0x2015, 0x203E, 0x2212]

# 欧字から置き換える GSUB の機能。BIZ UDP は、ここで欧字を自分の幅のグリフにつなぐ
# (vrt2 は縦組で横に倒した欧字、zero は斜線の 0、frac・numr は分数の斜線、sups は上付き)。
# fwid (全角の欧字) は BIZ UD のままにする (BIZ UDP の fwid には欧字が無く、BIZ UDP の全角の欧字は
# プロポーショナル)。hwid (全角の英数字を半角に) も、BIZ UD の半角の字を別に残してつなぐ (build.py)
LATIN_FEATURES = ["frac", "numr", "sups", "zero", "vrt2"]

# 分数と上付き・下付きの機能。fraction_digits.py が、欧字を BIZ UDP の字にした後に作り直す (分子・分母の数字と
# 0〜9 の上付きの数字を足す。BIZ UD・BIZ UDP の frac は 1 2 3 を上付きにするだけで、分母が無い)
FRACTION_FEATURES = ["frac", "numr", "dnom", "sups", "subs", "sinf"]

# 欧字から始まる合字 (GSUB の ligature) を置き換える機能。BIZ UDP は、ccmp と liga で、f i を ﬁ に、
# æ ə ɑ などと結合用のアクセントを 1 つの字につなぐ (BIZ UD は f i をつながず、アクセントの付いた
# 字は BIZ UD の幅の字につなぐ)。dlig (!? など) は、欧文の中では locl で BIZ UDP の字になるので
# 触らない
LATIN_LIGATURE_FEATURES = ["ccmp", "liga"]

# vpal を付ける縦組の字の、BIZ UDP とのインクの幅と高さの差の上限 (spacing.py・check.py)
VERTICAL_SAME_INK = 100

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
