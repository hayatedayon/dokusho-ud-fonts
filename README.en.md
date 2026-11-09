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
| Files | `DokushoUDMincho-Regular.ttf`, `.woff2` and so on | `DokushoUDGothic-Regular.ttf`, `.woff2` and so on |

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
- Added in Dokusho UD: superscript digits from 0 to 9, and the superscript signs `⁺`, `⁻`, `⁼`, `⁽` and `⁾` (the characters `⁰`, `⁵`–`⁹` and `⁺`–`⁾`, and `sups`, `numr` and `dnom`; for `10⁻³` and the like, and `sups` also raises `+ - − = ( )`). The original fonts have only `¹ ² ³ ⁴`. The new ones are the regular digits and signs reduced by the same ratio as `¹ ² ³ ⁴`, emboldened by the same amount and raised by the same height (reduced alone, their strokes would be thinner; the signs keep their height relative to the digits). Generated digits have vertical-only hinting with shared top and bottom zones for each role, including a zero baseline for denominators. At small sizes these also absorb round-letter overshoots. The original ¹²³⁴ retain their hinting. Generated symbols remain unhinted.
- Added in Dokusho UD: subscript digits and signs `₀`–`₉`, `₊`, `₋`, `₌`, `₍` and `₎` (for `H₂O` and the like). They are the superscripts moved down until the bottom of `₍` meets the bottom of the Latin `p` (lower, they would leave the line). `subs` and `sinf` (`font-variant-position: sub` in CSS and so on) also turn digits and signs into them.
- Added in Dokusho UD: `palt`, which sets kana and punctuation proportionally (`font-feature-settings: "palt"` in CSS, Proportional Metrics in InDesign and so on), for headings and the like. It uses BIZ UDP's widths as they are (BIZ UDP's kana and punctuation are BIZ UD's glyphs with other widths). The vertical counterpart, `vpal`, matches glyph placement and vertical advances to BIZ UDP's vertical forms. Body text stays solid as before.
- Added in Dokusho UD: `tnum` (`font-variant-numeric: tabular-nums` in CSS and so on). BIZ UDP's `1` is narrower than the other digits (1065 against 1393 in Mincho Regular), so that figures in tables and tables of contents do not line up. With `tnum`, `1` gets the same width, with the extra space split between both sides.
- Added in Dokusho UD: a colon between digits is raised to the middle of the digits (`calt`, which browsers and the like apply by default). BIZ UDP's colon sits between the baseline and the x-height for text, so in `11:11` and `0213:2004` it looked low against the digits (BIZ UD's half-width colon is centered on them). So is a colon after Japanese (`時刻:`), which looked low next to kanji. A colon after a Latin word, as in `Note:`, and colons in vertical text do not change.
- Combining marks (the accents of U+0300–036F and the kana voiced and semi-voiced marks U+3099 and U+309A) sit on the letter before them. They have widths of their own in the original fonts. Without GPOS, HarfBuzz (Chromium, Firefox, Android and so on) zeroed the widths and placed them over the letter, but since `halt` and the other GPOS features came in 1.002 it no longer did, so the tilde of `q̃` came right of the `q` and the mark of `あ゙` after `あ`. They now have no width and attach with `mark` and `mkmk`, centered above or below Latin, full-width alphanumeric, Greek and Cyrillic letters (`моло́ко` and the like). The kana marks attach where `が` and `ぱ` have theirs, in vertical text too (where small kana move back so the mark does not collide with them). `i` before an accent above (even across a mark below) becomes the dotless `ı` (full-width `ｉ` likewise loses its dot). Combinations with precomposed letters, such as `é` and `が`, do not change.
- Added in Dokusho UD: the two- and three-em dashes `⸺` and `⸻` used in novels (two and three `―` joined, also in vertical text), the closing double prime quotation mark `〞` (U+301E, `〝` mirrored), the non-breaking hyphen `‑`, the spaces U+2000–200A, U+202F and U+205F (such as the thin space U+2009), and the invisible characters (zero width space U+200B, word joiner U+2060, ZWJ, ZWNJ and BOM, which some environments otherwise draw as a box).
- The glyphs taken from BIZ UDP (the Latin letters, the symbols in Latin text and the like) carry BIZ UDP's hinting. BIZ UD and BIZ UDP have different control value tables and prep programs, so BIZ UDP's are appended to BIZ UD's, and the cvt numbers in the instructions are shifted to match. Small Latin text is drawn with the same instructions and values as in BIZ UDP (up to 1.003 the instructions were removed, so on Windows the Latin letters alone looked slightly faint and soft in small text). Ten thin horizontal bars have their hinting removed, in BIZ UD's glyphs and `hwid` forms as well: the hyphen-minus, the low line, the soft hyphen, the macron, the combining macron, the en dash, the em dash, the horizontal bar (and `⸺` and `⸻` made from it), the overline and the minus sign. The hinting of the original fonts erases their stroke at some sizes (in BIZ UD and BIZ UDP themselves too).
- `halt` and `vhal` are added (BIZ UD has neither), so that `text-spacing-trim` in browsers (on by default in Chromium) removes the extra space between consecutive brackets and punctuation, as printed books do. `chws` and `vchw`, which trim only where punctuation is adjacent, are included too: where `text-spacing-trim` is unavailable, `font-feature-settings: "chws"` (`"vchw"` in vertical text) gives the same result (applying `halt` directly would also halve brackets that are not adjacent). Chromium's default setting does not change.
- Symbols in Latin text (the quotation marks and apostrophe `‘ ’ “ ”`, the dash `—`, `†`, `©`, `€`, fractions such as `½` and `⅓`, the minus sign `−`, and others whose outline or width differs between BIZ UD and BIZ UDP) take BIZ UDP's glyphs, but only within Latin script (`locl`). BIZ UD's `’` is full width, so Alice’s would otherwise have a full-width gap. The same holds for symbols set on their own (such as the hyphen `‐` that browsers add at the end of a line in English text, which up to 1.004 was BIZ UD's full-width glyph and left a gap after the word). Format characters such as the soft hyphen (U+00AD) are not substituted (in 1.003 and 1.004 a soft hyphen in English text was not hidden and left a gap in the word). In documents in Japanese (`lang="ja"`) symbols keep BIZ UD's glyphs, English passages included, except for those named next. The quotation marks and apostrophe `‘ ’ “ ”` always take BIZ UDP's glyphs, in Japanese documents and in Japanese text too, so that `“Hello”` quoted in Japanese (`画面に“Hello”と`) and `It’s` have no full-width gaps and both quotation marks match (browsers put the `“` after Japanese into the Japanese run, where a font cannot tell it from the `“` of `“本当”`, which therefore takes BIZ UDP's glyphs as well). Vertical text takes BIZ UDP's vertical forms of them too (half an em high; Chromium sets quotation marks upright in vertical text), and so do the other symbols wherever they take BIZ UDP's glyphs. `— − ¼ ½ ¾ ⅓ ⅔ ⅕ ° ‼ ⁇ ⁈ ⁉` also always take BIZ UDP's glyphs, in Japanese text and in vertical text as well. In BIZ UD, `—` (U+2014) is half width, so `——` is only 1 em long; `−` has a shorter bar than `+` and `=`; the fractions and `‼` are squeezed into half width; and `°` is full width, leaving a gap in `35°C`. `―` (U+2015) was full width already and does not change.
- Added conservative Latin kerning (`kern`) for frequent pairs such as `AV`, `WA`, `To`, `Te` and `LT`, including compatible accented forms (right-projecting carons on `Ť` and `Ľ` are excluded on the left). Full-width Japanese and Latin forms, `hwid` forms, tabular digits and substituted vertical forms are excluded. Latin text laid out horizontally and rotated within vertical text remains eligible for kerning. Kerning is enabled by default and can be disabled with `font-kerning: none`.
- Added `pnum` to restore proportional digits from `tnum` forms. If both are requested, `pnum` wins. It also works with `frac` and `zero`.
- In vertical text, `“ ”` take the forms of the double minutes `〝 〟` and `‘ ’` one stroke of them, in a full-width body; within English text `‘ ’` turn sideways with the words (JLReq treats `“ ” ‘ ’` as horizontal-only and `〝 〟` as the vertical quotes). The text itself does not change, so copying and searching still find `“ ” ‘ ’`, and horizontal text is unchanged. `ss01` restores the original quote forms in vertical text too.
- Added optional named stylistic sets: `ss01` (Japanese quotation marks) restores BIZ UD's `‘ ’ “ ”`; `ss02` (Latin symbols) selects BIZ UDP's symbols even in Japanese documents. Quotes are excluded from `ss02`, so both sets can be combined. When combined with `hwid` or `fwid`, `ss02` preserves the existing result of that width feature. `ss01` selects full-width Japanese quotes, including when combined with `fwid`. Both support horizontal and vertical text and are off by default.
- Added `ss03` (Ruby kana, trial), covering the 20 kana あめぬれゃゅょっがぱ and their katakana counterparts. It retains full-em frames and advances, slightly strengthens strokes and enlarges small kana by 12%. This is an opt-in comparison trial, not a complete ruby typeface. Default text and the existing `ruby` feature are unchanged. Trial glyphs have no hinting, so their small-size raster comparisons with the originals include differences in hinting as well as outlines. When combined with `palt` or `vpal`, trial glyphs retain the spacing adjustments and advances of their original kana.
- The fonts are renamed Dokusho UD, as BIZ UDMincho and BIZ UDGothic are trademarks of Morisawa Inc., and the fixed pitch flag (`post.isFixedPitch`) is cleared.

