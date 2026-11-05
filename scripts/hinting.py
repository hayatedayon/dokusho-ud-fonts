"""BIZ UDP から持ってきた字に、BIZ UDP のヒンティングを付ける。build.py が使う。

TrueType のヒンティングの命令は、フォントに 1 つの cvt (調整に使う値の表) の何番目かを指して
働く。読書 UD は BIZ UD を元にするので、cvt は BIZ UD のもの。BIZ UDP の字の命令をそのまま
入れると、BIZ UD の cvt の違う値を指してしまう。そこで

1. BIZ UDP の cvt を、BIZ UD の cvt の後ろに付け足す (offset = BIZ UD の cvt の数)
2. BIZ UDP の prep (大きさごとに cvt を計算し直す命令) を、cvt の番号を offset ずらして、
   BIZ UD の prep の後ろに付け足す
3. BIZ UDP から持ってきた字に BIZ UDP の命令を入れ、cvt の番号を offset ずらす

これが成り立つのは、次のことを確かめられるとき。どれか 1 つでも成り立たなければ止まる。

- fpgm (共通の関数) が BIZ UD と BIZ UDP で同じ
- 字の命令と prep が、cvt の番号を、自分の中で積んだ数字として渡す (関数の中で決め打ちした
  番号や、計算した番号ではない)。そうでなければ、ずらせない
- cvt の番号として積んだ数字を、点の番号などほかの用途に使わない。使うと、ずらしたときに
  そちらが壊れる
- 字の命令が cvt に書き込まない

番号として渡る数字は、命令を、積まれた値の動きだけ追ってなぞって見つける (Tracer)。数字は
分かる限り計算し、分からない値で分かれる IF は両方をなぞる。check.py が、FreeType で描いた
欧字の画素が BIZ UDP と同じことを確かめる。
"""

import re
from array import array

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.ttProgram import Program


class Pushed(int):
    """命令の中で積んだ数字。src は (命令の番号, 値の番号)"""

    def __new__(cls, value: int, src: tuple[int, int]):
        obj = int.__new__(cls, value)
        obj.src = src
        return obj


UNKNOWN = object()  # 値が分からない (点の座標・大きさなどから決まる)

# 命令ごとに、(取る値の用途を、取る順に並べたもの, 積む値の数)。用途は点の番号 (_POINT) かそれ以外 (_OTHER)
_POINT = "point"
_OTHER = "other"
_OPS: dict[str, tuple[list[str], int]] = {
    # 値を取らないもの
    **{op: ([], 0) for op in ("SVTCA", "SPVTCA", "SFVTCA", "SFVTPV", "RTHG", "RTG", "RTDG", "RDTG", "RUTG",
                              "ROFF", "FLIPON", "FLIPOFF", "IUP", "SMOOTH")},
    # 点を取るもの
    "SRP0": ([_POINT], 0), "SRP1": ([_POINT], 0), "SRP2": ([_POINT], 0), "MDAP": ([_POINT], 0),
    "MDRP": ([_POINT], 0), "UTP": ([_POINT], 0), "GC": ([_POINT], 1), "SCFS": ([_OTHER, _POINT], 0),
    "MD": ([_POINT, _POINT], 1), "MSIRP": ([_OTHER, _POINT], 0), "ALIGNPTS": ([_POINT, _POINT], 0),
    "ISECT": ([_POINT] * 5, 0), "SPVTL": ([_POINT, _POINT], 0), "SFVTL": ([_POINT, _POINT], 0),
    "SDPVTL": ([_POINT, _POINT], 0), "SHC": ([_OTHER], 0), "SHZ": ([_OTHER], 0), "FLIPRGON": ([_POINT, _POINT], 0),
    "FLIPRGOFF": ([_POINT, _POINT], 0),
    # 状態を変えるもの
    **{op: ([_OTHER], 0) for op in ("SZP0", "SZP1", "SZP2", "SZPS", "SROUND", "S45ROUND", "SMD", "SCVTCI",
                                    "SSWCI", "SSW", "SANGW", "SDB", "SDS", "SCANCTRL", "SCANTYPE")},
    "INSTCTRL": ([_OTHER, _OTHER], 0), "WS": ([_OTHER, _OTHER], 0), "SPVFS": ([_OTHER, _OTHER], 0),
    "SFVFS": ([_OTHER, _OTHER], 0),
    # 値を返すもの
    "GPV": ([], 2), "GFV": ([], 2), "MPPEM": ([], 1), "MPS": ([], 1), "RS": ([_OTHER], 1),
    "GETINFO": ([_OTHER], 1), "ODD": ([_OTHER], 1), "EVEN": ([_OTHER], 1), "ABS": ([_OTHER], 1),
    "NEG": ([_OTHER], 1), "FLOOR": ([_OTHER], 1), "CEILING": ([_OTHER], 1), "ROUND": ([_OTHER], 1),
    "NROUND": ([_OTHER], 1), "DIV": ([_OTHER, _OTHER], 1), "MUL": ([_OTHER, _OTHER], 1),
    "MAX": ([_OTHER, _OTHER], 1), "MIN": ([_OTHER, _OTHER], 1),
}
# 2 つの分かる値は計算する (IF の分かれ方を決めるため)
_ARITHMETIC = {
    "LT": lambda a, b: int(a < b), "LTEQ": lambda a, b: int(a <= b), "GT": lambda a, b: int(a > b),
    "GTEQ": lambda a, b: int(a >= b), "EQ": lambda a, b: int(a == b), "NEQ": lambda a, b: int(a != b),
    "AND": lambda a, b: int(bool(a) and bool(b)), "OR": lambda a, b: int(bool(a) or bool(b)),
    "ADD": lambda a, b: a + b, "SUB": lambda a, b: a - b,
}
# loop の回数だけ点を取るもの
_LOOPED = {"SHP", "IP", "ALIGNRP", "FLIPPT"}


