# The Electric Kool-Aid Background Remover — Project Brief

A portable Windows desktop tool for comparing background-removal models
across a folder of images. Built for internal use at Dyalog, primarily to
process staff photography. This brief is intended to bring another Claude
instance up to speed on context, decisions, and conventions.

**Provenance:** this entire project — application code, documentation,
design decisions, and this SPEC — was written by Claude (Anthropic) across
multiple conversations, directed by a human user. The one exception is the
name, which the human came up with. No code or docs were written by hand.
If you are a future Claude instance reading this: yes, you wrote most of
it. Try not to undo the good bits.

## Who this is for

A single user (the developer) on a high-spec Windows workstation:

- Windows 11 Pro
- AMD Ryzen 9 9950X3D (16C/32T), 64 GB RAM
- NVIDIA RTX 2080 (Turing, 8 GB) — present but workflow targets CPU
- Python 3.14 (currently the only Python installed); PyTorch wheels confirmed
  working on 3.14 as of May 2026
- Git installed and on PATH (required for installing BEN2)

The user is technically literate, comfortable with CLIs but prefers a small
GUI for repeated batch operations. They do not care about per-image speed —
they care about output quality and being able to A/B test models on real
content.

## Purpose

The user receives high-resolution group photographs from a professional
photographer at 300 DPI. They need transparent-background cutouts of these
photos for marketing/web/print use. Different background-removal models
produce visibly different results on different subject matter (especially
on hair edges and complex backgrounds), and the user wants to compare
candidates side-by-side rather than commit to one model up front.

The tool batch-processes a folder of images through one or more selected
models and writes outputs to labelled sibling folders for easy comparison.

## Functional requirements

1. **Input** — a folder of images OR a single image, chosen via separate
   pickers (Folder… / Image…). Supported extensions: `.jpg .jpeg .png
   .webp .tif .tiff .bmp`. Error if the selected folder contains no
   supported images, or if a chosen file isn't a supported type. When a
   single image is chosen, output folders are still created as siblings
   inside the image's parent directory.
2. **Format** — choose between `PNG`, `TIFF`, or `WebP` via a dropdown.
   TIFF uses lossless LZW compression. WebP uses lossless mode at quality
   100. All three formats preserve transparency (alpha channel) and carry
   the source image's DPI metadata through to the output (default 300 if
   the source is missing the tag). WebP has a hard 16383px-per-axis limit
   baked into the format; the app validates this upfront and refuses to
   start a run if any input image exceeds it (listing the offending
   images so the user can fix the input or pick a different format).
3. **Models** — multi-select from (BEN2 and BiRefNet-General default on; the
   rest default off):
   - **BEN2** (PramaLLC, MIT-licensed, installed from GitHub)
   - **BiRefNet-General** (via `rembg`)
   - **BiRefNet-HR** (via `rembg`, mapped to the `birefnet-hrsod` weights —
     high-resolution variant of the architecture)
   - **BiRefNet-Portrait** (via `rembg`)
   - **BiRefNet-Massive** (via `rembg`)
   - **BiRefNet-Lite** (via `rembg`)
   See the model table below for details and licence notes.
4. **Output** — for each selected model, a subfolder is created **inside the
   input folder** with the name `{ModelName}-{FORMAT}`, e.g.:
   - `BEN2-PNG`
   - `BiRefNet-General-TIFF`
   - `BiRefNet-Portrait-TIFF`
   Output filenames preserve the input stem and use the format's extension.
   Folders are created lazily on first write, so models that produced no new
   output (e.g. everything was already skipped) leave no empty folder behind.
5. **Skip-existing** — re-runs skip images whose output already exists, so
   crashes/interrupts can be resumed safely.
6. **Auto-install** — missing Python dependencies are detected on startup
   and offered for `pip install` (with user confirmation). Install output
   streams to the in-app log.

## Non-goals

