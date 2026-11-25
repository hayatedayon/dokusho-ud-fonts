"""斜線の濃さを保つヒンティング。元の BIZ UD・BIZ UDP の命令に、斜線の縁の点を動かす決まった形の末尾を足す。build.py が使う。

元の命令は、横線 (ベースライン・x-height・字の上端と下端) を画素にそろえるために、いくつかの点を動かし、
残りの点は最後の IUP が補間する。斜線の両側の縁は、別々の点を基準に補間されるので、同じ高さでも動く量が
違い、斜線の縦の幅が縮む (明朝 Regular の「2」の斜線は 9ppem で 7 割ほど細くなる)。

そこで、最後の IUP の前に、斜線の縁の点を、元の命令が動かした 2 点 (lo・hi) の間の IP で置く。IP は元の座標の
比で位置を決めるので、両側の縁は同じ高さなら同じ量だけ動き、縦の幅は保たれる。lo・hi は元の命令が動かす点
(横線の高さにそろえる点) で、IP の対象は元の命令が動かさない点だけなので、横線のそろえは元のまま。

足す末尾 (最後の IUP[0] と、あれば IUP[1] の前または後。グループの数だけ繰り返す):

    SVTCA[0]
    PUSH 点 1 … 点 n, n, hi, lo;  SRP1;  SRP2;  SLOOP;  IP

同じ参照点の動きを写す SHP の場合:

    SVTCA[0]
    PUSH 点 1 … 点 n, n, 参照点;  SRP1;  SLOOP;  SHP[1]

末尾はこの形に限る。scripts/checks/hinting.py の check_diagonal_hints が、この形・元の命令との一致・横線のそろい・
x が動かないこと・斜線の濃さを字ごとに確かめる。どの字に足すかは spec.DIAGONAL_GLYPHS に、点は diagonal_plans.json
に持つ (scripts/diagonal_plans.json は、元の命令の SHA-1 を添えて、元が変わったら止める)。
"""

import hashlib
import json
import re
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.ttProgram import Program

import spec

PLANS_PATH = Path(__file__).with_name("diagonal_plans.json")

_PUSH = re.compile(r"N?PUSH[BW]?\[")
_NUMBER = re.compile(r"-?\d+")


def tokens(program: Program) -> list:
    """命令を、積んだ値 (int) と命令の名前 (str。PUSH 系は除く。IUP[0] のように引数を含む) の並びにする。
    PUSHB と NPUSHB など、積み方の違いは無視して、同じ命令なら同じ並びになる"""
    out: list = []
    for line in program.getAssembly():
        text = line.split("/*")[0].strip()
        if not text or _PUSH.match(text):
            continue
        out.append(int(text) if _NUMBER.fullmatch(text) else text)
    return out


def assemble(items: list) -> Program:
    """tokens の並びから命令を作る。続く値は 1 つの PUSH にまとめる"""
    assembly: list[str] = []
    pending: list[int] = []
    for item in [*items, None]:
        if isinstance(item, int):
            pending.append(item)
            continue
        if pending:
            assembly.append("PUSH[ ]")
            assembly.extend(str(v) for v in pending)
            pending = []
        if item is not None:
            assembly.append(item)
    program = Program()
    program.fromAssembly(assembly)
    return program


def tail(groups: list, method: str = "ip") -> list:
    """IP の (lo, hi, 点の並び) または SHP の (参照点, 点の並び) から、足す末尾の tokens"""
    items: list = ["SVTCA[0]"]
    if method == "ip":
        for lo, hi, points in groups:
            items += [*points, len(points), hi, lo, "SRP1[ ]", "SRP2[ ]", "SLOOP[ ]", "IP[ ]"]
    elif method == "shp":
        for reference, points in groups:
            items += [*points, len(points), reference, "SRP1[ ]", "SLOOP[ ]", "SHP[1]"]
    else:
        raise ValueError(f"unknown diagonal tail method: {method}")
    return items


def group_points(groups: list) -> list[int]:
    return [point for group in groups for point in group[-1]]


def reference_points(groups: list) -> list[int]:
    return [point for group in groups for point in group[:-1]]


def ending(items: list) -> list:
    """tokens の最後の IUP ([IUP[0], IUP[1]] か [IUP[0]])。無ければ止まる"""
    if items[-2:] == ["IUP[0]", "IUP[1]"]:
        return items[-2:]
    if items[-1:] == ["IUP[0]"]:
        return items[-1:]
    raise SystemExit("the glyph program does not end with IUP[0]")


