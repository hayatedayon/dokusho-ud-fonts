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
- Their substitutions (`frac`, `numr`, `sups`, `zero`, and `vrt2`, the Latin letters turned sideways in vertical text) and the ligatures that start from them (`ccmp` and `liga`: `fi` into `ﬁ`, the IPA `ə` with a combining accent into one glyph, and so on) follow BIZ UDP, and so do the alternates of the Latin letters in `aalt` (as shown in the glyph panels of applications).
- The glyphs taken from BIZ UDP (the Latin letters, the symbols in Latin text and the like) carry BIZ UDP's hinting. BIZ UD and BIZ UDP have different control value tables and prep programs, so BIZ UDP's are appended to BIZ UD's, and the cvt numbers in the instructions are shifted to match. Small Latin text is drawn with the same instructions and values as in BIZ UDP (up to 1.003 the instructions were removed, so on Windows the Latin letters alone looked slightly faint and soft in small text). Eight thin horizontal bars have no hinting: the hyphen-minus, the low line, the soft hyphen, the macron, the en dash, the em dash, the overline and the minus sign. BIZ UDP's hinting erases their stroke at some sizes (in BIZ UDP itself too).
- `halt` and `vhal` are added (BIZ UD has neither), so that `text-spacing-trim` in browsers (on by default in Chromium) removes the extra space between consecutive brackets and punctuation, as printed books do.
- Symbols in Latin text (the quotation marks and apostrophe `‘ ’ “ ”`, the dash `—`, `†`, `©`, `€`, fractions such as `½` and `⅓`, the minus sign `−`, and others whose outline or width differs between BIZ UD and BIZ UDP) take BIZ UDP's glyphs, but only within Latin script (`locl`). BIZ UD's `’` is full width, so Alice’s would otherwise have a full-width gap. In documents in Japanese (`lang="ja"`) they keep BIZ UD's glyphs, English passages included, and “ ” in Japanese text stay full width. BIZ UD's `−` is half width with a shorter bar than `+` and `=`, so Latin text gets BIZ UDP's `−`, which matches `+`; Japanese text keeps BIZ UD's (the macOS Japanese input method enters this character as the full-width minus).
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

`scripts/check.py` compares the built fonts with the original ones. It checks that the Latin letters, their substitutions, ligatures and alternates (`aalt`) match BIZ UDP and a sample of Japanese characters matches BIZ UD in outline and width, that the glyphs drawn by FreeType with hinting are pixel for pixel BIZ UDP's for the Latin letters and the symbols in Latin text, and BIZ UD's for the sample of Japanese (it needs libfreetype, libfreetype6 on Debian and Ubuntu), that the symbols in Latin text become BIZ UDP's only within Latin script, and that the punctuation spacing, the vertical features and the names are right. CI builds and checks on every push, and makes a release for a `vX.Y.Z` tag, which is font version `X.YYZ` (`v1.0.0` is 1.000).

Releases cannot be changed afterwards (GitHub immutable releases): the files and the tag of a published release can be neither replaced nor deleted, so a version always downloads the same files. The SHA-256 of each file is shown on the release page and can be checked against the release attestation that GitHub makes.