- GPU acceleration. The user has an RTX 2080 but explicitly does not care
  about speed; CPU inference is fine. Code falls back to GPU automatically
  if `torch.cuda.is_available()` returns True, but no setup is required.
- Bundling as a `.exe`. PyTorch alone would make any PyInstaller bundle
  multiple GB. The tool is portable as a `.py` file that uses the system
  Python and self-bootstraps its dependencies.
- Cross-platform. Targeting Windows only.
- Image preview/comparison UI. Output folders are inspected externally.

## Models — quick reference

| Display name        | Backend | Model identifier         | Default | Notes                                      |
|---------------------|---------|--------------------------|---------|---------------------------------------------|
| BEN2                | direct  | `PramaLLC/BEN2`          | On      | HuggingFace repo. CGM pipeline. `refine_foreground=True` used. MIT. |
| BiRefNet-General    | rembg   | `birefnet-general`       | On      | Strong general-purpose default. MIT.        |
| BiRefNet-HR         | rembg   | `birefnet-hrsod`         | Off     | High-resolution variant (HRSOD weights). MIT. Note name mismatch: display name is "HR" but rembg's identifier is `birefnet-hrsod`. |
| BiRefNet-Portrait   | rembg   | `birefnet-portrait`      | Off     | Single-portrait tuned; mixed on groups.     |
| BiRefNet-Massive    | rembg   | `birefnet-massive`       | Off     | Larger training set than General.           |
| BiRefNet-Lite       | rembg   | `birefnet-general-lite`  | Off     | Faster, lighter variant of General.         |

Adding a model is a single entry in `MODELS` in the app file with
`backend`, `rembg_name`, `description`, and `default_on`. No other code
changes needed.

**Licence note for future additions:** BRIA-RMBG (`bria-rmbg`) is
available via rembg but was deliberately excluded from this build because
its CC BY-NC 4.0 licence forbids commercial use. Any future model added
here should have a permissive licence (MIT / Apache-2.0 etc.) confirmed
before inclusion, since Dyalog's likely uses are commercial.

## Technical decisions

- **Tkinter / ttk** for the GUI. Stdlib-only, no extra dep, looks native enough.
- **Threading** — dependency install and image processing run on background
  threads; UI updates marshalled via `self.after(0, ...)`.
- **DPI passthrough** — `src.info.get("dpi", (300, 300))` is read per-image
  inside a `with Image.open(path) as src:` block (the context manager
  releases the file handle promptly, which matters on Windows for large
  batches) and passed to `Image.save(..., dpi=dpi)`. PNG and TIFF both
  support the tag.
- **TIFF compression** — `tiff_lzw` is lossless, supported everywhere, keeps
  file sizes in the 30–80 MB range per image at 24 MP rather than 100+ MB
  uncompressed.
- **WebP encoding** — `format="WEBP", lossless=True, quality=100`. `quality`
  in WebP's lossless mode tunes the encoder's compression effort (not
  visual quality, which is bit-perfect at lossless); 100 = best compression.
  Pillow handles WebP natively, no extra dependency. Typical file sizes
  are 25–35% smaller than PNG. The 16383px-per-axis ceiling is a hard
  limit baked into the WebP container.
- **Progress indication** — an indeterminate `ttk.Progressbar` runs while
  processing (visual liveness) and the status bar text cycles through a
  dots animation appended to a base message ("Image 3/12 – BEN2", etc.).
  Both stop together when the run finishes or errors. Implemented via
  `self.after()` calls so the main thread stays responsive while the
  worker thread updates the base message.
