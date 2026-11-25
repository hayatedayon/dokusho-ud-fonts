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

## Diagonal hinting

The build adds instructions that move the edges of diagonal strokes for the glyphs listed in `spec.DIAGONAL_GLYPHS`, keeping their original hint programs. Each glyph's plan in `diagonal_plans.json` places the added instructions before or after the final `IUP`. They either interpolate between two points moved by the original program (`IP`) or copy one point's displacement (`SHP`). The checks match the added instructions against the list and plans and use FreeType to verify x positions, the number of horizontal groups aligned to pixel boundaries, and the vertical thickness of diagonal strokes. For the pixel comparison against the source fonts, the checks strip the added instructions from the listed glyphs and render the other glyphs as built.

## Reading and print proofs

```sh
.venv/bin/python scripts/specimen_page.py
.venv/bin/python scripts/proof_page.py
.venv/bin/python scripts/ruby_proof.py
python3 -m http.server 8000
```

Open `http://localhost:8000/dist/specimen.html` for feature controls, `dist/proof.html` for a fixed 32-em line measure and 1.75 line spacing, or `dist/small-type.html` for actual-size and enlarged FreeType raster comparisons of the small digits. `dist/ruby-trial.html` (from `scripts/ruby_proof.py`, about 40 seconds; see [docs/RUBY.md](RUBY.md), Japanese) lays out the ruby kana trial (`ss03`) as normal with hinting, normal without hinting, trial without hinting and trial with hinting at 6–10 ppem, with and without honoring gasp, and with several emboldening amounts. The fixed proof offers 12/14/16px and 9–12pt, horizontal/vertical text and comparisons with BIZ UD/UDP. Print at 100%; vertical proofs use A4 landscape.

`.venv/bin/python scripts/versions_page.py` builds `dist/versions.html`, which compares each published version with the same text (it opens directly as a file; the fonts of each version are fetched from the releases). The README images are made in `docs/images/` by `scripts/readme_images.py`.

CI generates these pages and uploads a `DokushoUD-proof` artifact with the required fonts. Fonts are checked and uploaded first; proof generation or upload failures do not block a release. Serve its extracted root with an HTTP server. [docs/PROOFING.md](PROOFING.md) records the procedure and verification limits. Source-equivalence shaping checks disable the newly added `kern`; separate checks verify kerning, fixed-width exclusions, non-touching pairs and numeric feature interactions.

## Added glyphs, line spacing and native proofs

`scripts/kerning.py` defines family-specific kerning before periods and commas. Only proportional ASCII punctuation enters the right classes, in a separate lookup from letter pairs, preventing earlier Class Pair zero values from masking them. `check.py` covers the new pairs and accented variants against declared adjustments, HarfBuzz advances and at least 1% em of outline clearance. It also requires hhea/typo line gaps of 1024 and checks every other line metric and `fsSelection` against BIZ UD.

`extra_glyphs.py` translates the upper 土 of 圭 and combines it with 吉's lower 口 to make `𠮷`. It joins the outlines of `〳/〴` and `〵`, removing their joining edges, to make `〱 〲`. The two-cell definition in [Unicode §6.2](https://www.unicode.org/versions/Unicode17.0.0/core-spec/chapter-6/) and the locally available Noto Serif CJK JP metrics (1 em horizontally, 2 em vertically) inform the advances; no Noto outlines are used.

Horizontal previews are scaled to half size inside one cell. `vert` and `vrt2` select the original stroke size with 2-em vertical advances, and `split_vertical_cells` then adds two last GSUB lookups (multiple substitutions, one for `vert` and one for `vrt2`, applied after every other lookup) that replace each such glyph (and the vertical forms of `⸺` `⸻`) with a glyph of the same outline, vertical advance and vertical origin, followed by blank glyphs. Engines decide the advance in different ways (HarfBuzz and DirectWrite use `vmtx`; CoreText and WebKitGTK use horizontal advances).

DirectWrite applies `vert` only, uses the largest vertical advance of the glyphs of one character for the last glyph, and shifts glyphs left by half of the summed horizontal advances (`hmtx` and GPOS). CoreText applies `vrt2` only and sums `hmtx`. WebKitGTK sums `hmtx` and the horizontal advance of GPOS `curs` (which DirectWrite does not use). So the blank glyph of `vert` has vertical and horizontal advances of 0, with the horizontal 1 em added by GPOS `curs`, and the blank glyph of `vrt2` has a vertical advance of 0 and a horizontal advance of 1 em. Engines without multiple substitution stop at the first step.

