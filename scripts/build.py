"""BIZ UD と BIZ UDP から、読書 UD明朝・読書 UDゴシックを作る (fonts/ に出す)。

和文の本の組み方 (JLReq のベタ組と、プロポーショナルな欧字) にするため、BIZ UD を元にして、
欧字だけを同じデザインの BIZ UDP の字にする。

1. 欧字 (spec.LATIN) のグリフの形・字幅・縦の字送りを BIZ UDP のものにする
2. 欧字からの GSUB の置き換え (spec.LATIN_FEATURES) を BIZ UDP と同じにする。置き換え先の
   グリフの形か字送りが違えば、それも BIZ UDP のものにする
3. 名前を読書 UD に変え (BIZ UD はモリサワの商標)、等幅の印 (post.isFixedPitch) を外す

BIZ UD と BIZ UDP は、ヒンティングの cvt が違う。BIZ UDP から持ってきたグリフの命令は
BIZ UD の cvt では正しく働かないので、外す。
"""

import copy
import os
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.misc.timeTools import epoch_diff as EPOCH_DIFF
from fontTools.ttLib.tables._g_l_y_f import Glyph

import spec

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "sources"
OUTPUT = ROOT / "fonts"


def feature_lookups(gsub, tag: str) -> list[int]:
    indexes: list[int] = []
    for record in gsub.FeatureList.FeatureRecord:
        if record.FeatureTag == tag:
            indexes.extend(i for i in record.Feature.LookupListIndex if i not in indexes)
    return indexes


def single_subtables(gsub, index: int):
    for subtable in gsub.LookupList.Lookup[index].SubTable:
        subtable = getattr(subtable, "ExtSubTable", subtable)
        if hasattr(subtable, "mapping"):
            yield subtable


def lookup_users(gsub, index: int) -> set[str]:
    return {r.FeatureTag for r in gsub.FeatureList.FeatureRecord if index in r.Feature.LookupListIndex}


def same_glyph(a: TTFont, b: TTFont, name: str) -> bool:
    if a["hmtx"][name] != b["hmtx"][name] or a["vmtx"][name] != b["vmtx"][name]:
        return False
    ga, gb = a["glyf"][name], b["glyf"][name]
    ca, ea, fa = ga.getCoordinates(a["glyf"])
    cb, eb, fb = gb.getCoordinates(b["glyf"])
    return list(ca) == list(cb) and list(ea) == list(eb) and list(fa) == list(fb)


def take_glyph(target: TTFont, source: TTFont, name: str) -> None:
    """source のグリフ (形・字幅・縦の字送り) を target に入れる。ヒンティングの命令は外す"""
    glyph: Glyph = copy.deepcopy(source["glyf"][name])
    glyph.expand(source["glyf"])
    if glyph.isComposite():
        raise SystemExit(f"{name}: composite glyphs are not expected in the Latin of BIZ UDP")
    glyph.removeHinting()
    target["glyf"][name] = glyph
    target["hmtx"][name] = source["hmtx"][name]
    target["vmtx"][name] = source["vmtx"][name]


def merge_latin(ud: TTFont, udp: TTFont) -> dict:
    cmap_ud, cmap_udp = ud.getBestCmap(), udp.getBestCmap()
    latin = []
    for code in spec.LATIN:
        if cmap_ud.get(code) != cmap_udp.get(code) or code not in cmap_ud:
            raise SystemExit(f"U+{code:04X}: BIZ UD and BIZ UDP map it to different glyphs")
        latin.append(cmap_ud[code])
    for name in latin:
        take_glyph(ud, udp, name)

    gsub_ud, gsub_udp = ud["GSUB"].table, udp["GSUB"].table
    changed_mappings = 0
    targets: set[str] = set()
    for tag in spec.LATIN_FEATURES:
        wanted = {}
        for index in feature_lookups(gsub_udp, tag):
            for subtable in single_subtables(gsub_udp, index):
                wanted.update({k: v for k, v in subtable.mapping.items() if k in latin})
        targets.update(wanted.values())
        subtables = [s for i in feature_lookups(gsub_ud, tag) for s in single_subtables(gsub_ud, i)]
        for index in feature_lookups(gsub_ud, tag):
            # 欧字を持つ lookup を、ほかの機能と分け合っていないこと (変えると、その機能も変わる)
            if any(k in latin for s in single_subtables(gsub_ud, index) for k in s.mapping):
                users = lookup_users(gsub_ud, index)
                if users != {tag}:
                    raise SystemExit(f"GSUB lookup {index} for {tag} is shared with {sorted(users)}")
        if wanted and not subtables:
            raise SystemExit(f"{tag}: BIZ UD has no single substitution to put the Latin into")
        for subtable in subtables:
            for key in [k for k in subtable.mapping if k in latin and k not in wanted]:
                del subtable.mapping[key]
                changed_mappings += 1
        for key, value in wanted.items():
            holder = next((s for s in subtables if key in s.mapping), subtables[0])
            if holder.mapping.get(key) != value:
                holder.mapping[key] = value
                changed_mappings += 1

    glyph_names = set(ud.getGlyphOrder())
    missing = sorted(t for t in targets if t not in glyph_names)
    if missing:
        raise SystemExit(f"GSUB targets missing from BIZ UD: {missing[:10]}")
    taken_targets = [t for t in sorted(targets) if t not in latin and not same_glyph(ud, udp, t)]
    for name in taken_targets:
        take_glyph(ud, udp, name)
    return {"latin": len(latin), "mappings": changed_mappings, "targets": len(taken_targets)}