def rewrite(program: Program, groups: list, after: bool = False, method: str = "ip") -> Program:
    """program に groups の末尾を足したもの。after が偽なら最後の IUP の前に、真なら最後の IUP の後ろ (全ての点が
    補間された後) に足す。後ろに足すと、IP で動かす点以外は元の命令の結果のまま動かない"""
    items = tokens(program)
    last = ending(items)
    if after:
        return assemble([*items, *tail(groups, method)])
    return assemble([*items[: len(items) - len(last)], *tail(groups, method), *last])


def _read_groups(body: list):
    """body の最後から、同じ種類のグループの並びと、その前の SVTCA[0] を読む。
    (グループの並び, それより前の tokens, 命令の種類)。決まった形でなければ None"""
    groups: list = []
    method = "shp" if body[-3:] == ["SRP1[ ]", "SLOOP[ ]", "SHP[1]"] else "ip"
    operations = ["SRP1[ ]", "SLOOP[ ]", "SHP[1]"] if method == "shp" else [
        "SRP1[ ]", "SRP2[ ]", "SLOOP[ ]", "IP[ ]"
    ]
    nops = len(operations)
    nrefs = 1 if method == "shp" else 2
    header = nops + nrefs + 1
    while body[-nops:] == operations:
        values = body[-header:-nops]
        if len(values) != nrefs + 1 or not all(isinstance(v, int) for v in values):
            return None
        count, *refs = values
        points = body[-header - count:-header]
        if count < 1 or len(points) != count or not all(isinstance(v, int) for v in points):
            return None
        groups.insert(0, [*reversed(refs), points])
        body = body[:-header - count]
    if not groups or body[-1:] != ["SVTCA[0]"]:
        return None
    return groups, body[:-1], method


def split_tail(items: list):
    """tokens を (元の命令の tokens, グループの並び, 後ろに足したか, 命令の種類) に分ける。末尾が決まった形でなければ None
    (グループが無い元のままの命令も None)"""
    read = _read_groups(items)
    if read is not None:
        groups, rest, method = read
        try:
            ending(rest)
        except SystemExit:
            return None
        return rest, groups, True, method
    try:
        last = ending(items)
    except SystemExit:
        return None
    read = _read_groups(items[: len(items) - len(last)])
    if read is None:
        return None
    groups, rest, method = read
    return [*rest, *last], groups, False, method


def digest(program: Program) -> str:
    """元の命令の識別 (命令の SHA-1 の先頭 12 桁。積み方の違いに依らない)"""
    return hashlib.sha1(json.dumps(tokens(program)).encode()).hexdigest()[:12]


def load_plans() -> dict:
    return json.loads(PLANS_PATH.read_text(encoding="utf-8"))


def add(font: TTFont, family: str, weight: str) -> dict[str, int]:
    """diagonal_plans.json の字の命令に末尾を足す。maxp の命令の長さと積む値の数の上限を、足りなければ上げる。
    足した字と命令の長さを返す。書体ごとの字の一覧 (spec.DIAGONAL_GLYPHS) と、元の命令の SHA-1 が合わなければ止まる"""
    plans = load_plans().get(f"{family}-{weight}", {})
    if set(plans) != set(spec.DIAGONAL_GLYPHS.get((family, weight), {})):
        raise SystemExit(f"{family} {weight}: diagonal_plans.json and spec.DIAGONAL_GLYPHS list different glyphs")
    glyf = font["glyf"]
    order = font.getGlyphOrder()
    sizes, stack = {}, 0
    for key, plan in plans.items():
        # 作ったフォントを開き直したときのグリフ名 (post が形式 3 なので番号から付く。作っている途中の名前とは違う) を
        # key に、作っている途中の名前を番号から引く
        name = order[plan["index"]]
        glyph = glyf[name]
        glyph.expand(glyf)
        count = len(glyph.getCoordinates(glyf)[0])
        if glyph.isComposite() or digest(glyph.program) != plan["program"]:
            raise SystemExit(f"{key} ({name}): the original program is not the one the diagonal plan was made for")
        groups = plan["groups"]
        used = reference_points(groups) + group_points(groups)
        if not groups or not all(0 <= p < count for p in used):
            raise SystemExit(f"{key} ({name}): a point of the diagonal plan does not exist")
        glyph.program = rewrite(glyph.program, groups, after=plan.get("after", False),
                                method=plan.get("method", "ip"))
        sizes[key] = len(glyph.program.getBytecode())
        stack = max(stack, max(len(group[-1]) + len(group) for group in groups))
    if sizes:
        maxp = font["maxp"]
        maxp.maxSizeOfInstructions = max(maxp.maxSizeOfInstructions, *sizes.values())
        # 末尾が積む値の数。元の命令の積む値と重なる (SVTCA の前までに積んだ値は、IP が使い切る) とは限らないので足す
        maxp.maxStackElements = max(maxp.maxStackElements, stack + 64)
    return sizes