- **Window icon** — embedded as a base64 ICO constant (`LEMON_ICO_B64`,
  at the bottom of the file to keep it out of the way). On startup the
  bytes are written to a temp file via `tempfile.mkstemp(suffix=".ico")`
  and `iconbitmap(default=path)` is called. The .ico is a true
  multi-resolution Windows icon containing 16, 32, and 48 pixel renders
  each drawn separately at the right size — Windows picks the
  appropriate one for the title bar, taskbar, and Alt-Tab. An `atexit`
  handler removes the temp file on exit. Single-file convention preserved
  (no external .ico to ship).

  History: v3.4 tried iconphoto + embedded PNG → blank space at title-bar
  size because Tk couldn't render 96×97 RGBA into 16×16 well. v3.5
  switched to iconbitmap + embedded ICO, but the source .ico was a single
  96×97 image wrapped in an ICO container, so Windows still had to scale
  it down and got the same blank result. v3.6 uses a true multi-res .ico
  with native 16/32/48 renders — that's the correct shape of input for
  Windows iconbitmap.

  **Attribution:** the lemon icon is CC BY 4.0 licensed; credit must
  appear in README.md (see Credits section there).
- **BEN2 install via Git URL** — BEN2 isn't on PyPI as `ben2`. The pip target
  is `git+https://github.com/PramaLLC/BEN2.git`. This requires Git on PATH.
  BEN2 also imports `cv2` (OpenCV) without listing it as a dependency, so
  `opencv-python` is installed alongside.
- **Sessions loaded once** — rembg sessions and the BEN2 model are
  instantiated once at the start of a run and reused across all images.

## Known issues / caveats

- **First-run download size**: PyTorch CPU wheels are ~250 MB, rembg models
  ~900 MB each on first use, BEN2 ~400 MB. Plus their transitive deps. Total
  first-run footprint is several GB; warn users accordingly.
- **Python 3.14 is bleeding-edge**. Most ML libraries support it as of May
  2026 but some transitive deps may not. If install fails on a specific
  package, suggest Python 3.12.
- **BEN2 setup.py classifies as Python 3.10** but actually works on newer
  versions. The classifier is documentation-only.
- **`birefnet-portrait` on group photos** behaves unpredictably (model was
  trained on single-subject portraits). Keep it available but don't promote
  it as the obvious choice for group shots.
- **Tkinter dialogs must run on the main thread.** When asking the user a
  question from a worker thread (e.g. dependency install confirmation),
  marshal via `self.after()` and block on a `threading.Event` for the answer.

## File layout

The whole app is one file: `the-electric-kool-aid-background-remover.py`.
The version lives inside the file as `__version__` and in Git commit
messages and tags — not in the filename. There are no other runtime
assets. The earlier batch-processing scripts (`compare_bg_removal.py`,
`compare_all_tiff.py`, etc.) remain in the user's working folder as a
reference / fallback for headless runs.

Two documentation files sit alongside the app:

- `README.md` — user-facing docs (what it does, how to install, how to
  use, troubleshooting). Written for someone arriving at the project cold,
  potentially via GitHub. Assumes no prior context.
- `SPEC.md` — developer/handover docs. Context, decisions, conventions,
  caveats. Written for the next developer (human or AI) picking up the
  codebase.

The version string lives in a single `__version__` constant near the top of
the app file; `APP_TITLE` is built from it, so the title bar always matches.
Bumping a release means: edit `__version__`, update `README.md` and
`SPEC.md`, add an entry to the version history below, and use the version
number in the Git commit message.

## Conventions

- Folder naming for outputs: `{ModelDisplayName}-{FORMAT}` where FORMAT is
  uppercase (`PNG` or `TIFF`). Examples: `BEN2-PNG`, `BiRefNet-Portrait-TIFF`.
- File naming for outputs: `{input_stem}_{ModelDisplayName}{ext}`. Example:
  input `test_01.jpg` → `BEN2-PNG/test_01_BEN2.png` and
  `BiRefNet-Portrait-PNG/test_01_BiRefNet-Portrait.png`. The model suffix in
  the filename means files remain self-identifying even when moved out of
  their folder.
- All output folders are siblings inside the input folder, not in a separate
  location. This keeps a run self-contained — copy the input folder
  somewhere and all outputs go with it.
- All log lines are written to a single `ScrolledText` widget; status bar
  shows current high-level state.