As with multi-em dashes, these dedicated vertical glyphs are checked against their two-cell vertical frame instead of a single horizontal line's clipping bounds. Added glyphs have no hinting. Supplementary `𠮷` enters format 12 cmaps that retain all existing assignments; Non-Plane 0 (bit 57) is already set in all four sources and is inherited unchanged.

```sh
.venv/bin/python scripts/additions_proof.py  # dist/additions.html and dist/additions/*.png
.venv/bin/python scripts/native_proof.py --prepare  # platform-independent input only
```

The added-glyph page saves actual-size and 4x FreeType rasters at 12/14/16px, plus 96px images, for all four faces. Compare joints, stroke size and two-cell advances with the original halves beside them.

`.github/workflows/native-proof.yml` is an auxiliary CI workflow independent of build, release and pages (`release.yml` calls only `build.yml` and does not depend on it). CoreText on macOS (`scripts/native/coretext.swift`) and DirectWrite on Windows (`scripts/native/directwrite.cpp`) shape the same 53 cases in four faces at 24px. Cases include Japanese/English horizontal/vertical text, punctuation kerning, accents, new characters, the 17 symbols with `locl` enabled/disabled, and `ss03` enabled/disabled (the 194 kana, horizontal and vertical). Fonts load directly from files. The `DokushoUD-coretext` and `DokushoUD-directwrite` artifacts retain `dist/native/index.html`, PNGs, JSON glyph IDs/advances/positions, `checks-<engine>.json` (check results), font SHA-256 and OS details (`platform.txt`). Compare artifacts with matching font hashes. Differences in the `locl-off` diagnostics inform a future cmap decision; equality with `locl` disabled is not required. With both CoreText and DirectWrite, `locl=0` leaves glyph IDs and advances unchanged, so it does not reproduce an environment without `locl`.

| Run | Fonts checked | OS | When a check fails |
| --- | --- | --- | --- |
| Manual (`workflow_dispatch`) | By default the fonts built from the ref. With input `fonts=release` (and `release_tag`, empty = latest), a published release's TTFs | Pinned (`macos-15`, `windows-2025`) | Advisory (the job fails, the run succeeds) |
| Scheduled (`schedule`; Sundays 19:17 UTC = Mondays 04:17 JST; runs only on `main`) | TTFs of the latest published release (`gh release download --pattern '*.ttf'`) | `macos-latest`, `windows-latest` (to notice breakage on new OS versions early) | The job and the run fail, and GitHub emails the failure |

The scheduled run answers "does the published font still shape correctly on today's OS", so it uses the release fonts instead of building `main`. The OS version and the font source (release tag or commit) are kept in the job log and in `platform.txt` of the artifact. `permissions` stays `contents: read`; no issue is created and nothing external is notified.

