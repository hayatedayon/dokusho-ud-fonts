"""fonts/ の読書 UD を、元の BIZ UD・BIZ UDP と突き合わせて確かめる。

build.py とは別の書き方で、できたものだけを見る。1 つでも合わなければ 1 で終わる。
検査は scripts/checks/ に、対象ごとのモジュールで置いてある。このファイルは、どの検査をどの順に
実行するかだけを持つ。

    python scripts/check.py                 全検査
    python scripts/check.py --list          検査の名前 (モジュール) と、その中の検査の一覧
    python scripts/check.py --only kerning,vertical   指定したモジュールの検査だけ
"""

import argparse
import inspect
import sys

import spec
from checks import (additions, charset, digits, hinting, kerning, latin, marks, names, native, references,
                    shaping, smalltype, spacing, styles, vertical, woff2)
from checks.common import FontContext, problems

# 実行の順序。引数の無い検査 (フォントに依らない) を先に、続いて書体 × 太さごとに、上から順に実行する。
# 検査が見つけた問題は、この順に報告する。
STEPS = [
    kerning.check_kern_lookup_precedence,
    kerning.check_outline_distance,
    names.check_license,
    native.check_native_proof_tools,
    # 書体 × 太さごと
    charset.check_cmap,
    latin.check_latin_letters,
    charset.check_japanese_kept,
    latin.check_latin_substitutions,
    vertical.check_vertical_tables,
    names.check_name_table,
    latin.check_latin_symbols,
    hinting.check_hinting,
    spacing.check_spacing,
    digits.check_fractions,
    additions.check_extra,
    additions.check_line_metrics,
    additions.check_japanese_additions,
    spacing.check_proportional,
    vertical.check_proportional_vertical,
    digits.check_tabular,
    marks.check_marks,
    additions.check_overflow,
    # HarfBuzz で組んで比べる
    shaping.check_kept_characters,
    shaping.check_quotes_always_udp,
    shaping.check_ligatures_and_variations,
    shaping.check_latin_text,
    vertical.check_vertical_latin,
    shaping.check_invisible,
    spacing.check_shaped_proportional,
    digits.check_zero_fractions,
    marks.check_shaped_marks,
    marks.check_kana_marks,
    spacing.check_contextual_spacing,
    digits.check_colon,
    # 新しい組版機能
    kerning.check_kern_pairs,
    references.check_recorded_references,
    styles.check_style_widths,
    vertical.check_vertical_minutes,
    hinting.check_generated_mark_hints,
    kerning.check_kern_behavior,
    digits.check_numeric_widths,
    styles.check_style_copies_all,
    spacing.check_double_trimming,
    styles.check_style_quotes,
    styles.check_style_labels,
    smalltype.check_ruby,
    smalltype.check_small_digits,
    woff2.check_woff2,
]


def group(step) -> str:
    """検査の属するグループ (モジュールの名前)"""
    return step.__module__.rsplit(".", 1)[-1]


def per_font(step) -> bool:
    return len(inspect.signature(step).parameters) > 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="fonts/ の読書 UD を元の BIZ UD・BIZ UDP と突き合わせて確かめる")
    parser.add_argument("--only", metavar="NAME[,NAME...]", help="指定したグループの検査だけ実行する (--list で名前を見る)")
    parser.add_argument("--list", action="store_true", help="検査のグループと、その中の検査を実行順に出して終わる")
    args = parser.parse_args(argv)
    groups = list(dict.fromkeys(group(step) for step in sorted(STEPS, key=group)))
    if args.list:
        for name in groups:
            print(f"{name}: " + ", ".join(step.__name__ for step in STEPS if group(step) == name))
        return 0
    steps = STEPS
    if args.only is not None:
        chosen = [name.strip() for name in args.only.split(",") if name.strip()]
        unknown = [name for name in chosen if name not in groups]
        if unknown or not chosen:
            parser.error(f"unknown check group {', '.join(unknown) or '(empty)'}; choose from: {', '.join(groups)}")
        steps = [step for step in STEPS if group(step) in chosen]
    for step in steps:
        if not per_font(step):
            step()
    for family in spec.FAMILIES:
        for weight in spec.WEIGHTS:
            ctx = FontContext(family, weight)
            try:
                for step in steps:
                    if per_font(step):
                        step(ctx)
            finally:
                ctx.close()
    if problems:
        print("\n".join(problems[:50]))
        print(f"{len(problems)} problem(s)")
        return 1
    print(f"ok: {len(spec.FAMILIES) * len(spec.WEIGHTS)} fonts" + (f" (only {args.only})" if args.only else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