## Run instructions for the user

```
py the-electric-kool-aid-background-remover.py
```

On first run, the app will offer to install missing dependencies. After
that, the workflow is: Browse → pick folder → tick models → tick format →
Run.

## Version history

- **v3.7.1** — patch: `REQUIRED_DEPS` auto-install targets now pinned to
  match `requirements.txt` (previously unpinned, so quick-start and venv
  routes could diverge); Python version requirement corrected to 3.12+ in
  docstring (was 3.10+, inconsistent with README); README install section
  reordered so venv route is presented first and explicitly labelled
  "Recommended for most users", quick-start labelled as the casual/own-machine
  route.
- **v3.7** — Cancel button stops the run cleanly after the current image
  finishes (sets a flag checked at the top of each image loop iteration);
  Open Output Folder button opens the input directory in Explorer after a
  run completes; `requirements.txt` added with pinned versions from a
  known-working environment (Python 3.14.3, May 2026); `MODEL-LICENCES.md`
  added documenting each bundled model's source, licence, and verification
  date; AI Slop disclaimer moved from top of README to a Provenance section
  at the bottom per reviewer feedback (the joke works, it just shouldn't
  be the first thing a non-technical stakeholder sees).
- **v3.6** — window icon properly working at last. Replaced the embedded
  .ico with a true multi-resolution version (16/32/48 px renders, each
  drawn at native size). Previous .ico in v3.5 was a single 96×97 image
  wrapped in ICO container format — Windows had to scale it down to 16
  for the title bar and the visible content collapsed to nothing. New
  icon is CC BY 4.0 licensed; attribution lives in README.md. Source
  file shrank from ~80 KB / 1300 lines to ~50 KB / 880 lines because
  the new ICO is smaller despite being multi-res.
- **v3.5** — window icon fixed. Previous (v3.4) approach used an embedded
  PNG via `iconphoto()`, which on Windows reserved title-bar space for an
  icon but rendered as blank (96×97 RGBA scaled down to 16px lost the
  visible shape). Replaced with an embedded multi-resolution .ico file
  written to a temp path on startup and applied via `iconbitmap()`. Adds
  ~51 KB of base64 to the source file; that's the cost of a working icon
  on Windows. Single-file convention preserved.
- **v3.4** — added WebP as an output format alongside PNG and TIFF
  (lossless, dpi-preserving, ~30% smaller files), with upfront validation
  against WebP's 16383px-per-axis canvas limit; format picker changed
  from radio buttons to a dropdown with inline description text; input
  picker now accepts either a folder or a single image (two buttons:
  Folder… / Image…); added an indeterminate progress bar and a
  dots-animated status message ("Image 3/12 – BEN2…") so the app shows
  liveness during long inference runs; Copy button renamed to "Copy
  Output"; window icon set from an embedded base64 PNG (a lemon).
- **v3.3** — added BiRefNet-HR model (mapped to rembg's `birefnet-hrsod`
  weights — high-resolution variant of the BiRefNet architecture, MIT
  licensed); added a Copy button above the output log that writes the
  entire log to the clipboard. At the time, the SPEC filename was versioned
  (e.g. `SPEC-v3.3.md`); this convention was later dropped in favour of a
  single `SPEC.md`.
- **v3.2** — file renamed to `Kool-Aid-Background-Remover-v{version}.py`;
  `__version__` constant introduced and surfaced in the title bar so the
  window identifies which build is running. No behavioural changes.
- **v3.1** — `Image.open` wrapped in a context manager (releases file
  handles promptly on Windows); output folders created lazily on first
  write so unused model folders no longer get left behind; docstring and
  this spec brought back in sync with the actual five-model lineup.
- **v3** — current five-model lineup (BEN2, BiRefNet General / Portrait /
  Massive / Lite); Tkinter GUI with auto-install of missing deps.
- **v2, v1** — earlier iterations (headless batch scripts kept as fallback
  in the working folder; see "File layout").
