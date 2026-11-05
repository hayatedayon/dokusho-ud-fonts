"""BIZ UD と BIZ UDP から、読書 UD明朝・読書 UDゴシックを作る (fonts/ に出す)。

和文の本の組み方 (JLReq のベタ組と、プロポーショナルな欧字) にするため、BIZ UD を元にして、
欧字だけを同じデザインの BIZ UDP の字にする。

1. 欧字 (spec.LATIN) のグリフの形・字幅・縦の字送りを BIZ UDP のものにする
2. 欧字からの GSUB の置き換え (spec.LATIN_FEATURES) と、欧字から始まる合字
   (spec.LATIN_LIGATURE_FEATURES) を BIZ UDP と同じにする。置き換え先のグリフの形か字送りが
   違えば、それも BIZ UDP のものにする。字形の候補 (aalt) の欧字の候補も、それに合わせる
3. 欧文の中の記号 (引用符・アポストロフィ・ダッシュなど) を、欧字の用字系の中でだけ BIZ UDP の
   字にする (latin_symbols.py。日本語の文書では置き換えない)
4. BIZ UDP から持ってきた字に、BIZ UDP のヒンティングを付ける (hinting.py)
5. 名前を読書 UD に変え (BIZ UD はモリサワの商標)、等幅の印 (post.isFixedPitch) を外す
6. 約物の詰め (halt・vhal) を足す (spacing.py)

BIZ UD と BIZ UDP は、ヒンティングの cvt と prep が違う。BIZ UDP から持ってきた字の命令は、
いったん外し (BIZ UD の cvt では正しく働かない)、hinting.py が cvt と prep を付け足してから、
cvt の番号をずらして入れ直す。
"""

import copy
import os
import re
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.misc.timeTools import epoch_diff as EPOCH_DIFF
from fontTools.ttLib.tables._g_l_y_f import Glyph

import fetch_sources
import hinting
import latin_symbols
import spacing
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


def subtables(gsub, index: int, kind: str):
    """lookup の、kind ("mapping" は 1 対 1、"ligatures" は合字、"alternates" は候補) のサブテーブル"""
    for subtable in gsub.LookupList.Lookup[index].SubTable:
        subtable = getattr(subtable, "ExtSubTable", subtable)
        if hasattr(subtable, kind):
            yield subtable


def feature_subtables(gsub, tag: str, kind: str) -> list:
    return [s for i in feature_lookups(gsub, tag) for s in subtables(gsub, i, kind)]


def single_mapping(gsub, tag: str, keys) -> dict[str, str]:
    """tag の 1 対 1 の置き換えのうち、keys からのもの。同じ字が何度も出れば、先のものを取る
    (文字を並べる仕組みは、先の lookup で置き換えた字を、後の lookup にかける)"""
    mapping: dict[str, str] = {}
    for subtable in feature_subtables(gsub, tag, "mapping"):
        for key, value in subtable.mapping.items():
            if key in keys:
                mapping.setdefault(key, value)
    return mapping


def alternates(gsub, tag: str, keys) -> dict[str, list[str]]:
    """tag (aalt など) の候補のうち、keys からのもの。1 対 1 の置き換えも候補 1 つとして数える"""
    result: dict[str, list[str]] = {}
    for index in feature_lookups(gsub, tag):
        for subtable in subtables(gsub, index, "mapping"):
            for key, value in subtable.mapping.items():
                if key in keys and value not in result.setdefault(key, []):
                    result[key].append(value)
        for subtable in subtables(gsub, index, "alternates"):
            for key, values in subtable.alternates.items():
                if key in keys:
                    result.setdefault(key, []).extend(v for v in values if v not in result[key])
    return result


