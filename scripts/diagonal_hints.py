"""斜線の濃さを保つヒンティング。BIZ UDP から持ってきた字の命令に、斜線の点を動かす命令を足す。build.py が使う。

BIZ UDP の命令は、横線 (ベースライン・x-height・字の上端と下端) を画素にそろえるために、いくつかの点を
動かし、残りの点は最後の IUP が補間する。斜線の両側の縁は、別々の点を基準に補間されるので、同じ高さでも
動く量が違い、斜線の縦の幅が縮む (「2」の斜線は 9ppem で 7 割ほど細くなる)。

ここでは、最後の IUP の前に、斜線の両側の縁の点を、同じ 2 点 (lo・hi) の間の IP で置く。IP は元の
座標の比で位置を決めるので、両側の縁は同じ高さなら同じ量だけ動き、縦の幅は保たれる。lo・hi は、元の
命令が動かす点 (横線の高さにそろえる点) なので、横線のそろえは元のままで、IP の対象の点は元の命令が
動かした点を含まない。

追加する命令 (SVTCA[0] で y 方向にしてから):
    SVTCA[0]; SRP1 lo; SRP2 hi; SLOOP n; IP (n 個の点)
"""

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.ttProgram import Program

# (グリフ名) → (lo, hi, 斜線の縁の点)。書体 ((family, weight)) ごと。点の番号は BIZ UDP の輪郭のもの
# lo・hi は元の命令が動かす点で、lo が下 (元の y が小さい)、hi が上
PLANS: dict[tuple[str, str], dict[str, tuple[int, int, list[int]]]] = {
    ("Mincho", "Regular"): {
        "two": (45, 14, [1, 2, 3, 4, 5, 6, 7, 8, 9, 38, 39, 40, 41, 42, 43, 44]),
        "Oslash": (8, 0, [2, 10, 11, 13, 23, 24, 25, 33, 41]),
        "oslash": (8, 0, [2, 10, 11, 13, 21, 22, 23, 31, 39]),
    },
    ("Mincho", "Bold"): {
        "two": (46, 12, [1, 2, 3, 4, 5, 6, 7, 38, 39, 40, 41, 42, 43, 44, 45]),
        "Oslash": (9, 0, [2, 11, 12, 14, 24, 25, 36, 37, 47]),
        "oslash": (9, 0, [12, 13, 15, 26, 35, 36, 46]),
    },
    ("Gothic", "Regular"): {
        "two": (29, 12, [2, 3, 4, 5, 6, 7, 22, 23, 24, 25, 26, 27, 28]),
        "Oslash": (8, 0, [2, 10, 11, 12, 13, 21, 22, 23, 31, 39]),
        "oslash": (8, 0, [2, 10, 11, 23, 24, 25, 33, 41]),
    },
    ("Gothic", "Bold"): {
        "two": (34, 12, [2, 3, 4, 5, 6, 7, 27, 28, 29, 30, 31, 32, 33]),
        "Oslash": (8, 0, [2, 10, 11, 12, 13, 21, 22, 23, 31, 39]),
        "oslash": (8, 0, [2, 23, 24, 25, 33, 41]),
    },
}


def _lines(program: Program) -> list[str]:
    return [line.split("/*")[0].strip() for line in program.getAssembly() if line.split("/*")[0].strip()]


def rewrite(program: Program, lo: int, hi: int, points: list[int]) -> Program:
    """program の最後の IUP[0] IUP[1] の前に、点 points を lo・hi の間に IP で置く命令を足したもの"""
    lines = _lines(program)
    if lines[-2:] != ["IUP[0]", "IUP[1]"]:
        raise SystemExit("the glyph program does not end with IUP[0] IUP[1]")
    head, assembly, pending = lines[:-2], [], []
    for line in head:
        if line.lstrip("-").isdigit():
            pending.append(line)
        else:
            if pending:
                assembly.append("PUSH[ ]")
                assembly.extend(pending)
                pending = []
            assembly.append(line if "PUSH" not in line else "PUSH[ ]")
    if pending:
        raise SystemExit("the glyph program ends with pushed values")
    assembly += ["PUSH[ ]", *map(str, [*points, len(points), hi, lo]), "SVTCA[0]", "SRP1[ ]", "SRP2[ ]", "SLOOP[ ]", "IP[ ]",
                 "IUP[0]", "IUP[1]"]
    result = Program()
    result.fromAssembly(assembly)
    return result


def add(font: TTFont, family: str, weight: str) -> dict[str, int]:
    """PLANS の字の命令を書き直す。maxp の命令の長さの上限を、足りなければ上げる。書き直した字と命令の長さを返す"""
    sizes = {}
    for name, (lo, hi, points) in PLANS.get((family, weight), {}).items():
        glyph = font["glyf"][name]
        count = len(glyph.getCoordinates(font["glyf"])[0])
        if not (0 <= lo < count and 0 <= hi < count and all(0 <= p < count for p in points)) or len(set(points)) != len(points):
            raise SystemExit(f"{name}: a point of the diagonal plan does not exist")
        glyph.program = rewrite(glyph.program, lo, hi, points)
        sizes[name] = len(glyph.program.getBytecode())
    if sizes:
        font["maxp"].maxSizeOfInstructions = max(font["maxp"].maxSizeOfInstructions, *sizes.values())
    return sizes
