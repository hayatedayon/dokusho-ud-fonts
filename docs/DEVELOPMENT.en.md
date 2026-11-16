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

The checks live in `scripts/checks/`, one module per subject. `scripts/check.py` is only the entry point, which holds the order in which the checks run.

| Module | What it checks |
| --- | --- |
| `charset`, `names` | the character map and glyph order, that Japanese characters are still BIZ UD's, the name table, version and OS/2 ranges, the license |
| `latin` | that the Latin letters and the symbols in Latin text match BIZ UDP (substitutions, ligatures, `aalt`, `hwid`) |
| `hinting` | the pixels drawn by FreeType (hinting) |
| `spacing`, `vertical` | punctuation spacing (`halt`, `palt`, `chws` and so on), vertical text (`vert`, `vpal`, vertical quotation marks) |
| `digits`, `additions`, `marks` | fractions, `tnum` and the colon, added characters, line metrics and overflow, combining marks and the kana voicing marks |
| `kerning`, `styles`, `smalltype` | `kern`, `ss01` to `ss03`, small type (ruby and small digits) |
| `shaping`, `references`, `woff2`, `native` | comparing how text is set by HarfBuzz, the references that do not depend on the original fonts, WOFF2, the tools for native environments |

`python scripts/check.py` with no arguments runs every check; CI and the release run it. `--list` shows the module names with the checks in them, and `--only kerning,vertical` runs only the checks of the listed modules (for use while working). The checks that shape text with HarfBuzz are spread over several modules: `shaping` holds only the comparisons of how the original fonts set text, and the checks of vertical text, spacing and so on are in their own modules.

The embedded version (`VERSION` in `scripts/spec.py`) is not advanced until that version is published. Unreleased changes are recorded under the next version in FONTLOG.

Releases cannot be changed afterwards (GitHub immutable releases): the files and the tag of a published release can be neither replaced nor deleted, so a version always downloads the same files. The SHA-256 of each file is shown on the release page and can be checked against the release attestation that GitHub makes.

## Reading and print proofs

```sh
.venv/bin/python scripts/specimen_page.py
.venv/bin/python scripts/proof_page.py
.venv/bin/python scripts/ruby_proof.py
python3 -m http.server 8000
```

Open `http://localhost:8000/dist/specimen.html` for feature controls, `dist/proof.html` for a fixed 32-em line measure and 1.75 line spacing, or `dist/small-type.html` for actual-size and enlarged FreeType raster comparisons of the small digits. `dist/ruby-trial.html` (from `scripts/ruby_proof.py`, about 40 seconds; see [docs/RUBY.md](RUBY.md), Japanese) lays out the ruby kana trial (`ss03`) as normal with hinting, normal without hinting and trial without hinting at 6–10 ppem, with and without honoring gasp, and with several emboldening amounts. The fixed proof offers 12/14/16px and 9–12pt, horizontal/vertical text and comparisons with BIZ UD/UDP. Print at 100%; vertical proofs use A4 landscape.

`.venv/bin/python scripts/versions_page.py` builds `dist/versions.html`, which compares each published version with the same text (it opens directly as a file; the fonts of each version are fetched from the releases). The README images are made in `docs/images/` by `scripts/readme_images.py`.

CI generates these pages and uploads a `DokushoUD-proof` artifact with the required fonts. Fonts are checked and uploaded first; proof generation or upload failures do not block a release. Serve its extracted root with an HTTP server. [docs/PROOFING.md](PROOFING.md) records the procedure and verification limits. Source-equivalence shaping checks disable the newly added `kern`; separate checks verify kerning, fixed-width exclusions, non-touching pairs and numeric feature interactions.

## Added glyphs, line spacing and native proofs

`scripts/kerning.py` defines family-specific kerning before periods and commas. Only proportional ASCII punctuation enters the right classes, in a separate lookup from letter pairs, preventing earlier Class Pair zero values from masking them. `check.py` covers the new pairs and accented variants against declared adjustments, HarfBuzz advances and at least 1% em of outline clearance. It also requires hhea/typo line gaps of 1024 and checks every other line metric and `fsSelection` against BIZ UD.

