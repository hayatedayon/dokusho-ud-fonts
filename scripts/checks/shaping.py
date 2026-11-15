"""HarfBuzz で組んで、字を変えていない文字・合字・異体字・欧文・見えない文字を元のフォントと比べる。"""

import spec

from .common import FontContext, JAPANESE_CONTEXTS, LATIN_CONTEXT, Report, same_glyph
from .fonttables import gsub_ligatures


def check_kept_characters(ctx: FontContext) -> None:
    """字を変えていない和文の文字が、BIZ UD と同じに組まれること。"""
    font = ctx.font
    font_ud = ctx.ud
    ours = ctx.ours
    ud = ctx.ud_shaped
    cmap = ctx.cmap
    cmap_ud = ctx.cmap_ud
    marks = ctx.marks
    report = Report(ctx.label)
    # 和文の文脈で、字を変えていない文字
    kept = [code for code in sorted(cmap_ud) if code >= 0x20 and code not in spec.LATIN and code not in marks
            and code not in spec.ALWAYS_UDP and code in cmap and same_glyph(font, cmap[code], font_ud, cmap_ud[code])]
    tags = sorted({r.FeatureTag for r in font_ud["GSUB"].table.FeatureList.FeatureRecord}
                  - {"aalt", *spec.FRACTION_FEATURES})
    for code in kept:
        for context, language in JAPANESE_CONTEXTS:
            text = context.format(chr(code))
            for vertical in (False, True):
                if ours.run(text, language, vertical, cluster=1) != ud.run(text, language, vertical, cluster=1):
                    report(f"in Japanese {'vertical' if vertical else 'horizontal'} text differs from BIZ UD",
                           f"U+{code:04X}")
        text = JAPANESE_CONTEXTS[0][0].format(chr(code))
        for tag in tags:
            for vertical in (False, True):
                if ours.run(text, "ja", vertical, [tag], 1) != ud.run(text, "ja", vertical, [tag], 1):
                    report(f"with {tag} differs from BIZ UD", f"U+{code:04X}{' (vertical)' if vertical else ''}")
    report.flush()


def check_quotes_always_udp(ctx: FontContext) -> None:
    """引用符とアポストロフィが、和文の中でも BIZ UDP の字に組まれること。"""
    ours = ctx.ours
    udp = ctx.udp_shaped
    report = Report(ctx.label)
    # spec.ALWAYS_UDP は、和文の中でも日本語の文書でも BIZ UDP の字 (Chromium は、和文の後の “Hello の “
    # を和文の組に入れる)。縦組も BIZ UDP の縦組の字 (Chromium は、縦組の引用符を正立させる)
    for code in spec.ALWAYS_UDP:
        expected = udp.run(LATIN_CONTEXT[0].format(chr(code)), "en", cluster=1)
        for context, language in [*JAPANESE_CONTEXTS, (LATIN_CONTEXT[0], "ja"), ("{}", "ja"), ("あ{}", "ja")]:
            text = context.format(chr(code))
            index = context.index("{}")
            cluster = len(context[:index].encode())
            if ours.run(text, language, cluster=cluster) != expected:
                report("always-UDP symbols are not BIZ UDP's in horizontal text", f"U+{code:04X} in {context}")
            if code not in spec.VERTICAL_MINUTES and ours.run(text, language, True, cluster=cluster) != udp.run(text, language, True, cluster=cluster):
                report("always-UDP symbols are not BIZ UDP's in vertical text", f"U+{code:04X} in {context}")
    report.flush()


def check_ligatures_and_variations(ctx: FontContext) -> None:
    """BIZ UD の合字と異体字 (IVS) が BIZ UD と同じに組まれること。"""
    font_ud = ctx.ud
    ours = ctx.ours
    ud = ctx.ud_shaped
    cmap_ud = ctx.cmap_ud
    report = Report(ctx.label)
    # BIZ UD の合字と異体字
    first_codes = {name: code for code, name in sorted(cmap_ud.items(), reverse=True)}
    always_names = {cmap_ud[code] for code in spec.ALWAYS_UDP}  # dlig の ！！ → ‼ は、locl で BIZ UDP の字になる
    for tag, ligatures in sorted({tag: gsub_ligatures(font_ud, tag) for tag in ("ccmp", "liga", "dlig")}.items()):
        for first, entries in ligatures.items():
            for components, target in entries:
                sequence = [first, *components]
                if not all(g in first_codes for g in sequence) or first_codes[first] in spec.LATIN or target in always_names:
                    continue
                text = "あ" + "".join(chr(first_codes[g]) for g in sequence)
                for vertical in (False, True):
                    if ours.run(text, "ja", vertical, [tag]) != ud.run(text, "ja", vertical, [tag]):
                        report(f"{tag} ligatures differ from BIZ UD", " ".join(f"U+{ord(c):04X}" for c in text[1:]))
    for table in font_ud["cmap"].tables:
        if table.format != 14:
            continue
        for selector, pairs in table.uvsDict.items():
            for base, _glyph in pairs:
                text = chr(base) + chr(selector)
                for vertical in (False, True):
                    if ours.run(text, "ja", vertical) != ud.run(text, "ja", vertical):
                        report("variation sequences differ from BIZ UD", f"U+{base:04X} U+{selector:04X}")
    report.flush()


def check_latin_text(ctx: FontContext) -> None:
    """英語の文の中の欧字と記号が BIZ UDP と同じに組まれること。"""
    ours = ctx.ours
    udp = ctx.udp_shaped
    cmap = ctx.cmap
    cmap_udp = ctx.cmap_udp
    marks = ctx.marks
    ignorable = ctx.ignorable
    orientation = ctx.orientation
    report = Report(ctx.label)
    # 英語の文脈の欧字と記号
    context, language = LATIN_CONTEXT
    for code in sorted(set(spec.LATIN) | set(spec.LATIN_SYMBOLS)):
        if code not in cmap or code not in cmap_udp or code in marks or code in ignorable:
            continue
        text = context.format(chr(code))
        if ours.run(text, language, cluster=1) != udp.run(text, language, cluster=1):
            report("in Latin text differs from BIZ UDP", f"U+{code:04X}")
        # 1 字だけで組む (ブラウザが行末に足すハイフンなど)
        if ours.run(chr(code), language) != udp.run(chr(code), language):
            report("alone in Latin text differs from BIZ UDP", f"U+{code:04X}")
        if orientation.get(code, "R") != "R":
            a, b = ours.ink(text, language, True)[1], udp.ink(text, language, True)[1]
            if (a is None) != (b is None) or (a and any(abs(p - q) > 1 for p, q in zip(a, b))):
                report("upright in vertical Latin text is not placed as in BIZ UDP", f"U+{code:04X}")
    report.flush()


def check_invisible(ctx: FontContext) -> None:
    """見えない文字がどの文脈でも幅 0 であること。"""
    ours = ctx.ours
    cmap = ctx.cmap
    ignorable = ctx.ignorable
    report = Report(ctx.label)
    # 見えない文字
    contexts = [*JAPANESE_CONTEXTS, LATIN_CONTEXT]
    for code in sorted(c for c in cmap if c in ignorable):
        for context, language in contexts:
            for vertical in (False, True):
                if any(xa or ya for _o, xa, ya, _xo, _yo in ours.run(context.format(chr(code)), language, vertical, cluster=1)):
                    report("invisible characters are not of zero width", f"U+{code:04X}"
                           f"{' (vertical)' if vertical else ''} after {context[0]}")
    report.flush()
