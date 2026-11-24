"""スタイルセット (ss01・ss02・ss03 の名前) と記号の幅・複製。"""

import unicodedata
from pathlib import Path

import freetype_render
import spec

from .common import FontContext, Shaped, check
from .fonttables import gsub_mapping, outline, outputs, vertical_closure
from .hinting import HINTING_PPEMS, stripped_font


STYLE_MODES = ((False, ()), (True, ()), (True, ("vert=0", "vrt2")))


def check_style_widths(ctx: FontContext) -> int:
    """記号の全対象字を実際に組み、ss02 が明示した幅・字形・縦組位置を変えないこと。"""
    label = ctx.label
    font = ctx.font
    shaper = ctx.shaper
    cmap = font.getBestCmap()
    codes = [code for code in spec.LATIN_SYMBOLS if code in cmap and code not in spec.LATIN_QUOTES
             and unicodedata.category(chr(code)) != "Cf"]
    bad, count = [], 0
    for code in codes:
        for language in ("ja", "en"):
            for context in ("{}", "字{}字", "A{}A"):
                text = context.format(chr(code))
                for vertical, vertical_features in STYLE_MODES:
                    for tag in ("hwid", "fwid"):
                        plain = shaper.shape(text, language, vertical, (tag, *vertical_features))
                        styled = shaper.shape(text, language, vertical, (tag, "ss02", *vertical_features))
                        if plain != styled:
                            bad.append((f"U+{code:04X}", language, context, vertical, vertical_features, tag))
                        count += 1
    check(bool(count), f"{label}: no style/width combinations were checked")
    check(not bad, f"{label}: {len(bad)} ss02 combinations override explicit widths: {bad[:8]}")
    return count


def check_style_copies(label: str, ours: Shaped, udp: Shaped, path: Path, source_path: Path,
                       stripped_path: Path | None = None, listed=()) -> None:
    """各複製を対応する文字・縦組経路の UDP 字形に照合し、未符号化の候補も描いて比べる。斜線を書き直した字
    (spec.DIAGONAL_GLYPHS) の複製は、足した末尾を外した字 (stripped_path) で比べる (末尾が何を変えるかは hinting.check_diagonal_hints が縛る)。"""
    font = ours.font
    clones = vertical_closure(font, outputs(font, ("ss02",)))
    originals = vertical_closure(font, outputs(font, ("locl",)))
    check(bool(clones) and not clones & originals, f"{label}: ss02 copies are not isolated from locl")
    covered, pairs = set(), {}
    cmap, cmap_udp = font.getBestCmap(), udp.font.getBestCmap()
    unhinted = {cmap_udp[code] for code in spec.UNHINTED if code in cmap_udp}
    local = gsub_mapping(font, "locl")
    forms = {tag: gsub_mapping(font, tag) for tag in ("vert", "vrt2")}
    definitions = [getattr(font["GDEF"].table, field, None)
                   for field in ("GlyphClassDef", "MarkAttachClassDef")]

    def classes(name):
        return tuple(definition.classDefs.get(name, 0) if definition is not None else 0 for definition in definitions)

    for code in spec.LATIN_SYMBOLS:
        if code not in cmap or code not in cmap_udp or code in spec.LATIN_QUOTES or unicodedata.category(chr(code)) == "Cf":
            continue
        for vertical, features in STYLE_MODES:
            normal = cmap[code]
            if vertical:
                form = forms["vrt2" if features else "vert"]
                normal = form.get(normal, normal)
            normal = local.get(normal, normal)
            if vertical:
                normal = form.get(normal, normal)
            # 通常の locl が先に変える ALWAYS_UDP の専用複製も、直接選んで検査する。
            actual = ours.shaper.shape(chr(code), "ja", vertical, ("locl=0", "ss02", *features))
            wanted = udp.shaper.shape(chr(code), "ja", vertical, features)
            check(len(actual) == len(wanted), f"{label}: ss02 copy count differs for U+{code:04X} {features}")
            for a, b in zip(actual, wanted):
                name, source = ours.order[a[0]], udp.order[b[0]]
                if name not in clones:
                    continue
                covered.add(name)
                check(classes(name) == classes(normal),
                      f"{label}: ss02 changed GDEF classes for U+{code:04X} {features}")
                check(outline(font, name) == outline(udp.font, source)
                      and font["hmtx"][name] == udp.font["hmtx"][source]
                      and font["vmtx"][name] == udp.font["vmtx"][source],
                      f"{label}: ss02 copy of U+{code:04X} {features} is not the corresponding UDP glyph")
                if source not in unhinted:
                    pairs[(a[0], b[0])] = f"U+{code:04X} {features}"
    check(not clones - covered, f"{label}: ss02 copies have no character/path correspondence: {sorted(clones - covered)[:8]}")
    for mode, interpreter, flags in freetype_render.MODES:
        actual = freetype_render.Renderer(path, interpreter, flags)
        stripped = freetype_render.Renderer(stripped_path, interpreter, flags) if stripped_path else actual
        reference = freetype_render.Renderer(source_path, interpreter, flags)
        bad = [(description, ppem) for (gid, source), description in pairs.items() for ppem in HINTING_PPEMS
               if (stripped if ours.order[gid] in listed else actual).render(gid, ppem) != reference.render(source, ppem)]
        check(not bad, f"{label}: {mode}: ss02 copies differ from corresponding UDP rasters: {bad[:6]}")
        if stripped is not actual:
            stripped.close()
        actual.close()
        reference.close()


