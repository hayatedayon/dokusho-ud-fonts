"""読書 UD明朝・読書 UDゴシックの決まり。build.py と check.py が使う。"""

# フォントの版 (head.fontRevision と name の Version)。リリースのタグ vX.Y.Z は X.YYZ に対応する
# (v1.0.0 は 1.000、v1.2.3 は 1.023)。.github/workflows/release.yml が突き合わせる
# 次の版を公開するまでは、公開済みの版を保つ。未公開の変更は FONTLOG に記録する。
VERSION = "1.013"

# ⦅ ⦆ は全角の二重括弧 ｟ ｠ と同じグリフを使う。
WHITE_PARENTHESIS_ALIASES = {0x2985: 0xFF5F, 0x2986: 0xFF60}

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

# 斜線を書き直した字 (書体 → グリフ名 → 文字、別形は元の字)。ヒンティングで斜線が薄くなる字 (斜線の縁が別々の点から
# 補間されて縦の幅が縮む) の命令に、決まった形の末尾 (diagonal_hints.py。点は diagonal_plans.json) を足す。元の BIZ UD・
# BIZ UDP の命令のままの字とは画素が違うので、checks/hinting.py は、この字だけ BIZ UD・BIZ UDP との画素の比較から外し、
# 代わりに、命令が「元の命令 + 決まった末尾」であること、元の命令だけの画素が BIZ UD・BIZ UDP と同じこと、x に動く点が無い
# こと、横線がそろう組の数が元と同じこと、斜線の縦の幅が元より縮まないことで縛る。漢字・仮名は、拡大画像で見て悪くない
# ので書き直さない
DIAGONAL_GLYPHS: dict[tuple[str, str], dict[str, str]] = {
    ("Mincho", "Regular"): {
        ".notdef": "未定義の字",
        "A": "U+0041 A",
        "Aacute": "U+00C1 Á",
        "Abreve": "U+0102 Ă",
        "Acircumflex": "U+00C2 Â",
        "Adieresis": "U+00C4 Ä",
        "Agrave": "U+00C0 À",
        "Alpha": "U+0391 Α",
        "Amacron": "U+0100 Ā",
        "Aogonek": "U+0104 Ą",
        "Atilde": "U+00C3 Ã",
        "Oslash": "U+00D8 Ø",
        "S": "U+0053 S",
        "Sacute": "U+015A Ś",
        "Scaron": "U+0160 Š",
        "Scedilla": "U+015E Ş",
        "Scircumflex": "U+015C Ŝ",
        "V": "U+0056 V",
        "Z": "U+005A Z",
        "Zacute": "U+0179 Ź",
        "Zcaron": "U+017D Ž",
        "Zdotaccent": "U+017B Ż",
        "Zeta": "U+0396 Ζ",
        "aleph": "U+2135 ℵ",
        "delta": "U+03B4 δ",
        "eight": "U+0038 8",
        "emptyset": "U+2205 ∅",
        "female": "U+2640 ♀",
        "four": "U+0034 4",
        "glyph01311": "別形",
        "glyph01317": "別形",
        "glyph01393": "別形",
        "glyph01849": "別形",
        "glyph11971": "別形 U+003E U+00BB U+2267",
        "glyph12879": "別形 U+0030",
        "glyph13235": "別形 U+0030 U+00D8 U+3007",
        "glyph13284": "別形",
        "glyph13287": "別形",
        "glyph13302": "別形 U+00C6",
        "glyph13339": "別形 U+00D1",
        "glyph13420": "別形 U+0045 U+FF25",
        "glyph13433": "別形 U+0052 U+FF32",
        "glyph13439": "別形 U+0058 U+FF38",
        "glyph13443": "別形 U+00A5",
        "glyph13473": "別形 U+007B U+FF5B",
        "glyph13486": "別形",
        "glyph13599": "別形 U+0036",
        "glyph13622": "別形 U+004D",
        "glyph13623": "別形 U+004E",
        "glyph13705": "別形",
        "glyph13711": "別形",
        "glyph13951": "別形 U+0053 U+FF33",
        "glyph13958": "別形 U+005A U+FF3A",
        "glyph13977": "別形 U+0038 U+FF18",
        "glyph13981": "別形 U+0034 U+FF14",
        "glyph14015": "別形 U+0032 U+FF12",
        "glyph14143": "別形 U+2113",
        "glyph14166": "別形 U+00A2",
        "glyph14174": "別形 U+00AB",
        "glyph14492": "別形 U+00A2",
        "glyph14533": "別形 U+2113",
        "glyph14550": "別形 U+00AB",
        "gradient": "U+2207 ∇",
        "igrave": "U+00EC ì",
        "logicaland": "U+2227 ∧",
        "notsubset": "U+2284 ⊄",
        "nu": "U+03BD ν",
        "oslash": "U+00F8 ø",
        "two": "U+0032 2",
        "uni0163": "U+0163 ţ",
        "uni01CD": "U+01CD Ǎ",
        "uni0255": "U+0255 ɕ",
        "uni0394": "U+0394 Δ",
        "uni0410": "U+0410 А",
        "uni212B": "U+212B Å",
        "uni2174": "U+2174 ⅴ",
        "uni21E9": "U+21E9 ⇩",
        "uni2276": "U+2276 ≶",
        "uni2277": "U+2277 ≷",
        "uni23C2": "U+23C2 ⏂",
        "uni248F": "U+248F ⒏",
        "uni25B3": "U+25B3 △",
        "uni2606": "U+2606 ☆",
        "uni2616": "U+2616 ☖",
        "uni2661": "U+2661 ♡",
        "uni3006": "U+3006 〆",
        "uniFF56": "U+FF56 ｖ",
        "universal": "U+2200 ∀",
        "z": "U+007A z",
        "zacute": "U+017A ź",
        "zdotaccent": "U+017C ż",
    },
    ("Mincho", "Bold"): {
        ".notdef": "未定義の字",
        "J": "U+004A J",
        "Oslash": "U+00D8 Ø",
        "Zacute": "U+0179 Ź",
        "Zdotaccent": "U+017B Ż",
        "alpha": "U+03B1 α",
        "emptyset": "U+2205 ∅",
        "four": "U+0034 4",
        "glyph01393": "別形",
        "glyph01731": "別形",
        "glyph01745": "別形",
        "glyph12031": "別形 U+0028 U+2985 U+FF08",
        "glyph12304": "別形 U+025A",
        "glyph12305": "別形 U+025A",
        "glyph12879": "別形 U+0030",
        "glyph12916": "別形 U+201C U+301D",
        "glyph13235": "別形 U+0030 U+00D8 U+3007",
        "glyph13422": "別形 U+0047 U+FF27",
        "glyph13486": "別形",
        "glyph13633": "別形 U+0058",
        "gradient": "U+2207 ∇",
        "logicaland": "U+2227 ∧",
        "nacute": "U+0144 ń",
        "notsubset": "U+2284 ⊄",
        "nu": "U+03BD ν",
        "oslash": "U+00F8 ø",
        "three": "U+0033 3",
        "two": "U+0032 2",
        "ugrave": "U+00F9 ù",
        "uni01F9": "U+01F9 ǹ",
        "uni0394": "U+0394 Δ",
        "uni03BC": "U+03BC μ",
        "uni1F70": "U+1F70 ὰ",
        "uni2048": "U+2048 ⁈",
        "uni2113": "U+2113 ℓ",
        "uni21E9": "U+21E9 ⇩",
        "uni23C0": "U+23C0 ⏀",
        "uni23C1": "U+23C1 ⏁",
        "uni23C2": "U+23C2 ⏂",
        "uni248A": "U+248A ⒊",
        "uni25B3": "U+25B3 △",
        "uni2616": "U+2616 ☖",
        "uni2661": "U+2661 ♡",
        "uni3034": "U+3034 〴",
        "universal": "U+2200 ∀",
    },
    ("Gothic", "Regular"): {
        ".notdef": "未定義の字",
        "A": "U+0041 A",
        "Alpha": "U+0391 Α",
        "M": "U+004D M",
        "Mu": "U+039C Μ",
        "N": "U+004E N",
        "Nu": "U+039D Ν",
        "Oslash": "U+00D8 Ø",
        "S": "U+0053 S",
        "V": "U+0056 V",
        "Z": "U+005A Z",
        "Zdotaccent": "U+017B Ż",
        "Zeta": "U+0396 Ζ",
        "ampersand": "U+0026 &",
        "cedilla": "U+00B8 ¸",
        "delta": "U+03B4 δ",
        "eight": "U+0038 8",
        "female": "U+2640 ♀",
        "four": "U+0034 4",
        "glyph01278": "別形",
        "glyph01291": "別形",
        "glyph01306": "別形",
        "glyph01309": "別形",
        "glyph01356": "別形",
        "glyph01358": "別形",
        "glyph01393": "別形",
        "glyph01841": "別形",
        "glyph01849": "別形",
        "glyph13194": "別形 U+007D U+23AC U+FF5D",
        "glyph13284": "別形",
        "glyph13401": "別形 U+0032 U+FF12",
        "glyph13443": "別形 U+00A5",
        "glyph13472": "別形 U+007A U+FF5A",
        "glyph13627": "別形 U+0052",
        "glyph13684": "別形",
        "glyph13690": "別形",
        "glyph13702": "別形",
        "glyph13703": "別形",
        "glyph13739": "別形",
        "glyph13741": "別形",
        "glyph13767": "別形",
        "glyph13790": "別形",
        "glyph13946": "別形 U+004E U+FF2E",
        "glyph13961": "別形 U+0026 U+FF06",
        "glyph13977": "別形 U+0038 U+FF18",
        "glyph13981": "別形 U+0034 U+FF14",
        "glyph14015": "別形 U+0032 U+FF12",
        "glyph14023": "別形 U+007A U+FF5A",
        "glyph14094": "別形 U+00A2",
        "glyph14143": "別形 U+2113",
        "glyph14166": "別形 U+00A2",
        "glyph14474": "別形 U+00B8",
        "glyph14475": "別形 U+00A2",
        "glyph14492": "別形 U+00A2",
        "glyph14534": "別形 U+2113",
        "gradient": "U+2207 ∇",
        "logicaland": "U+2227 ∧",
        "musicalnotedbl": "U+266B ♫",
        "notelement": "U+2209 ∉",
        "notsubset": "U+2284 ⊄",
        "nu": "U+03BD ν",
        "oslash": "U+00F8 ø",
        "s": "U+0073 s",
        "uni0255": "U+0255 ɕ",
        "uni028C": "U+028C ʌ",
        "uni0394": "U+0394 Δ",
        "uni0410": "U+0410 А",
        "uni0418": "U+0418 И",
        "uni041C": "U+041C М",
        "uni0438": "U+0438 и",
        "uni043C": "U+043C м",
        "uni2116": "U+2116 №",
        "uni2276": "U+2276 ≶",
        "uni2277": "U+2277 ≷",
        "uni23C2": "U+23C2 ⏂",
        "uni248B": "U+248B ⒋",
        "uni25B3": "U+25B3 △",
        "uni2616": "U+2616 ☖",
        "uni2661": "U+2661 ♡",
        "uniFF13": "U+FF13 ３",
        "uniFF2D": "U+FF2D Ｍ",
        "uniFF2E": "U+FF2E Ｎ",
        "uniFF4B": "U+FF4B ｋ",
        "uniFF57": "U+FF57 ｗ",
        "uniFF5A": "U+FF5A ｚ",
        "v": "U+0076 v",
        "w": "U+0077 w",
        "x": "U+0078 x",
        "z": "U+007A z",
        "zdotaccent": "U+017C ż",
    },
    ("Gothic", "Bold"): {
        ".notdef": "未定義の字",
        "Oslash": "U+00D8 Ø",
        "ampersand": "U+0026 &",
        "eight": "U+0038 8",
        "glyph12916": "別形 U+201C U+301D",
        "glyph13305": "縦組で横に倒した U+00D8 Ø",
        "glyph13433": "別形 U+0052 U+FF32",
        "glyph13457": "別形 U+006B U+FF4B",
        "glyph13485": "別形",
        "glyph13627": "別形 U+0052",
        "glyph13961": "別形 U+0026 U+FF06",
        "glyph14094": "別形 U+00A2",
        "glyph14475": "別形 U+00A2",
        "musicalnotedbl": "U+266B ♫",
        "nu": "U+03BD ν",
        "oslash": "U+00F8 ø",
        "tcaron": "U+0165 ť",
        "uni0418": "U+0418 И",
        "uni0438": "U+0438 и",
        "uni23C2": "U+23C2 ⏂",
        "uni25B3": "U+25B3 △",
        "uni2616": "U+2616 ☖",
        "uni2661": "U+2661 ♡",
    },
}

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