def ensure_own_lookups(gsub, tag: str, kind: str, keys=None) -> None:
    """tag の lookup のうち、keys の字 (None ならどの字でも) を持つものを、ほかの機能と分け合って
    いないこと (変えると、その機能も変わる)"""
    for index in feature_lookups(gsub, tag):
        if keys is not None and not any(k in keys for s in subtables(gsub, index, kind) for k in getattr(s, kind)):
            continue
        users = {r.FeatureTag for r in gsub.FeatureList.FeatureRecord if index in r.Feature.LookupListIndex}
        if users != {tag}:
            raise SystemExit(f"GSUB lookup {index} for {tag} is shared with {sorted(users)}")


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
    latin: list[str] = []
    for code in spec.LATIN:
        if code not in cmap_ud and code not in cmap_udp:
            continue
        if cmap_ud.get(code) != cmap_udp.get(code):
            raise SystemExit(f"U+{code:04X}: BIZ UD and BIZ UDP map it to different glyphs")
        latin.append(cmap_ud[code])
    for name in latin:
        take_glyph(ud, udp, name)

    gsub_ud, gsub_udp = ud["GSUB"].table, udp["GSUB"].table
    latin_set = set(latin)
    before = {tag: single_mapping(gsub_ud, tag, latin_set) for tag in spec.LATIN_FEATURES}
    changed_mappings = 0
    targets: set[str] = set()
    for tag in spec.LATIN_FEATURES:
        wanted = single_mapping(gsub_udp, tag, latin_set)
        targets.update(wanted.values())
        ensure_own_lookups(gsub_ud, tag, "mapping", latin_set)
        subtables_ud = feature_subtables(gsub_ud, tag, "mapping")
        if wanted and not subtables_ud:
            raise SystemExit(f"{tag}: BIZ UD has no single substitution to put the Latin into")
        for subtable in subtables_ud:
            for key in [k for k in subtable.mapping if k in latin_set and k not in wanted]:
                del subtable.mapping[key]
                changed_mappings += 1
        for key, value in wanted.items():
            holder = next((s for s in subtables_ud if key in s.mapping), subtables_ud[0])
            if holder.mapping.get(key) != value:
                holder.mapping[key] = value
                changed_mappings += 1

    glyph_names = set(ud.getGlyphOrder())
    changed_mappings += merge_latin_ligatures(gsub_ud, gsub_udp, latin_set, targets, glyph_names)
    changed_mappings += merge_latin_alternates(gsub_ud, gsub_udp, latin_set, before)

    missing = sorted(t for t in targets if t not in glyph_names)
    if missing:
        raise SystemExit(f"GSUB targets missing from BIZ UD: {missing[:10]}")
    taken_targets = [t for t in sorted(targets) if t not in latin_set and not same_glyph(ud, udp, t)]
    for name in taken_targets:
        take_glyph(ud, udp, name)
    return {"latin": len(latin), "mappings": changed_mappings, "targets": len(taken_targets),
            "glyphs": latin + taken_targets}


def merge_latin_ligatures(gsub_ud, gsub_udp, latin: set[str], targets: set[str], glyph_names: set[str]) -> int:
    """欧字から始まる合字 (spec.LATIN_LIGATURE_FEATURES) を BIZ UDP と同じにする。置き換え先は
    targets に足す (BIZ UD に無ければ merge_latin が止まる)。つなぐ字 (結合用のアクセントなど) は
    BIZ UD のままにし、BIZ UD にあることだけを確かめる。変えた合字の数を返す"""
    changed = 0
    for tag in spec.LATIN_LIGATURE_FEATURES:
        wanted = {}
        for subtable in feature_subtables(gsub_udp, tag, "ligatures"):
            for first, ligatures in subtable.ligatures.items():
                if first not in latin:
                    continue
                # いくつものサブテーブルに分かれていると、1 つにまとめたときに順が変わる
                if first in wanted:
                    raise SystemExit(f"{tag}: BIZ UDP has ligatures from {first} in more than one subtable")
                wanted[first] = ligatures
        ensure_own_lookups(gsub_ud, tag, "ligatures", latin)
        subtables_ud = feature_subtables(gsub_ud, tag, "ligatures")
        if wanted and not subtables_ud:
            raise SystemExit(f"{tag}: BIZ UD has no ligature substitution to put the Latin into")
        for subtable in subtables_ud:
            for first in [k for k in subtable.ligatures if k in latin and k not in wanted]:
                del subtable.ligatures[first]
                changed += 1
        for first, ligatures in wanted.items():
            holder = next((s for s in subtables_ud if first in s.ligatures), subtables_ud[0])
            for subtable in subtables_ud:
                if subtable is not holder and first in subtable.ligatures:
                    del subtable.ligatures[first]
            current = [(list(l.Component), l.LigGlyph) for l in holder.ligatures.get(first, [])]
            if current != [(list(l.Component), l.LigGlyph) for l in ligatures]:
                holder.ligatures[first] = copy.deepcopy(ligatures)
                changed += 1
            for ligature in ligatures:
                targets.add(ligature.LigGlyph)
                missing = [c for c in ligature.Component if c not in glyph_names]
                if missing:
                    raise SystemExit(f"{tag}: the ligature {first} {missing} of BIZ UDP needs glyphs missing from BIZ UD")
    return changed


