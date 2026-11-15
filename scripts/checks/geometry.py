"""輪郭を折れ線にして、インクの外形・間隔・はみ出しを測る補助。"""

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont

from .fonttables import outline


def flattened(font: TTFont, name: str, dx: float = 0, dy: float = 0) -> list[list[tuple[float, float]]]:
    """グリフの輪郭を、折れ線にしたもの (曲線は 16 に分ける)"""
    pen = DecomposingRecordingPen(font.getGlyphSet())
    font.getGlyphSet()[name].draw(pen)
    polygons, current, start = [], [], None
    for op, args in pen.value:
        if op == "moveTo":
            current, start = [args[0]], args[0]
        elif op == "lineTo":
            current.append(args[0])
        elif op == "qCurveTo":
            points = list(args)
            if points[-1] is None:  # 曲線の上の点が無い輪郭
                raise SystemExit(f"{name}: contours without on-curve points are not checked")
            p0 = current[-1]
            controls, end = points[:-1], points[-1]
            for k, control in enumerate(controls):
                target = end if k == len(controls) - 1 else (
                    ((control[0] + controls[k + 1][0]) / 2, (control[1] + controls[k + 1][1]) / 2))
                for step in range(1, 17):
                    t = step / 16
                    current.append(((1 - t) ** 2 * p0[0] + 2 * t * (1 - t) * control[0] + t * t * target[0],
                                    (1 - t) ** 2 * p0[1] + 2 * t * (1 - t) * control[1] + t * t * target[1]))
                p0 = target
        elif op in ("closePath", "endPath"):
            if current:
                polygons.append(current)
            current = []
    return [[(x + dx, y + dy) for x, y in polygon] for polygon in polygons]


def row(polygons, y: float) -> list[float]:
    xs = []
    for polygon in polygons:
        for (x0, y0), (x1, y1) in zip(polygon, polygon[1:] + polygon[:1]):
            if (y0 <= y < y1) or (y1 <= y < y0):
                xs.append(x0 + (y - y0) / (y1 - y0) * (x1 - x0))
    return sorted(xs)


def ink_gap(left, right) -> float:
    """left のインクの右から right のインクの左までの、同じ高さどうしのいちばん近い横の距離"""
    ys = [y for polygon in left + right for _x, y in polygon]
    best = None
    for y in range(int(min(ys)), int(max(ys)) + 1, 3):
        a, b = row(left, y + 0.5), row(right, y + 0.5)
        if a and b:
            best = b[0] - a[-1] if best is None else min(best, b[0] - a[-1])
    return best


def ink_area(font: TTFont, name: str) -> float:
    total = 0.0
    for polygon in flattened(font, name):
        total += sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(polygon, polygon[1:] + polygon[:1])) / 2
    return abs(total)


def glyph_bounds(font: TTFont, name: str):
    pen = BoundsPen(font.getGlyphSet())
    font.getGlyphSet()[name].draw(pen)
    return pen.bounds


def offset_of(font: TTFont, name: str, other: str):
    """name の輪郭が other の輪郭を平行に動かしたものなら、その (dx, dy)。違えば None"""
    a, b = outline(font, name), outline(font, other)
    if a[1:] != b[1:] or not a[0]:
        return None
    dx, dy = a[0][0][0] - b[0][0][0], a[0][0][1] - b[0][0][1]
    return (dx, dy) if all((x - u, y - v) == (dx, dy) for (x, y), (u, v) in zip(a[0], b[0])) else None


def moved_by(font: TTFont, name: str, other: TTFont, other_name: str):
    """font の name の輪郭が、other の other_name の輪郭を平行に動かしたものなら、その (dx, dy)"""
    a, b = outline(font, name), outline(other, other_name)
    if a[1:] != b[1:] or not a[0]:
        return None
    dx, dy = a[0][0][0] - b[0][0][0], a[0][0][1] - b[0][0][1]
    return (dx, dy) if all((x - u, y - v) == (dx, dy) for (x, y), (u, v) in zip(a[0], b[0])) else None


def overflow(font: TTFont, name: str) -> tuple[int, int]:
    """字のインクが、行の上 (usWinAscent) と下 (usWinDescent) から出る量"""
    bounds = glyph_bounds(font, name)
    if bounds is None:
        return 0, 0
    os2 = font["OS/2"]
    return max(0, bounds[3] - os2.usWinAscent), max(0, -os2.usWinDescent - bounds[1])


def drawing(font: TTFont, name: str) -> list:
    pen = DecomposingRecordingPen(font.getGlyphSet())
    font.getGlyphSet()[name].draw(pen)
    return pen.value
