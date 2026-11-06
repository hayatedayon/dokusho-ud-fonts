# Dokusho UD Mincho and Dokusho UD Gothic

[![Build](https://github.com/hayatedayon/dokusho-ud-fonts/actions/workflows/build.yml/badge.svg)](https://github.com/hayatedayon/dokusho-ud-fonts/actions/workflows/build.yml)
[![Release](https://img.shields.io/github/v/release/hayatedayon/dokusho-ud-fonts?sort=semver&display_name=tag)](https://github.com/hayatedayon/dokusho-ud-fonts/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/hayatedayon/dokusho-ud-fonts/total)](https://github.com/hayatedayon/dokusho-ud-fonts/releases)
[![License: OFL-1.1](https://img.shields.io/badge/license-OFL--1.1-blue)](OFL.txt)
<br>
![Format](https://img.shields.io/badge/format-TrueType-555)
[![Built with fontTools](https://img.shields.io/badge/built%20with-fontTools%204.61-3776AB?logo=python&logoColor=white)](https://github.com/fonttools/fonttools)

[日本語](README.md)

Fonts for reading books. They are Morisawa's [BIZ UDMincho](https://github.com/googlefonts/morisawa-biz-ud-mincho) and [BIZ UDGothic](https://github.com/googlefonts/morisawa-biz-ud-gothic) with only the Latin letters taken from BIZ UDP, the proportional version of the same design, so that text is set the way printed Japanese books are, both horizontally and vertically.

| | Dokusho UD Mincho | Dokusho UD Gothic |
| --- | --- | --- |
| Japanese name | 読書 UD明朝 | 読書 UDゴシック |
| Weights | Regular, Bold | Regular, Bold |
| Files | `DokushoUDMincho-Regular.ttf` and so on | `DokushoUDGothic-Regular.ttf` and so on |

## Why

Horizontal Japanese books set kana, kanji and punctuation on a full-width grid (solid setting in the [Requirements for Japanese Text Layout](https://www.w3.org/TR/jlreq/)), and Latin letters in a proportional typeface. Neither BIZ UD nor BIZ UDP does that on its own.

| | Kana and punctuation | Latin letters |
| --- | --- | --- |
| BIZ UD | Full width, on the grid | Monospaced half width (`i` is as wide as `W`) |
| BIZ UDP | Their own widths (a full stop is 60% of full width, an opening bracket half) | Their own widths |
| **Dokusho UD** | **Full width, as BIZ UD** | **Their own widths, as BIZ UDP** |

The vertical forms (`vert`, `vrt2`) and vertical metrics of kana, kanji and punctuation, and the kanji of JIS levels 1 and 2, are those of BIZ UD.

## What changed

- The Latin letters (U+0020–007E, U+00C0–00D6, U+00D8–00F6, U+00F8–02FF, U+1E00–1EFF and U+FB00–FB06, including the extended Latin letters, the IPA symbols and ligatures such as ﬁ) and the superscript ⁴ take their outlines, widths and vertical metrics from BIZ UDP. In BIZ UD, pinyin letters such as `ǎ` and `ǐ` are full width and the IPA symbols half width, which leaves gaps inside words. × and ÷ are mapped as in BIZ UD, since Japanese text uses them full width, and take BIZ UDP's glyphs only in Latin text (see the symbols below).
- Their substitutions (`zero`, and `vrt2`, the Latin letters turned sideways in vertical text) and the ligatures that start from them (`ccmp` and `liga`: `fi` into `ﬁ`, the IPA `ə` with a combining accent into one glyph, and so on) follow BIZ UDP, and so do the alternates of the Latin letters in `aalt` (as shown in the glyph panels of applications). `hwid`, which turns the full-width forms (`Ａ`, `％`, `１` and so on) half width, still gives BIZ UD's half-width (monospaced) glyphs, which are kept as separate glyphs.
- Added in Dokusho UD: `hwid` also turns the proportional Latin letters, digits and symbols (`A`, `1`, `%` and so on) into BIZ UD's half-width glyphs (neither BIZ UD nor BIZ UDP does this). With `hwid`, two digits such as `12` fit exactly in one em in tate-chu-yoko (horizontal-in-vertical) text. The alternates (`aalt`) offer the half-width glyphs too, so glyph panels offer both the proportional `A` and the half-width `A` for `Ａ`.
- Added in Dokusho UD: fractions (`frac`). With `frac`, `1/2` and `10/25` become fractions with small numerators, a fraction slash and small denominators on the baseline (the whole number of `1 1/2` and the `/` of `and/or` stay as they are). With `⁄` (U+2044 FRACTION SLASH), browsers and other applications make the fraction without any feature being asked for. The numerators and denominators are based on the superscripts `¹ ² ³ ⁴` of the original fonts, and the space between the digits and the slash follows BIZ UDP's `½`, `¾` and so on. The `frac` of BIZ UD and BIZ UDP only raised `1`, `2` and `3`, and had no denominators.
- Added in Dokusho UD: superscript digits from 0 to 9, and the superscript signs `⁺`, `⁻`, `⁼`, `⁽` and `⁾` (the characters `⁰`, `⁵`–`⁹` and `⁺`–`⁾`, and `sups`, `numr` and `dnom`; for `10⁻³` and the like, and `sups` also raises `+ - − = ( )`). The original fonts have only `¹ ² ³ ⁴`. The new ones are the regular digits and signs reduced by the same ratio as `¹ ² ³ ⁴`, emboldened by the same amount and raised by the same height (reduced alone, their strokes would be thinner; the signs keep their height relative to the digits). They have no hinting.
- Added in Dokusho UD: subscript digits and signs `₀`–`₉`, `₊`, `₋`, `₌`, `₍` and `₎` (for `H₂O` and the like). They are the superscripts moved down until the bottom of `₍` meets the bottom of the Latin `p` (lower, they would leave the line). `subs` and `sinf` (`font-variant-position: sub` in CSS and so on) also turn digits and signs into them.
- Added in Dokusho UD: `palt`, which sets kana and punctuation proportionally (`font-feature-settings: "palt"` in CSS, Proportional Metrics in InDesign and so on), for headings and the like. It uses BIZ UDP's widths as they are (BIZ UDP's kana and punctuation are BIZ UD's glyphs with other widths). Body text stays solid as before.
- Added in Dokusho UD: `tnum` (`font-variant-numeric: tabular-nums` in CSS and so on). BIZ UDP's `1` is narrower than the other digits (1065 against 1393 in Mincho Regular), so that figures in tables and tables of contents do not line up. With `tnum`, `1` gets the same width, with the extra space split between both sides.
- Combining marks (the accents of U+0300–036F and the kana voiced and semi-voiced marks U+3099 and U+309A) sit on the letter before them. They have widths of their own in the original fonts. Without GPOS, HarfBuzz (Chromium, Firefox, Android and so on) zeroed the widths and placed them over the letter, but since `halt` and the other GPOS features came in 1.002 it no longer did, so the tilde of `q̃` came right of the `q` and the mark of `あ゙` after `あ`. They now have no width and attach with `mark` and `mkmk`, centered above or below Latin, Greek and Cyrillic letters (`моло́ко` and the like). The kana marks attach where `が` and `ぱ` have theirs, in vertical text too. `i` before an accent above becomes the dotless `ı`. Combinations with precomposed letters, such as `é` and `が`, do not change.
- Added in Dokusho UD: the two- and three-em dashes `⸺` and `⸻` used in novels (two and three `―` joined, also in vertical text), the non-breaking hyphen `‑`, the spaces U+2000–200A, U+202F and U+205F (such as the thin space U+2009), and the invisible characters (zero width space U+200B, word joiner U+2060, ZWJ, ZWNJ and BOM, which some environments otherwise draw as a box).
- The glyphs taken from BIZ UDP (the Latin letters, the symbols in Latin text and the like) carry BIZ UDP's hinting. BIZ UD and BIZ UDP have different control value tables and prep programs, so BIZ UDP's are appended to BIZ UD's, and the cvt numbers in the instructions are shifted to match. Small Latin text is drawn with the same instructions and values as in BIZ UDP (up to 1.003 the instructions were removed, so on Windows the Latin letters alone looked slightly faint and soft in small text). Seven thin horizontal bars have no hinting: the hyphen-minus, the low line, the macron, the en dash, the em dash, the overline and the minus sign. BIZ UDP's hinting erases their stroke at some sizes (in BIZ UDP itself too).
- `halt` and `vhal` are added (BIZ UD has neither), so that `text-spacing-trim` in browsers (on by default in Chromium) removes the extra space between consecutive brackets and punctuation, as printed books do.
- Symbols in Latin text (the quotation marks and apostrophe `‘ ’ “ ”`, the dash `—`, `†`, `©`, `€`, fractions such as `½` and `⅓`, the minus sign `−`, and others whose outline or width differs between BIZ UD and BIZ UDP) take BIZ UDP's glyphs, but only within Latin script (`locl`). BIZ UD's `’` is full width, so Alice’s would otherwise have a full-width gap. Format characters such as the soft hyphen (U+00AD) are not substituted (in 1.003 and 1.004 a soft hyphen in English text was not hidden and left a gap in the word). In documents in Japanese (`lang="ja"`) the other symbols, such as the dashes, keep BIZ UD's glyphs, English passages included (Japanese books use them as in `OK――`). The quotation marks and apostrophe `‘ ’ “ ”`, however, always take BIZ UDP's glyphs in horizontal text, in Japanese documents and in Japanese text too, so that `“Hello”` quoted in Japanese (`画面に“Hello”と`) and `It’s` have no full-width gaps and both quotation marks match (browsers put the `“` after Japanese into the Japanese run, where a font cannot tell it from the `“` of `“本当”`, which therefore takes BIZ UDP's glyphs as well). Vertical text keeps BIZ UD's. BIZ UD's `−` is half width with a shorter bar than `+` and `=`, so Latin text gets BIZ UDP's `−`, which matches `+`; Japanese text keeps BIZ UD's (the macOS Japanese input method enters this character as the full-width minus).
- The fonts are renamed Dokusho UD, as BIZ UDMincho and BIZ UDGothic are trademarks of Morisawa Inc., and the fixed pitch flag (`post.isFixedPitch`) is cleared.

[FONTLOG.txt](FONTLOG.txt) has the details.

## Inherited from the original fonts

The following is the same in BIZ UD and BIZ UDP, and Dokusho UD leaves it as it is.

- Greek and Cyrillic letters are full width, the width Japanese text uses them at (as in α波 or β版). BIZ UDP has no proportional forms of them either, so they stay full width in Latin text too: Greek or Russian text, or a π or Ω in an English sentence, is set with wide gaps.
- Few of the extended Latin letters are included (16 of the 208 in Latin Extended-B, 55 of the 96 IPA symbols, and 2 of the 256 in Latin Extended Additional, which Vietnamese uses). Browsers and other applications draw the missing ones (such as the IPA `ɪ`) with the next font in the list, so those letters alone change shape.

For such text, combine Dokusho UD with another Latin typeface.

## License

[SIL Open Font License 1.1](OFL.txt). Free for personal and commercial use, and free to bundle with apps and documents; the fonts may not be sold by themselves. The copyright notices of the original fonts are in OFL.txt.

Releases contain only the font files. The copyright notice and the full text of the license, which the OFL requires in each copy, are inside the fonts (the copyright and license fields of the name table), so the files alone are enough when you redistribute them.

These fonts are not affiliated with Morisawa. Please report problems as issues in this repository.

## Building

The fonts are built with [fontTools](https://github.com/fonttools/fonttools) from the Google Fonts files, pinned to the commit and SHA-256 in `scripts/sources.json`. `scripts/build.py` checks the SHA-256 of the sources too and stops if they do not match. The same sources always give the same files.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/fetch_sources.py   # the original fonts, in sources/
.venv/bin/python scripts/build.py           # Dokusho UD, in fonts/
.venv/bin/python scripts/check.py           # compare with the original fonts
```

`scripts/check.py` compares the built fonts with the original ones. It checks that the Latin letters, their substitutions, ligatures and alternates (`aalt`) match BIZ UDP, that `frac` replaces only the digits of fractions and spaces them from the slash as BIZ UDP's fractions do, that the new superscripts are as heavy and as high as `¹ ² ³ ⁴`, and a sample of Japanese characters and the half-width forms of `hwid` match BIZ UD in outline and width, that the glyphs drawn by FreeType with hinting are pixel for pixel BIZ UDP's for the Latin letters and the symbols in Latin text, and BIZ UD's for the sample of Japanese (it needs libfreetype, libfreetype6 on Debian and Ubuntu), that the symbols in Latin text become BIZ UDP's only within Latin script, and that the punctuation spacing (`halt`, `vhal` and `palt`), `tnum`, where the combining marks attach, the vertical features, the added characters and the names are right, and that no glyph reaches farther out of the line (`usWinAscent` and `usWinDescent`, outside which Windows GDI draws nothing) than in the original fonts. It also shapes text with HarfBuzz (which Chromium, Firefox, Android and others use) and checks that the characters whose glyphs were not changed are set as in BIZ UD in Japanese text, that the Latin letters and the symbols in Latin text are set as in BIZ UDP in English text, that BIZ UD's ligatures and variation sequences are set the same, that invisible characters are hidden, and that combining marks sit on the letter before them. This catches features that change the behavior of the original fonts (from 1.002 combining marks did not sit on their letters, and from 1.003 the soft hyphen was not hidden in English text). It needs libharfbuzz and the Unicode data files (libharfbuzz0b and unicode-data on Debian and Ubuntu). The glyphs that do (`‚` `„`, and the Greek letters with tonos in Mincho Bold, as in BIZ UD and BIZ UDP) are drawn into `dist/overflow.html` by `scripts/overflow_page.py`. CI builds and checks on every push, and makes a release for a `vX.Y.Z` tag, which is font version `X.YYZ` (`v1.0.0` is 1.000).

Releases cannot be changed afterwards (GitHub immutable releases): the files and the tag of a published release can be neither replaced nor deleted, so a version always downloads the same files. The SHA-256 of each file is shown on the release page and can be checked against the release attestation that GitHub makes.
