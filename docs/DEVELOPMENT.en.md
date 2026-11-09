# Building and checking Dokusho UD

How to build the fonts, run the checks and make the proofs.

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

`.venv/bin/python scripts/versions_page.py` builds `dist/versions.html`, which compares each published version with the same text (it opens directly as a file; the fonts of each version are fetched from the releases). The README images are made in `docs/images/` by `scripts/readme_images.py`.

CI generates these pages and uploads a `DokushoUD-proof` artifact with the required fonts. Fonts are checked and uploaded first; proof generation or upload failures do not block a release. Serve its extracted root with an HTTP server. [docs/PROOFING.md](PROOFING.md) records the procedure and verification limits. Source-equivalence shaping checks disable the newly added `kern`; separate checks verify kerning, fixed-width exclusions, non-touching pairs and numeric feature interactions.