class Instruction:
    def __init__(self, op: str, text: str):
        self.op, self.text, self.values = op, text, []


def disassemble(program: Program) -> list[Instruction]:
    code: list[Instruction] = []
    for line in program.getAssembly():
        text = line.split("/*")[0].strip()
        if not text:
            continue
        if re.fullmatch(r"-?\d+", text):
            code[-1].values.append(int(text))
        else:
            code.append(Instruction(text.split("[")[0], text))
    return code


def is_push(op: str) -> bool:
    return op.endswith("PUSHB") or op.endswith("PUSHW")


def functions(fpgm: Program) -> dict[int, list[Instruction]]:
    """fpgm の関数。FDEF の番号は、その前に積んだ数字"""
    code, funcs, pending, i = disassemble(fpgm), {}, [], 0
    while i < len(code):
        if is_push(code[i].op):
            pending.extend(code[i].values)
        elif code[i].op == "FDEF":
            number, body, i = pending.pop(), [], i + 1
            while code[i].op != "ENDF":
                if code[i].op == "FDEF":
                    raise SystemExit("nested FDEF in fpgm")
                body.append(code[i])
                i += 1
            funcs[number] = body
        i += 1
    return funcs


class Tracer:
    """命令を、積まれた値の動きだけ追ってなぞる。cvt の番号として使われた数字と、ほかの用途に
    使われた数字を集める"""

    def __init__(self, funcs: dict[int, list[Instruction]]):
        self.funcs = funcs
        self.cvt_operands: list = []  # 番号として使われた値 (Pushed なら、どこで積んだか分かる)
        self.cvt_writes: list = []  # cvt に書き込んだ番号
        self.other_uses: dict[tuple[int, int], str] = {}  # cvt 以外に使われた、積んだ数字 → その命令
        self.current = ""  # なぞっている命令 (止まったときの手がかり)

    def _use(self, value, role: str) -> None:
        if isinstance(value, Pushed):
            if role == "cvt":
                self.cvt_operands.append(value)
            elif role not in ("compare", "discard"):
                # 比べる・捨てるのは用途に数えない (関数は番号を写し取って比べ、要らない写しを捨てる)
                self.other_uses.setdefault(value.src, self.current)
        elif role == "cvt":
            self.cvt_operands.append(value)

    def run(self, code: list[Instruction], stack: list, loop: list | None = None) -> None:
        loop = loop if loop is not None else [1]
        i = 0
        while i < len(code):
            ins = code[i]
            op = ins.op
            self.current = ins.text

            def pop(role: str = _OTHER):
                if not stack:
                    raise SystemExit(f"stack underflow at {ins.text}")
                value = stack.pop()
                self._use(value, role)
                return value

            if is_push(op):
                stack.extend(ins.values)
            elif op == "DUP":
                stack.append(stack[-1])
            elif op == "POP":
                pop("discard")
            elif op == "CLEAR":
                stack.clear()
            elif op == "SWAP":
                stack[-1], stack[-2] = stack[-2], stack[-1]
            elif op == "DEPTH":
                stack.append(len(stack))
            elif op == "CINDEX":
                k = pop()
                stack.append(stack[-k] if isinstance(k, int) else UNKNOWN)
            elif op == "MINDEX":
                k = pop()
                if not isinstance(k, int):
                    raise SystemExit(f"MINDEX of an unknown depth at {ins.text}")
                stack.append(stack.pop(-k))
            elif op == "ROLL":
                stack[-3], stack[-2], stack[-1] = stack[-2], stack[-1], stack[-3]
            elif op in _ARITHMETIC:
                b, a = pop("compare"), pop("compare")
                known = isinstance(a, int) and isinstance(b, int)
                stack.append(_ARITHMETIC[op](int(a), int(b)) if known else UNKNOWN)
            elif op == "NOT":
                a = pop("compare")
                stack.append(int(not a) if isinstance(a, int) else UNKNOWN)
            elif op == "RCVT":
                pop("cvt")
                stack.append(UNKNOWN)
            elif op in ("WCVTP", "WCVTF"):
                pop()
                self.cvt_writes.append(stack[-1] if stack else None)
                pop("cvt")
            elif op in ("MIRP", "MIAP"):
                pop("cvt")
                pop(_POINT)
            elif op == "SLOOP":
                n = pop()
                if not isinstance(n, int):
                    raise SystemExit(f"SLOOP with an unknown count at {ins.text}")
                loop[0] = int(n)
            elif op == "SHPIX":
                pop()  # 動かす距離。点は loop の回数だけ取る
                for _ in range(loop[0]):
                    pop(_POINT)
                loop[0] = 1
            elif op in _LOOPED:
                for _ in range(loop[0]):
                    pop(_POINT)
                loop[0] = 1
            elif op.startswith(("DELTAP", "DELTAC")):
                n = pop()
                if not isinstance(n, int):
                    raise SystemExit(f"{op} with an unknown count at {ins.text}")
                for _ in range(int(n)):
                    pop("cvt" if op.startswith("DELTAC") else _POINT)
                    pop()
            elif op == "CALL":
                number = pop()
                if not isinstance(number, int) or int(number) not in self.funcs:
                    raise SystemExit(f"call to an unknown function at {ins.text}")
                self.run(self.funcs[int(number)], stack, loop)
            elif op == "LOOPCALL":
                number, count = pop(), pop()
                if not isinstance(count, int) or not isinstance(number, int):
                    raise SystemExit(f"LOOPCALL with unknown values at {ins.text}")
                for _ in range(int(count)):
                    self.run(self.funcs[int(number)], stack, loop)
            elif op == "IF":
                condition = pop("compare")
                depth, j, else_at = 0, i + 1, None
                while True:
                    if code[j].op == "IF":
                        depth += 1
                    elif code[j].op == "EIF":
                        if depth == 0:
                            break
                        depth -= 1
                    elif code[j].op == "ELSE" and depth == 0:
                        else_at = j
                    j += 1
                then_part = code[i + 1: else_at if else_at is not None else j]
                else_part = code[else_at + 1: j] if else_at is not None else []
                if isinstance(condition, int):
                    self.run(then_part if condition else else_part, stack, loop)
                else:
                    # どちらに進むか分からない。両方をなぞり、積まれた値の数が同じなら先へ進む
                    first, second = list(stack), list(stack)
                    self.run(then_part, first, list(loop))
                    self.run(else_part, second, list(loop))
                    if len(first) != len(second):
                        raise SystemExit(f"the branches of IF leave different stacks at {ins.text}")
                    # 同じ値でも、別の所で積んだ数字は別のものとして扱う (積んだ場所を取り違えない)
                    stack[:] = [a if a is b or (type(a) is int and type(b) is int and a == b) else UNKNOWN
                                for a, b in zip(first, second)]
                i = j
            elif op in ("ELSE", "EIF"):
                pass
            elif op in _OPS:
                takes, gives = _OPS[op]
                for role in takes:
                    pop(role)
                stack.extend([UNKNOWN] * gives)
            else:
                raise SystemExit(f"cannot trace {ins.text}")
            i += 1