def license_text() -> str:
    """OFL.txt の全文 (著作権表示と使用許諾)"""
    return (ROOT / "OFL.txt").read_text(encoding="utf-8").replace("\r\n", "\n").strip()


def rename(font: TTFont, family: dict, weight: str) -> None:
    name = font["name"]
    original_copyright = name.getDebugName(0)
    keep = {9, 12, 14}  # 設計者・設計者の URL・ライセンスの URL
    name.names = [r for r in name.names if r.nameID in keep]
    postscript = f"{family['postscript']}-{weight}"
    full_en = family["name_en"] if weight == "Regular" else f"{family['name_en']} {weight}"
    full_ja = family["name_ja"] if weight == "Regular" else f"{family['name_ja']} {weight}"
    records = {
        0: (f"{original_copyright} {spec.COPYRIGHT}", None),
        1: (family["name_en"], family["name_ja"]),
        2: (weight, weight),
        3: (f"{spec.VERSION};NONE;{postscript}", None),
        4: (full_en, full_ja),
        5: (f"Version {spec.VERSION}; based on {family['source_name']} 1.06 and "
            f"{family['source_name'].replace('BIZ UD', 'BIZ UDP')} 1.06", None),
        6: (postscript, None),
        10: (
            f"{family['name_en']} is {family['source_name']} with the proportional Latin letters of the same "
            "design, for reading books: kana, kanji and punctuation sit on the full-width grid, while Latin "
            "letters keep their own widths.",
            None,
        ),
        11: (spec.REPOSITORY, None),
        # 著作権表示 (0) と使用許諾の全文。OFL は、配るフォントの 1 つ 1 つに、両方を含めることを
        # 求める (利用者が見られるメタデータの欄でよい)。フォントのファイルだけで配れるように
        13: (license_text(), None),
    }
    for name_id, (english, japanese) in records.items():
        name.setName(english, name_id, 3, 1, 0x409)
        if japanese:
            name.setName(japanese, name_id, 3, 1, 0x411)


def build(family: dict, weight: str) -> Path:
    ud = TTFont(SOURCES / f"{family['ud']}-{weight}.ttf")
    udp = TTFont(SOURCES / f"{family['udp']}-{weight}.ttf")
    if ud["head"].unitsPerEm != udp["head"].unitsPerEm:
        raise SystemExit("BIZ UD and BIZ UDP have different units per em")
    if ud["fpgm"].compile(ud) != udp["fpgm"].compile(udp):
        raise SystemExit("BIZ UD and BIZ UDP have different fpgm")
    stats = merge_latin(ud, udp)

    rename(ud, family, weight)
    ud["post"].isFixedPitch = 0
    ud["OS/2"].achVendID = "NONE"
    ud["OS/2"].recalcAvgCharWidth(ud)
    ud["head"].fontRevision = float(spec.VERSION)
    # 元の署名は、変えたフォントでは合わない
    if "DSIG" in ud:
        del ud["DSIG"]

    # 同じ元からは同じファイルを作る。作った日時は SOURCE_DATE_EPOCH (無ければ BIZ UD のもの)
    ud.recalcTimestamp = False
    if "SOURCE_DATE_EPOCH" in os.environ:
        ud["head"].modified = int(os.environ["SOURCE_DATE_EPOCH"]) - EPOCH_DIFF

    OUTPUT.mkdir(exist_ok=True)
    out = OUTPUT / spec.output_name(family, weight)
    ud.save(out)
    print(f"{out.relative_to(ROOT)}: Latin {stats['latin']} glyphs, {stats['mappings']} GSUB mappings, "
          f"{stats['targets']} GSUB targets from BIZ UDP")
    return out


def main() -> int:
    for family in spec.FAMILIES:
        for weight in spec.WEIGHTS:
            build(family, weight)
    return 0


if __name__ == "__main__":
    sys.exit(main())