def merge_latin_alternates(gsub_ud, gsub_udp, latin: set[str], before: dict[str, dict[str, str]]) -> int:
    """aalt (アプリの字形パネルなどが出す字形の候補) の欧字の候補を、置き換え (spec.LATIN_FEATURES) を
    BIZ UDP と同じにしたのに合わせる。before は、変える前の BIZ UD の置き換え。置き換え先が変わった
    候補は新しいものにし (BIZ UD の古い置き換え先は、ほかの機能からは使われず、等幅の字のまま残る。
    BIZ UDP の aalt にもある候補は残す)、BIZ UDP の aalt にあって BIZ UD に無い新しい置き換え先は
    足す。ほかの候補 (全角の字・丸数字など) と並びは BIZ UD のまま。変えた字の数を返す"""
    ensure_own_lookups(gsub_ud, "aalt", "mapping")
    singles = feature_subtables(gsub_ud, "aalt", "mapping")
    multiples = feature_subtables(gsub_ud, "aalt", "alternates")
    if not singles or not multiples:
        raise SystemExit("aalt: BIZ UD has no single and alternate substitutions to put the Latin into")
    after = {tag: single_mapping(gsub_ud, tag, latin) for tag in spec.LATIN_FEATURES}
    current, theirs = alternates(gsub_ud, "aalt", latin), alternates(gsub_udp, "aalt", latin)
    changed = 0
    for key in sorted(latin):
        old = current.get(key, [])
        new = list(old)
        for tag in spec.LATIN_FEATURES:
            was, now = before[tag].get(key), after[tag].get(key)
            if was == now:
                continue
            if was in new:
                # BIZ UDP でも候補なら残す (zero の Ø。BIZ UD の zero は、斜線の 0 に Ø を使う)
                position = new.index(was)
                if was in theirs.get(key, []):
                    position += 1
                else:
                    new.remove(was)
                if now is not None and now not in new:
                    new.insert(position, now)
            elif now is not None and now not in new and now in theirs.get(key, []):
                new.append(now)
        if new == old:
            continue
        for subtable in singles:
            subtable.mapping.pop(key, None)
        for subtable in multiples:
            subtable.alternates.pop(key, None)
        if len(new) == 1:
            singles[0].mapping[key] = new[0]
        elif new:
            multiples[0].alternates[key] = new
        changed += 1
    return changed


def license_text() -> str:
    """OFL.txt の全文 (著作権表示と使用許諾)"""
    return (ROOT / "OFL.txt").read_text(encoding="utf-8").replace("\r\n", "\n").strip()


def source_version(font: TTFont) -> str:
    """元のフォントの版 (name の 5 の "Version 1.06" の 1.06)"""
    match = re.match(r"Version (\d+\.\d+)", font["name"].getDebugName(5) or "")
    if not match:
        raise SystemExit(f"cannot read the version of {font['name'].getDebugName(6)}")
    return match.group(1)


def rename(font: TTFont, family: dict, weight: str, versions: tuple[str, str]) -> None:
    """versions は、元の BIZ UD と BIZ UDP の版"""
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
        5: (f"Version {spec.VERSION}; based on {family['source_name']} {versions[0]} and "
            f"{family['source_name'].replace('BIZ UD', 'BIZ UDP')} {versions[1]}", None),
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
    versions = (source_version(ud), source_version(udp))
    stats = merge_latin(ud, udp)
    symbols = latin_symbols.add(ud, udp)
    # BIZ UDP から持ってきた字 (読書 UD のグリフ名 → BIZ UDP のグリフ名)
    taken = {name: name for name in stats["glyphs"]} | {target: source for source, target in symbols["glyphs"].items()}
    cmap_udp = udp.getBestCmap()
    unhinted = {cmap_udp[code] for code in spec.UNHINTED if code in cmap_udp}
    hinted = hinting.add(ud, udp, taken, unhinted)
    spaced = spacing.add(ud)

    rename(ud, family, weight, versions)
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
          f"{stats['targets']} GSUB targets from BIZ UDP; {symbols['symbols']} symbols in Latin text; "
          f"hinting of BIZ UDP on {hinted['hinted']} glyphs (cvt +{hinted['cvt']}); "
          f"halt {spaced['halt']}, vhal {spaced['vhal']} glyphs")
    return out


def main() -> int:
    stale = fetch_sources.mismatches()
    if stale:
        print(f"sources/ does not match sources.json: {', '.join(stale)}; run scripts/fetch_sources.py",
              file=sys.stderr)
        return 1
    for family in spec.FAMILIES:
        for weight in spec.WEIGHTS:
            build(family, weight)
    return 0


if __name__ == "__main__":
    sys.exit(main())