def _marked(code: list[Instruction]) -> list[Instruction]:
    """積んだ数字に、積んだ場所の印を付ける"""
    for n, ins in enumerate(code):
        if is_push(ins.op):
            ins.values = [Pushed(v, (n, k)) for k, v in enumerate(ins.values)]
    return code


def shift_cvt(program: Program, funcs: dict[int, list[Instruction]], offset: int, label: str,
              allow_writes: bool) -> tuple[Program, int]:
    """program の中の、cvt の番号として積んだ数字を offset ずらしたもの。ずらした数を返す"""
    code = _marked(disassemble(program))
    tracer = Tracer(funcs)
    tracer.run(code, [])
    sources = set()
    for value in tracer.cvt_operands:
        if not isinstance(value, Pushed):
            raise SystemExit(f"{label}: a cvt number does not come straight from a push")
        sources.add(value.src)
    reused = sources & tracer.other_uses.keys()
    if reused:
        where = tracer.other_uses[min(reused)]
        raise SystemExit(f"{label}: a number pushed as a cvt number is also used otherwise (by {where})")
    if tracer.cvt_writes and not allow_writes:
        raise SystemExit(f"{label}: the glyph program writes to the cvt")
    assembly: list[str] = []
    for n, ins in enumerate(code):
        if is_push(ins.op):
            values = [int(v) + offset if (n, k) in sources else int(v) for k, v in enumerate(ins.values)]
            assembly.append("PUSH[ ]")
            assembly.extend(str(v) for v in values)
        else:
            assembly.append(ins.text)
    shifted = Program()
    shifted.fromAssembly(assembly)
    return shifted, len(sources)


