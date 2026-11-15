"""元のフォントに依らない基準 (公開 1.006 の字送り、Noto の字の向き) との照合。"""

import glyph_reference
import width_reference

from .common import FontContext, SOURCES, problems


def check_recorded_references(ctx: FontContext) -> None:
    """記録した字送りと、字の向き・位置の基準との照合。"""
    label = ctx.label
    family = ctx.family
    weight = ctx.weight
    path = ctx.path
    font = ctx.font
    shaper = ctx.shaper
    problems.extend(width_reference.check_recorded(label, font, shaper))
    problems.extend(glyph_reference.check_font(label, path, family["key"],
                                               [SOURCES / f"{family['ud']}-{weight}.ttf", SOURCES / f"{family['udp']}-{weight}.ttf"]))