[FONTLOG.txt](FONTLOG.txt) has the details.

## Examples by use

These CSS examples show how to enable OpenType features. Install the font and set its family on your page. Feature support varies by application.

```css
@font-face {
  font-family: "Dokusho UD Mincho";
  src: url("DokushoUDMincho-Regular.woff2") format("woff2"),
       url("DokushoUDMincho-Regular.ttf") format("truetype");
}

body {
  font-family: "Dokusho UD Mincho", serif;
  /* Solid setting by default. Trims the space between adjacent brackets and punctuation (on by default in Chromium). */
  text-spacing-trim: normal;
  font-kerning: normal;
}

/* Characters BIZ UD lacks (Greek text, some IPA) come from the next family. */
.mixed {
  font-family: "Dokusho UD Mincho", "Noto Serif", serif;
}

h1, h2 {
  text-spacing-trim: space-all;
  font-feature-settings: "palt" 1, "chws" 0, "halt" 0; /* Horizontal headings */
}

.vertical-heading {
  writing-mode: vertical-rl;
  text-spacing-trim: space-all;
  font-feature-settings: "vpal" 1, "vchw" 0, "vhal" 0; /* Vertical headings */
}

table, .toc-pages {
  font-variant-numeric: tabular-nums; /* Tables and page numbers */
}

.tate-chu-yoko {
  text-combine-upright: all;
  font-feature-settings: "hwid" 1; /* e.g. 12 in vertical text */
}

.fraction {
  font-feature-settings: "frac" 1; /* 1/2 as a fraction */
}

.japanese-quotes { font-feature-settings: "ss01" 1; }
.latin-symbols { font-feature-settings: "ss02" 1; }
rt.ruby-trial { font-feature-settings: "ss03" 1; } /* 20 trial kana only */
.proportional-digits { font-variant-numeric: proportional-nums; }

sup {
  font-variant-position: super; /* superscript glyphs (sub for subscripts) */
}
```