def add(ud: TTFont, udp: TTFont, glyphs: dict[str, str], unhinted: set[str] = frozenset()) -> dict[str, int]:
    """glyphs (ud のグリフ名 → udp のグリフ名) の字に、BIZ UDP のヒンティングを付ける。unhinted
    (udp のグリフ名) は付けない (spec.UNHINTED。BIZ UDP のヒンティングで消える字)"""
    if ud["fpgm"].program.getBytecode() != udp["fpgm"].program.getBytecode():
        raise SystemExit("BIZ UD and BIZ UDP have different fpgm")
    funcs = functions(udp["fpgm"].program)
    offset = len(ud["cvt "].values)
    ud["cvt "].values = array("h", list(ud["cvt "].values) + list(udp["cvt "].values))

    prep, prep_shifted = shift_cvt(udp["prep"].program, funcs, offset, "BIZ UDP prep", allow_writes=True)
    merged = Program()
    merged.fromAssembly(ud["prep"].program.getAssembly() + prep.getAssembly())
    ud["prep"].program = merged

    hinted, sizes = 0, [0]
    for target, source in glyphs.items():
        program = getattr(udp["glyf"][source], "program", None)
        # 部品でできた字は、分解して足すので点の並びが変わる。命令はそのまま入れられない
        if program is None or not program.getBytecode() or udp["glyf"][source].isComposite():
            continue
        if source in unhinted:
            continue
        if ud["glyf"][target].numberOfContours != udp["glyf"][source].numberOfContours:
            raise SystemExit(f"{target}: the outline is not BIZ UDP's {source}")
        shifted, _ = shift_cvt(program, funcs, offset, source, allow_writes=False)
        ud["glyf"][target].program = shifted
        sizes.append(len(shifted.getBytecode()))
        hinted += 1

    maxp = ud["maxp"]
    maxp.maxStackElements = max(maxp.maxStackElements, udp["maxp"].maxStackElements)
    maxp.maxSizeOfInstructions = max(maxp.maxSizeOfInstructions, max(sizes))
    for field in ("maxStorage", "maxTwilightPoints", "maxFunctionDefs", "maxZones"):
        setattr(maxp, field, max(getattr(maxp, field), getattr(udp["maxp"], field)))
    return {"hinted": hinted, "cvt": len(udp["cvt "].values), "prep": prep_shifted}