Checks that decide pass or fail (`scripts/native_proof.py`; expectations come from the font's `hmtx`, `cmap`, GSUB and GPOS):

- The vertical advances of `〱 〲 ⸺ ⸻` are 2, 2, 2 and 3 em.
- The 17 symbols (`ALWAYS_UDP`) have the glyph IDs and widths of the post-`locl` (BIZ UDP) glyphs in horizontal text.
- The width of the kerning line (`T. V, W. Y, P. F, r. y, v. w,`) and of isolated punctuation pairs equals the effective GPOS values. Environment differences are explicit: CoreText removes the kerning with `kern=0`, DirectWrite does not (same width as `kern`).
- `𠮷 〱 〲` and the characters of the `ja` sentence have the `cmap` glyph IDs and `hmtx` advances.
- The vertical glyph sequences of `〱 〲 ⸺ ⸻` equal `vrt2` for CoreText and `vert` (`〱 〲`) plus the cmap glyph (`⸺ ⸻`) for DirectWrite.
- With `ss03`, the 194 kana (horizontal and vertical) are set with the glyphs of the font's `ss03` substitution (vertically, after `vrt2` for CoreText and after `vert` for DirectWrite). The expected glyphs come from the font's `ss03` substitution, so when the scheduled run checks a published font, it checks that version's `ss03` coverage. Horizontal advances equal those of the original kana, and the same strings with `ss03=0` keep the normal glyphs.
- Every character of the test sentences is in this font, with no fallback to another font and no missing glyph (glyph ID 0).

The checks run after the gallery (images and JSON) is written and collect every failure before failing. A failure shows the sentence, face, character (code point), expected and actual values in the job log (`::error::` annotations and a final count) and in `checks-<engine>.json` of the artifact. Known environment differences, such as vertical `ALWAYS_UDP` (DirectWrite rotates the horizontal half-width quotes), are not checks and are recorded in [PROOFING.md](PROOFING.md) (Japanese).

GitHub disables scheduled workflows of public repositories after 60 days without repository activity such as commits (per GitHub's documentation). When that happens, runs simply stop coming; nothing notifies you. The only way to notice is to look at the date of the last scheduled run in the Actions tab. No countermeasure has been added.

Safari and Microsoft Edge are measured by the `browser-proof` job of the same workflow (advisory; it does not fail the scheduled run either). `scripts/browser_proof.py` speaks W3C WebDriver (HTTP + JSON) with the standard library only and drives the runner's `safaridriver` (needs `sudo safaridriver --enable`) and `msedgedriver` (headless). It serves a test page from 127.0.0.1 and measures, with `Range.getBoundingClientRect()` and the height of a shrink-wrapped box, the vertical and horizontal advances, the 17 symbols, kerning and the `𠮷` coverage. The `DokushoUD-safari` and `DokushoUD-edge` artifacts keep the measured values (`result.json`, `summary.json`), a screenshot and the WebDriver log. Locally, `scripts/browser_proof.py --validate` checks the tool without a browser, and `--serve` only serves the page (to open by hand or in WebKitGTK).

On each native OS, compile using the workflow commands, then run `scripts/native_proof.py --renderer <executable>`. On Linux, only `--prepare` runs.

## Trying a candidate before releasing

Releases cannot be undone, so unreleased fonts are tried in real environments before a version is cut. This section is step 1 of the release procedure in [AGENTS.md](../AGENTS.md) (Japanese) and is done before proofreading and before raising `VERSION`. CI artifacts are kept for one day by default; only a manual run can extend that.

1. Run `Build` manually in GitHub Actions (`gh workflow run build.yml --ref <branch> -f retention_days=14`) and set the retention to 14 days or so. The default is 1 day, and `push`, `pull_request` and the call from `release.yml` are unchanged. The upper limit is 90 days.
2. Download the `DokushoUD` (fonts and SBOM) and `DokushoUD-proof` (proof pages) artifacts and read with the fonts in Hayate Reader or similar for a few days. The Reader procedure is in [PROOFING.md](PROOFING.md#hayate-reader-で確かめる) (Japanese). The fonts in the artifact still carry the already published version number (`VERSION` is raised in the release procedure). Do not publish or distribute candidate files; only the release files made from the tag are published.
3. Run `.github/workflows/native-proof.yml` manually and look at the CoreText and DirectWrite results (checks and gallery) and the Safari and Edge measurements. A scheduled run also exists, but it runs only on `main` and checks the published fonts, so a candidate is checked by a manual run.
4. If there are no problems, continue with step 2 (proofreading) of the release procedure in [AGENTS.md](../AGENTS.md) (Japanese). If there are, fix them and start again from step 1.

## Updating dependencies

The dependencies are the two packages in `requirements.txt` (`fonttools` and `brotli`) and the GitHub Actions the workflows use (pinned by commit SHA, with the version in a comment). Once a month Dependabot (`.github/dependabot.yml`) opens update pull requests: one for `pip` (`fonttools` and `brotli` together) and one for the Actions. Only versions at least 7 days old are considered (security updates are not delayed by this wait). The interval is monthly because the fonts reach users only through releases, so taking an update sooner delivers nothing sooner. `fonttools` 4.68 requires `brotli` 1.2.1 or later, so the two move together.

An update of `fonttools` can change the bytes of the fonts, so always compare before and after before taking it.

- **On every pull request**, `.github/workflows/font-diff.yml` builds the base (`main`) and the change from their own `requirements.txt` with the same `SOURCE_DATE_EPOCH` and compares the four TTFs and WOFF2s. Differences are listed per table in the job summary (`scripts/compare_fonts.py`; it also tells apart a table whose contents are the same but whose bytes differ, that is, only ordering or compression, from one whose contents changed). When a pull request changes nothing but `requirements.txt` and `.github` (a dependency update) and the fonts change, **the job fails**: the next release's fonts would change, so a person reads the difference and decides. For a pull request that changes the build scripts (a font improvement) a difference is intended, so it only produces a notice and the summary and does not fail. The workflow has `contents: read` permission only. It can also be run by hand (`gh workflow run font-diff.yml --ref <branch>`, `-f base=<earlier ref>`).
- **Locally**, `.venv/bin/python scripts/deps_update.py` looks up the latest versions on PyPI, makes a venv and a copy of the repository for the current and the latest versions in a temporary folder, builds both with the same timestamp and compares them, runs the full check (`scripts/check.py`) with the latest versions, and prints a proposed `requirements.txt`. `--no-check` skips the full check; `--write` rewrites `requirements.txt` only when the fonts are identical and the checks pass. It does not touch the repository's `.venv`, `fonts/` or `dist/`.

To take an update:

1. Read the comparison. If the fonts are identical, go to step 2. If they changed, read which tables differ and how. A difference that changes the font's meaning (outlines, metrics, the contents of GSUB or GPOS) is not taken; the owner decides. A difference only in WOFF2 compression or ordering can be taken once it is recorded.
2. Read the packages' changelogs ([fontTools NEWS](https://github.com/fonttools/fonttools/blob/main/NEWS.rst)) for changes to what this repository uses (assembling `glyf`, GSUB and GPOS through `feaLib` and `otTables`, WOFF2 compression, `subset`, `ttLib`).
3. In a venv with the latest versions, confirm the full check, the proof pages (`specimen_page.py`, `proof_page.py`, `ruby_proof.py`, `additions_proof.py`, `overflow_page.py`) and `native_proof.py --prepare` still work.
4. For Actions, in Dependabot's pull request confirm that the SHA and the version in the comment changed together, and read the release notes for changes to inputs or default behavior.
5. Update your local `.venv` by overwriting it with `.venv/bin/pip install -r requirements.txt` (no need to recreate it; CI builds from `requirements.txt` every time).

FreeType, HarfBuzz and unicode-data (external libraries the checks use, installed with apt in CI) are not pinned. At each update, look at the versions printed by the `dpkg-query` step in CI.

## Secret scanning

`secrets.yml` runs betterleaks v1.10.0 on pushes, pull requests and weekly. It checks the working tree and the push/PR commit range; scheduled and manual runs check all fetched history. Findings fail the job and values are redacted. Live validation against external APIs is disabled.

On Linux x86-64, use an empty work folder outside the repository:

```sh
python3 scripts/install_supply_chain_tools.py betterleaks \
  --bin-dir /path/to/work/bin --download-dir /path/to/work/downloads
export PATH="/path/to/work/bin:$PATH"
python3 scripts/scan_secrets.py
# Fetch every remote branch before auditing every local and remote ref.
git fetch origin '+refs/heads/*:refs/remotes/origin/*' --no-tags
python3 scripts/scan_secrets.py --all-history
```

The installer downloads only official GitHub release assets and checks their SHA-256 against `scripts/supply_chain_tools.json`. Where upstream provides a checksum file, the file itself is hash-pinned and its contents are checked too. Otherwise the downloaded asset's SHA-256 is pinned in that manifest. Existing different binaries are never overwritten.

`.betterleaks.toml` extends the built-in rules. Its only exception is the `shaping_sha256` property (a digest of font shaping test results) in `tests/fixtures/widths-1.006.json`, for the generic-api-key rule only. Other values in that file and provider-specific rules remain scanned. Report a new secret by location and type without sharing its value; do not delete it or rewrite history.

## Workflow lint

`workflow-lint.yml` runs actionlint 1.7.12 with ShellCheck 0.11.0 and zizmor 1.32.0 on changes to `.github/` or the tool installer, and weekly. All workflows and Dependabot configuration are checked. Actions keep full commit SHA pins and version comments so Dependabot can update both together. No linter rule exempts updated Action versions.

```sh
python3 scripts/install_supply_chain_tools.py actionlint shellcheck zizmor \
  --bin-dir /path/to/work/bin --download-dir /path/to/work/downloads
export PATH="/path/to/work/bin:$PATH"
actionlint
zizmor --persona pedantic --strict-collection --cache-dir /path/to/work/zizmor-cache \
  .github/workflows .github/dependabot.yml
```

Set `GH_TOKEN` to enable GitHub API audits; `--offline` runs only local audits. The official zizmor binary keeps lint dependencies outside the font build environment. `.github/zizmor.yml` records narrow exceptions: actionlint rejects the proposed `$/` self-repository syntax, so the release retains `./` at the same commit; native proof runs and independent release tags retain their existing concurrency behavior.

The security and SBOM tool binaries are updated manually: review the official release and checksums, update `scripts/supply_chain_tools.json`, and update the explicit workflow SHA-256 pins for assets without a checksum file. Dependabot continues to update Action SHAs and version comments.

## SBOM and attestations

`build.yml` generates one `fonts/DokushoUD-<version>.cdx.json` and includes it beside the eight fonts in the `DokushoUD` artifact. `release.yml` attaches it to the draft before publishing the immutable release. Earlier releases are unchanged.

`syft` 1.57.2 inventories the installed build venv using the Python installed-package cataloger. `scripts/build_sbom.py` keeps the exact `requirements.txt` pins and their discovered transitive dependencies, excluding unrelated tools such as pip. `scripts/font_sbom.py` separately describes the eight BIZ UD/UDP source fonts (actual embedded versions, Google Fonts commit and URLs, verified SHA-256 and OFL-1.1) and the four faces in TTF and WOFF2 (hashes, versions and OFL-1.1). `cyclonedx-cli` 0.33.1 `merge` combines the three parts. The release subject and build relationships are added, references are checked and `validate --fail-on-errors` validates CycloneDX 1.6. The current requirements produce 18 components plus the release subject and 19 dependency records: the release points to the eight outputs; each output points to its corresponding UD/UDP sources and Python build dependencies; WOFF2 also points to its TTF; fonttools depends on brotli. These are build inputs, not runtime requirements for using the fonts.

Run in a separate clean worktree after building with its own venv. Use a new intermediate directory and output each time; existing files are never overwritten:

```sh
python3 scripts/install_supply_chain_tools.py syft cyclonedx-cli \
  --bin-dir /path/to/work/bin --download-dir /path/to/work/downloads
export PATH="/path/to/work/bin:$PATH"
SOURCE_DATE_EPOCH="$(git log -1 --format=%ct)"
export SOURCE_DATE_EPOCH
.venv/bin/python scripts/build_sbom.py --work-dir /path/to/work/sbom
cyclonedx validate --input-file fonts/DokushoUD-1.010.cdx.json --fail-on-errors
```

The version in the example must match `scripts/spec.py`. An installed package missing from the pins, a changed source hash, a missing output, a wrong embedded version, a missing component after merge, an unresolved reference or an invalid schema stops generation.

The official `actions/attest` v4.2.2 (SHA pinned) is used twice, following its official inputs: `subject-path` alone generates SLSA provenance for all fonts and the SBOM; `subject-path` for the fonts plus `sbom-path` generates a CycloneDX SBOM attestation. Only the release job has `id-token: write` and `attestations: write`; build and PR jobs keep read permission. The attestation is created before publication and no bundle is uploaded as an extra release asset.

Download the fonts and the JSON for the same release and use a GitHub CLI with `gh attestation` support. Check provenance, the SBOM attestation for each font, and provenance of the JSON itself:

```sh
# 1.010 is an example: use the version you downloaded.
gh attestation verify DokushoUDMincho-Regular.ttf --repo hayatedayon/dokusho-ud-fonts \
  --signer-workflow hayatedayon/dokusho-ud-fonts/.github/workflows/release.yml
gh attestation verify DokushoUDMincho-Regular.ttf --repo hayatedayon/dokusho-ud-fonts \
  --signer-workflow hayatedayon/dokusho-ud-fonts/.github/workflows/release.yml \
  --predicate-type https://cyclonedx.org/bom
gh attestation verify DokushoUD-1.010.cdx.json --repo hayatedayon/dokusho-ud-fonts \
  --signer-workflow hayatedayon/dokusho-ud-fonts/.github/workflows/release.yml
```

`--signer-workflow` rejects attestations from unrelated test workflows in this repository. A verified attestation binds a digest and build identity; it does not assert that a font is defect-free or that the SBOM is exhaustive.
