"""組版者が選ぶ引用符・記号の字形。既定の locl は保ち、後の lookup で選択を上書きする。

ss01: 和文引用符 (BIZ UD)。ss02: 欧文記号 (BIZ UDP、引用符は含めない)。
横組と縦組の両方を扱い、２つのセットは重ならない。ss02 は hwid/fwid 併用時も従来の結果を保つ。
ss01 は全角の和文引用符を選ぶため、fwid と併用しても全角の字になる。
名前は build.rename の後で付ける。
"""

import copy

from fontTools.ttLib.tables import otTables

import fraction_digits
import latin_symbols
import spec

LABELS = {
    "ss01": ("Japanese quotation marks", "和文引用符"),
    "ss02": ("Latin symbols", "欧文記号"),
    "ss03": ("Ruby kana (trial)", "ルビ仮名（試作）"),
}


def add(font, symbols: dict) -> None:
    import build

    gsub, cmap = font["GSUB"].table, font.getBestCmap()
    mapping = symbols["mapping"]
    quotes = {cmap[c] for c in spec.LATIN_QUOTES}
    japanese = {mapping[g]: g for g in quotes}
    latin = {g: target for g, target in mapping.items() if g not in quotes}
    latin.update(symbols["stylistic"]["mapping"])
    for original, (base, target) in symbols["vertical_mapping"].items():
        if base in quotes:
            japanese[target] = original
        else:
            latin[original] = target
    # “ ” は BIZ UD に縦組専用の字が無い。その UDP 縦組字形も元の全角の字へ戻す。
    for base in quotes:
        for tag in ("vert", "vrt2"):
            target = symbols["after"][tag].get(mapping[base])
            if target is not None:
                original = build.single_mapping(gsub, tag, {base}).get(base, base)
                japanese.setdefault(target, original)
    # locl と出力を共有すると、ss02 が無効でも幅の補正が働いてしまう。ss02 専用の
    # 複製にし、幅を指定した場合は「ss02 に入る直前の字」へ戻す。幅変換と通常の locl・
    # 縦組変換は既に済んでいるので、幅変換先のない字を別の幅へ戻すこともない。
    restore = {}

    def copy_classes(source: str, name: str) -> None:
        for field in ("GlyphClassDef", "MarkAttachClassDef"):
            definition = getattr(font["GDEF"].table, field, None)
            if definition is not None and source in definition.classDefs:
                definition.classDefs[name] = definition.classDefs[source]

    def clone(source: str, name: str, before: str) -> str:
        glyph = copy.deepcopy(font["glyf"][source])
        glyph.expand(font["glyf"])
        fraction_digits._add_glyph(font, name, glyph, font["hmtx"][source][0], font["vmtx"][source])
        font["hmtx"][name] = font["hmtx"][source]
        copy_classes(source, name)
        restore[name] = before
        return name

    chosen = {source: clone(target, source + ".ss02", source) for source, target in sorted(latin.items())}
    fraction_digits._new_feature(gsub, "ss01", latin_symbols.single(gsub, japanese))
    fraction_digits._new_feature(gsub, "ss02", latin_symbols.single(gsub, chosen))
    # BIZ UD に縦組専用字形がない記号も、複製同士でだけ変換する。通常の locl 出力や
    # 元の字には lookup を足さず、縦組の複製も変換前の字に戻せるようにする。
    for tag in ("vert", "vrt2"):
        forms = {}
        for base, target in symbols["mapping"].items():
            vertical = symbols["after"][tag].get(target)
            if base in chosen and vertical is not None:
                forms[chosen[base]] = clone(vertical, base + ".ss02." + tag, base)
        # ¹²³ など、横組は既に UDP と同じ字の vrt2 も、ss02 専用の字にだけつなぐ。
        # 命令は hinting.add の前に UDP から取り込んでおく。
        for base, vertical in symbols["stylistic"]["after"][tag].items():
            forms[chosen[base]] = vertical
            copy_classes(base, vertical)
            restore[vertical] = base
        latin_symbols.append_feature_mapping(gsub, tag, forms)
    for tag in ("fwid", "hwid"):
        latin_symbols.append_feature_mapping(gsub, tag, restore)
    latin_symbols.sort_features(gsub)


def label(font) -> None:
    for tag, (english, japanese) in LABELS.items():
        records = [r for r in font["GSUB"].table.FeatureList.FeatureRecord if r.FeatureTag == tag]
        if not records:
            continue
        name_id = 256 + int(tag[2:])
        font["name"].setName(english, name_id, 3, 1, 0x409)
        font["name"].setName(japanese, name_id, 3, 1, 0x411)
        for record in records:
            params = otTables.FeatureParamsStylisticSet()
            params.Version, params.UINameID = 0, name_id
            record.Feature.FeatureParams = params