Use `palt` and `vpal` for headings and similar text, rather than body copy, because they make kana and punctuation proportional. `tnum` aligns figures. `hwid` changes Latin letters, digits and symbols to half-width forms, which can fit text such as `12` into a tate-chu-yoko cell. `font-feature-settings` on a child element replaces its parent's, so list the features you combine together (`tnum` and the like are not replaced when written as `font-variant-numeric`). In InDesign, use the corresponding settings, such as Proportional Metrics for `palt` and `vpal`, and Tabular Figures for `tnum`.

`palt` is mutually exclusive with `chws` and `halt`; likewise `vpal` with `vchw` and `vhal`. Explicitly enabling both can double-trim punctuation and reduce a bracket's advance to zero. The heading examples turn off contextual trimming and automatic punctuation trimming.

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

`scripts/check.py` compares the built fonts with the original ones. It checks that the Latin letters, their substitutions, ligatures and alternates (`aalt`) match BIZ UDP, that `frac` replaces only the digits of fractions and spaces them from the slash as BIZ UDP's fractions do, that the new superscripts are as heavy and as high as `¹ ² ³ ⁴`, and a sample of Japanese characters and the half-width forms of `hwid` match BIZ UD in outline and width, that the glyphs drawn by FreeType with hinting are pixel for pixel BIZ UDP's for the Latin letters and the symbols in Latin text, and BIZ UD's for the sample of Japanese (it needs libfreetype, libfreetype6 on Debian and Ubuntu), that the symbols in Latin text become BIZ UDP's only within Latin script, and that the punctuation spacing (`halt`, `vhal`, `palt` and `vpal`), `tnum`, the colon between digits, where the combining marks attach, the vertical features, the added characters and the names are right, and that no glyph reaches farther out of the line (`usWinAscent` and `usWinDescent`, outside which Windows GDI draws nothing) than in the original fonts. It also shapes text with HarfBuzz (which Chromium, Firefox, Android and others use) and checks that the characters whose glyphs were not changed are set as in BIZ UD in Japanese text, that the Latin letters and the symbols in Latin text are set as in BIZ UDP in English text, that BIZ UD's ligatures and variation sequences are set the same, that invisible characters are hidden, and that combining marks sit on the letter before them. This catches features that change the behavior of the original fonts (from 1.002 combining marks did not sit on their letters, and from 1.003 the soft hyphen was not hidden in English text). It needs libharfbuzz and the Unicode data files (libharfbuzz0b and unicode-data on Debian and Ubuntu). The glyphs that do (`‚` `„`, and the Greek letters with tonos in Mincho Bold, as in BIZ UD and BIZ UDP) are drawn into `dist/overflow.html` by `scripts/overflow_page.py`. CI builds and checks on every push, and makes a release for a `vX.Y.Z` tag, which is font version `X.YYZ` (`v1.0.0` is 1.000).

