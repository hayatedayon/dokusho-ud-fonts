# Dokusho UD Mincho and Dokusho UD Gothic

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

The vertical forms (`vert`, `vrt2`), vertical metrics and the kanji of JIS levels 1 and 2 are those of BIZ UD.

## What changed

- The Latin letters (U+0020–007E, U+00C0–00D6, U+00D8–00F6, U+00F8–017F) take their outlines, widths and vertical metrics from BIZ UDP. × and ÷ stay as in BIZ UD, since Japanese text uses them full width.
- Their substitutions (`frac`, `numr`, `sups`, `zero`, and `vrt2`, the Latin letters turned sideways in vertical text) follow BIZ UDP.
- The hinting instructions of the glyphs taken from BIZ UDP are removed, because BIZ UD and BIZ UDP have different control value tables.
- The fonts are renamed Dokusho UD, as BIZ UDMincho and BIZ UDGothic are trademarks of Morisawa Inc., and the fixed pitch flag (`post.isFixedPitch`) is cleared.

[FONTLOG.txt](FONTLOG.txt) has the details.

## License

[SIL Open Font License 1.1](OFL.txt). Free for personal and commercial use, and free to bundle with apps and documents; the fonts may not be sold by themselves. The copyright notices of the original fonts are in OFL.txt.

Releases contain only the font files. The copyright notice and the full text of the license, which the OFL requires in each copy, are inside the fonts (the copyright and license fields of the name table), so the files alone are enough when you redistribute them.

These fonts are not affiliated with Morisawa. Please report problems as issues in this repository.

## Building

The fonts are built with [fontTools](https://github.com/fonttools/fonttools) from the Google Fonts files, pinned to the commit and SHA-256 in `scripts/sources.json`. The same sources always give the same files.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/fetch_sources.py   # the original fonts, in sources/
.venv/bin/python scripts/build.py           # Dokusho UD, in fonts/
.venv/bin/python scripts/check.py           # compare with the original fonts
```

`scripts/check.py` checks that the Latin letters match BIZ UDP and the Japanese characters match BIZ UD in outline and width, and that the vertical features and the names are right. CI builds and checks on every push, and makes a release for a `vX.Y.Z` tag, which is font version `X.YYZ` (`v1.0.0` is 1.000).

Releases cannot be changed afterwards (GitHub immutable releases): the files and the tag of a published release can be neither replaced nor deleted, so a version always downloads the same files. The SHA-256 of each file is shown on the release page and can be checked against the release attestation that GitHub makes.
