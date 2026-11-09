"""欧字の頻出ペアを控えめに詰める。輪郭・字幅そのものと、和文のベタ組は変えない。

値は em の千分率。斜線・張り出しのある欧字と、ピリオド・コンマの組を対象にする。
アクセント付きの字は Unicode の正規分解で同じクラスに入れるが、右に張り出すキャロンは除く。全角・hwid・tnum・
上付き・下付き・縦組の置き換え先は入れない。縦組中の横倒し欧字を横組として組む場合は対象になる。
GPOS の kern は spacing.add が組み込む。
"""

import unicodedata

import spec

# (左の文字群, 右の文字群, 明朝, ゴシック)。控えめな初期値で、書体別の見本で調整できる。
PAIRS = [
    ("A", "V", -45, -35), ("A", "W", -30, -25), ("A", "Y", -45, -40),
    ("A", "T", -25, -20), ("V", "A", -45, -35), ("W", "A", -30, -25),
    ("Y", "A", -45, -40), ("T", "A", -25, -20),
    # T の u だけを調整できるよう、V/W/Y も右側のクラスを同じ境界で分ける。
    # aeou を混在させると、重なるクラスが別サブテーブルに分かれ、先のゼロ値に遮られる。
    ("T", "aeo", -45, -35), ("T", "u", -20, -35),
    ("V", "aeo", -25, -20), ("V", "u", -25, -20),
    ("W", "aeo", -20, -15), ("W", "u", -20, -15),
    ("Y", "aeo", -40, -30), ("Y", "u", -40, -30),
    ("L", "TVWY", -30, -25), ("F", "ao", -20, -15),
    # 句読点の前は下側の余白だけを控えめに減らす。右クラスは同じ . , の組にし、
    # 欧字ペアとは別 lookup に入れる (先行サブテーブルのゼロ値による遮蔽を防ぐ)。
    ("T", ".,", -70, -55), ("V", ".,", -65, -50),
    ("W", ".,", -50, -40), ("Y", ".,", -75, -60),
    ("P", ".,", -90, -65), ("F", ".,", -65, -50),
    ("r", ".,", -35, -25), ("y", ".,", -35, -25),
    ("v", ".,", -40, -30), ("w", ".,", -30, -20),
]

# Ť・Ľ のキャロンは上ではなく右に張り出す。基底の T・L と同じ左側クラスには入れない。
EXCLUDED_LEFT = "ŤĽ"

def adjustment(em: int, family: str, mincho: int, gothic: int) -> int:
    """宣言した em 千分率をフォント単位にする。生成と実シェーピング検査で共有する。"""
    return round(em * (mincho if family == "Mincho" else gothic) / 1000)


def feature(font, family: str) -> str:
    cmap = font.getBestCmap()
    groups: dict[str, set[str]] = {}
    for code in spec.LATIN:
        if code in cmap and unicodedata.category(chr(code)).startswith("L"):
            base = unicodedata.normalize("NFD", chr(code))[0]
            if base.isascii() and base.isalpha():
                groups.setdefault(base, set()).add(cmap[code])
    # ASCII の比例幅句読点だけ。全角・hwid・縦組の候補や locl 出力を取り込まない。
    for char in ".,":
        groups[char] = {cmap[ord(char)]}
    lines = ["feature kern {"]
    em = font["head"].unitsPerEm
    excluded = {cmap[ord(c)] for c in EXCLUDED_LEFT if ord(c) in cmap}
    for lookup, punctuation in (("LatinKern", False), ("LatinPunctuationKern", True)):
        lines += [f"  lookup {lookup} {{", "    lookupflag IgnoreMarks;"]
        for left, right, mincho, gothic in PAIRS:
            if (set(right) <= set(".,")) != punctuation:
                continue
            a = sorted({g for c in left for g in groups.get(c, ())} - excluded)
            b = sorted({g for c in right for g in groups.get(c, ())})
            amount = adjustment(em, family, mincho, gothic)
            if a and b:
                lines.append(f"    pos [{' '.join(a)}] [{' '.join(b)}] {amount};")
        lines.append(f"  }} {lookup};")
    lines.append("} kern;")
    return "\n".join(lines)