The embedded version (`VERSION` in `scripts/spec.py`) is not advanced until that version is published. Unreleased changes are recorded under the next version in FONTLOG.

Releases cannot be changed afterwards (GitHub immutable releases): the files and the tag of a published release can be neither replaced nor deleted, so a version always downloads the same files. The SHA-256 of each file is shown on the release page and can be checked against the release attestation that GitHub makes.

## Reading and print proofs

```sh
.venv/bin/python scripts/specimen_page.py
.venv/bin/python scripts/proof_page.py
python3 -m http.server 8000
```

Open `http://localhost:8000/dist/specimen.html` for feature controls, `dist/proof.html` for a fixed 32-em line measure and 1.75 line spacing, or `dist/small-type.html` for actual-size and enlarged FreeType raster comparisons. The fixed proof offers 12/14/16px and 9–12pt, horizontal/vertical text and comparisons with BIZ UD/UDP. Print at 100%; vertical proofs use A4 landscape.

CI generates these pages and uploads a `DokushoUD-proof` artifact with the required fonts. Fonts are checked and uploaded first; proof generation or upload failures do not block a release. Serve its extracted root with an HTTP server. [docs/PROOFING.md](docs/PROOFING.md) records the procedure and verification limits. Source-equivalence shaping checks disable the newly added `kern`; separate checks verify kerning, fixed-width exclusions, non-touching pairs and numeric feature interactions.
