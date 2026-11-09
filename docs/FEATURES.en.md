# Dokusho UD features and changes

The full list of what differs from BIZ UD and BIZ UDP, with examples of the features. See the [README](../README.en.md) for an overview.

## What changed

- Set `hhea.lineGap` and `OS/2.sTypoLineGap` to 1024 (0.5 em), so `line-height: normal` is 1.5 em. Ascenders, descenders, the Windows clipping bounds and `USE_TYPO_METRICS` stay as in the sources. Existing documents using `line-height: normal` may change line spacing and pagination. Applications interpret `normal` differently; specify `line-height: 1.5` on web pages that need consistent spacing.
- Added `𠮷` (U+20BB7), made from the upper 土 of 圭 and the lower 口 of 吉, preserving stroke sizes, the full-width frame and 吉's vertical metrics. `〱 〲` (U+3031/3032) join the edges of `〳/〴` and `〵` into single vertical repeat glyphs. Following Unicode, they have a 2-em vertical advance and 1-em horizontal width; horizontal text uses a compact one-cell preview. These additions have no hinting. Existing glyphs and `aalt` alternatives are unchanged.
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
- Added conservative Latin kerning (`kern`) for frequent pairs such as `AV`, `WA`, `To`, `Te` and `LT`, and `T.`, `P,`, `r.` and others, including compatible accented forms (right-projecting carons on `Ť` and `Ľ` are excluded on the left). Full-width Japanese and Latin forms, `hwid` forms, tabular digits and substituted vertical forms are excluded. Latin text laid out horizontally and rotated within vertical text remains eligible for kerning. Kerning is enabled by default and can be disabled with `font-kerning: none`.
- Added `pnum` to restore proportional digits from `tnum` forms. If both are requested, `pnum` wins. It also works with `frac` and `zero`.
- In vertical text, `“ ”` take the forms of the double minutes `〝 〟` and `‘ ’` one stroke of them, in a full-width body; within English text `‘ ’` turn sideways with the words (JLReq treats `“ ” ‘ ’` as horizontal-only and `〝 〟` as the vertical quotes). The text itself does not change, so copying and searching still find `“ ” ‘ ’`, and horizontal text is unchanged. `ss01` restores the original quote forms in vertical text too.
- Added optional named stylistic sets: `ss01` (Japanese quotation marks) restores BIZ UD's `‘ ’ “ ”`; `ss02` (Latin symbols) selects BIZ UDP's symbols even in Japanese documents. Quotes are excluded from `ss02`, so both sets can be combined. When combined with `hwid` or `fwid`, `ss02` preserves the existing result of that width feature. `ss01` selects full-width Japanese quotes, including when combined with `fwid`. Both support horizontal and vertical text and are off by default.
- Added `ss03` (Ruby kana, trial), covering the 20 kana あめぬれゃゅょっがぱ and their katakana counterparts. It retains full-em frames and advances, slightly strengthens strokes and enlarges small kana by 12%. This is an opt-in comparison trial, not a complete ruby typeface. Default text and the existing `ruby` feature are unchanged. Trial glyphs have no hinting, so their small-size raster comparisons with the originals include differences in hinting as well as outlines. When combined with `palt` or `vpal`, trial glyphs retain the spacing adjustments and advances of their original kana.
- The fonts are renamed Dokusho UD, as BIZ UDMincho and BIZ UDGothic are trademarks of Morisawa Inc., and the fixed pitch flag (`post.isFixedPitch`) is cleared.

[FONTLOG.txt](../FONTLOG.txt) has the details.

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