def check_style_copies_all(ctx: FontContext) -> None:
    """ss02 の複製が、対応する BIZ UDP の字と同じであること。"""
    label = ctx.label
    path = ctx.path
    ours = ctx.ours
    udp = ctx.udp_shaped
    udp_path = ctx.udp_path
    with stripped_font(ctx) as (stripped_path, listed):
        check_style_copies(label, ours, udp, path, udp_path, stripped_path, listed)


def check_style_quotes(ctx: FontContext) -> None:
    """ss01・ss02 が引用符・記号を BIZ UD・BIZ UDP の字にすること。"""
    label = ctx.label
    ours = ctx.ours
    ud = ctx.ud_shaped
    udp = ctx.udp_shaped
    cmap = ctx.cmap
    cmap_udp = ctx.cmap_udp
    for language in ("ja", "en"):
        for vertical, vertical_features in STYLE_MODES:
            for char in "‘’“”":
                reference = chr(spec.VERTICAL_SWAPPED_QUOTES.get(ord(char), ord(char))) if vertical else char
                check(ours.run(char, language, vertical, ("ss01", *vertical_features)) == ud.run(reference, language, vertical, vertical_features),
                      f"{label}: ss01 {char} is not BIZ UD ({language}, vertical={vertical})")
                check(ours.run(char, language, vertical, ("ss01", "ss02", *vertical_features)) == ours.run(char, language, vertical, ("ss01", *vertical_features)),
                      f"{label}: ss02 overrides ss01 quotes")
            for code in spec.LATIN_SYMBOLS:
                if (code not in cmap or code not in cmap_udp or code in spec.LATIN_QUOTES
                        or unicodedata.category(chr(code)) == "Cf"):
                    continue
                char = chr(code)
                check(ours.run(char, language, vertical, ("ss02", *vertical_features)) == udp.run(char, language, vertical, vertical_features),
                      f"{label}: ss02 U+{code:04X} is not BIZ UDP ({language}, vertical={vertical}, {vertical_features})")


def check_style_labels(ctx: FontContext) -> None:
    """ss01〜ss03 に名前が付いていること。"""
    label = ctx.label
    font = ctx.font
    for tag in ("ss01", "ss02", "ss03"):
        for record in font["GSUB"].table.FeatureList.FeatureRecord:
            if record.FeatureTag == tag:
                params = record.Feature.FeatureParams
                check(params is not None and font["name"].getDebugName(params.UINameID), f"{label}: {tag} has no label")