`extra_glyphs.py` translates the upper 土 of 圭 and combines it with 吉's lower 口 to make `𠮷`. It joins the outlines of `〳/〴` and `〵`, removing their joining edges, to make `〱 〲`. The two-cell definition in [Unicode §6.2](https://www.unicode.org/versions/Unicode17.0.0/core-spec/chapter-6/) and the locally available Noto Serif CJK JP metrics (1 em horizontally, 2 em vertically) inform the advances; no Noto outlines are used. Horizontal previews are scaled to half size inside one cell. `vert` and `vrt2` select the original stroke size with 2-em vertical advances, and `split_vertical_cells` then adds two last GSUB lookups (multiple substitutions, one for `vert` and one for `vrt2`, applied after every other lookup) that replace each such glyph (and the vertical forms of `⸺` `⸻`) with a glyph of the same outline, vertical advance and vertical origin, followed by blank glyphs. Engines decide the advance in different ways (HarfBuzz and DirectWrite use `vmtx`; CoreText and WebKitGTK use horizontal advances). DirectWrite applies `vert` only, uses the largest vertical advance of the glyphs of one character for the last glyph, and shifts glyphs left by half of the summed horizontal advances (`hmtx` and GPOS). CoreText applies `vrt2` only and sums `hmtx`. WebKitGTK sums `hmtx` and the horizontal advance of GPOS `curs` (which DirectWrite does not use). So the blank glyph of `vert` has vertical and horizontal advances of 0, with the horizontal 1 em added by GPOS `curs`, and the blank glyph of `vrt2` has a vertical advance of 0 and a horizontal advance of 1 em. Engines without multiple substitution stop at the first step. As with multi-em dashes, these dedicated vertical glyphs are checked against their two-cell vertical frame instead of a single horizontal line's clipping bounds. Added glyphs have no hinting. Supplementary `𠮷` enters format 12 cmaps that retain all existing assignments; Non-Plane 0 (bit 57) is already set in all four sources and is inherited unchanged.

```sh
.venv/bin/python scripts/additions_proof.py  # dist/additions.html and dist/additions/*.png
.venv/bin/python scripts/native_proof.py --prepare  # platform-independent input only
```

The added-glyph page saves actual-size and 4x FreeType rasters at 12/14/16px, plus 96px images, for all four faces. Compare joints, stroke size and two-cell advances with the original halves beside them.

`.github/workflows/native-proof.yml` is a manually run (`workflow_dispatch`) advisory CI workflow independent of build/release. CoreText on macOS 15 (`scripts/native/coretext.swift`) and DirectWrite on Windows 2025 (`scripts/native/directwrite.cpp`) shape the same 45 cases in four faces at 24px. Cases include Japanese/English horizontal/vertical text, punctuation kerning, accents, new characters, and the 17 symbols with `locl` enabled/disabled. Isolated punctuation pairs are checked against declared advances. Fonts load directly from files; fallback and missing glyphs fail validation. `DokushoUD-coretext` and `DokushoUD-directwrite` retain `dist/native/index.html`, PNGs, JSON glyph IDs/advances/positions, font SHA-256 and OS details. Compare artifacts with matching font hashes. Differences in the `locl-off` diagnostics inform a future cmap decision; equality with `locl` disabled is not required. With both CoreText and DirectWrite, `locl=0` leaves glyph IDs and advances unchanged, so it does not reproduce an environment without `locl`.

On each native OS, compile using the workflow commands, then run `scripts/native_proof.py --renderer <executable>`. On Linux, only `--prepare` runs.

## Trying a candidate before releasing

Releases cannot be undone, so unreleased fonts are tried in real environments before a version is cut. This section is step 1 of the release procedure in [AGENTS.md](../AGENTS.md) (Japanese) and is done before proofreading and before raising `VERSION`. CI artifacts are kept for one day by default; only a manual run can extend that.

1. Run `Build` manually in GitHub Actions (`gh workflow run build.yml --ref <branch> -f retention_days=14`) and set the retention to 14 days or so. The default is 1 day, and `push`, `pull_request` and the call from `release.yml` are unchanged. The upper limit is 90 days.
2. Download the `DokushoUD` (fonts) and `DokushoUD-proof` (proof pages) artifacts and read with the fonts in Hayate Reader or similar for a few days. The Reader procedure is in [PROOFING.md](PROOFING.md#hayate-reader-で確かめる) (Japanese). The fonts in the artifact still carry the already published version number (`VERSION` is raised in the release procedure). Do not publish or distribute candidate files; only the release files made from the tag are published.
3. Run `.github/workflows/native-proof.yml` manually and look at the CoreText and DirectWrite results (it is manual-only for now).
4. If there are no problems, continue with step 2 (proofreading) of the release procedure in [AGENTS.md](../AGENTS.md) (Japanese). If there are, fix them and start again from step 1.
