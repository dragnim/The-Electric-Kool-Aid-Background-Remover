# The Electric Kool-Aid Background Remover - Project Brief

A free, local, privacy-respecting background remover for Windows. Removes
backgrounds from single images or whole folders using a choice of seven AI
models, with lossless PNG, TIFF, or WebP output.

This document is the developer and contributor handover brief. Its primary
audience is a future Claude instance being asked to extend or maintain the
project - read this before touching any code. It covers the context behind
the tool, why decisions were made, the model lineup, known caveats, and
conventions to follow. Everything here was written by Claude across multiple
conversations; the design decisions were made by the human.

If you are a Claude instance picking this up: this document exists
specifically for you. Read it in full before making changes. The version
history at the bottom is particularly useful for understanding what has
already been tried and why.

**Provenance:** the application code, documentation, and this SPEC were
written by Claude (Anthropic). The design decisions, product direction, and
the name were the human's. No code or docs were written by hand.

## Who this is for

Anyone who wants to remove image backgrounds locally without uploading to
a cloud service, on Windows. The original use case was processing
high-resolution professional photography (300 DPI group portraits) for
marketing and web use, where edge quality on hair and complex backgrounds
matters more than speed.

The tool is also well suited for anyone who wants to compare multiple AI
background-removal models on their own material before committing to one.

## Purpose

The tool processes a folder or single image through one or more selected
background-removal models and writes transparent-background cutouts to
labelled sibling folders. Different models produce visibly different results
on different subject matter - especially on hair edges, glasses, and complex
backgrounds - and having outputs in separate named folders makes it easy to
compare results before committing to one model for a full batch.

## Functional requirements

1. **Input** - a folder of images OR a single image, chosen via separate
   pickers (Folder… / Image…) or by dragging and dropping onto the window.
   Supported extensions: `.jpg .jpeg .png .webp .tif .tiff .bmp`. Error if
   the selected folder contains no supported images, or if a chosen file
   isn't a supported type. When a single image is chosen, output folders
   are still created as siblings inside the image's parent directory.
   Dropping multiple files onto the window uses their parent folder as
   the input folder.
2. **Format** - choose between `PNG`, `TIFF`, or `WebP` via a dropdown.
   TIFF uses lossless LZW compression. WebP uses lossless mode at quality
   100. All three formats preserve transparency (alpha channel) and carry
   the source image's DPI metadata through to the output (default 300 if
   the source is missing the tag). WebP has a hard 16383px-per-axis limit
   baked into the format; the app validates this upfront and refuses to
   start a run if any input image exceeds it (listing the offending
   images so the user can fix the input or pick a different format).
3. **Models** - multi-select from (BEN2 and BiRefNet-General default on; the
   rest default off):
   - **BEN2** (PramaLLC, MIT-licensed, installed from GitHub)
   - **BiRefNet-General** (via `rembg`)
   - **BiRefNet-HR** (via `rembg`, mapped to the `birefnet-hrsod` weights  - 
     high-resolution variant of the architecture)
   - **BiRefNet-Portrait** (via `rembg`)
   - **BiRefNet-Massive** (via `rembg`)
   - **BiRefNet-Lite** (via `rembg`)
   - **InSPyReNet** (via `transparent-background`, MIT-licensed,
     installed lazily on first use - see Technical decisions)
   See the model table below for details and licence notes.
4. **Output** - for each selected model, a subfolder is created **inside the
   input folder** with the name `{ModelName}-{FORMAT}`, e.g.:
   - `BEN2-PNG`
   - `BiRefNet-General-TIFF`
   - `BiRefNet-Portrait-TIFF`
   Output filenames preserve the input stem and use the format's extension.
   Folders are created lazily on first write, so models that produced no new
   output (e.g. everything was already skipped) leave no empty folder behind.
5. **Skip-existing** - re-runs skip images whose output already exists, so
   crashes/interrupts can be resumed safely.
6. **Auto-install** - missing Python dependencies are detected on startup
   and offered for `pip install` (with user confirmation). Install output
   streams to the in-app log.
7. **Settings persistence** - last-used input folder, output format, and
   model selections are saved to `~/.ekbr_settings.json` on each run and
   restored on startup. A missing or corrupt file is silently ignored.
8. **Low-RAM notice** - if total physical RAM is below 24 GB (detected via
   `ctypes.windll.kernel32.GlobalMemoryStatusEx`, no extra dependency), a
   note is logged at startup advising the user to run one model at a time.

## Non-goals

- Bundling as a `.exe`. PyTorch alone would make any PyInstaller bundle
  multiple GB. The tool is distributed as a `.py` file plus `launch.bat`,
  which handles Python setup and GPU detection transparently.
- Cross-platform. Targeting Windows only.
- Image preview/comparison UI. Output folders are inspected externally.

## Models - quick reference

| Display name        | Backend | Model identifier         | Default | Notes                                      |
|---------------------|---------|--------------------------|---------|---------------------------------------------|
| BEN2                | direct  | `PramaLLC/BEN2`          | On      | HuggingFace repo. CGM pipeline. `refine_foreground=True` used. MIT. |
| BiRefNet-General    | rembg   | `birefnet-general`       | On      | Strong general-purpose default. MIT.        |
| BiRefNet-HR         | rembg   | `birefnet-hrsod`         | Off     | High-resolution variant (HRSOD weights). MIT. Note name mismatch: display name is "HR" but rembg's identifier is `birefnet-hrsod`. |
| BiRefNet-Portrait   | rembg   | `birefnet-portrait`      | Off     | Single-portrait tuned; mixed on groups.     |
| BiRefNet-Massive    | rembg   | `birefnet-massive`       | Off     | Larger training set than General.           |
| BiRefNet-Lite       | rembg   | `birefnet-general-lite`  | Off     | Faster, lighter variant of General.         |
| InSPyReNet          | direct  | `transparent_background.Remover` | Off | Pyramid-based salient object detection (ACCV 2022). Different architecture family from BEN2/BiRefNet. Configured with `mode='base'`, `resize='dynamic'`. MIT. **Lazy install** - see Technical decisions. |

Adding a model is a single entry in `MODELS` in the app file with
`backend`, `rembg_name`, `description`, and `default_on`. Models with a
new backend (not `rembg`) also need a load block and an inference branch
in `_process` - see the BEN2 and InSPyReNet code paths for the pattern.
For backends with fragile install (like InSPyReNet), follow the
`_try_load_inspyrenet` pattern: lazy import, prompt-to-install on
ImportError, graceful degradation to a None return on any failure.

**Licence note for future additions:** BRIA-RMBG (`bria-rmbg`) is
available via rembg but was deliberately excluded from this build because
its CC BY-NC 4.0 licence forbids commercial use. Any future model added
here should have a permissive licence (MIT / Apache-2.0 etc.) confirmed
before inclusion, since the likely uses are commercial.

## Technical decisions

- **Tkinter / ttk** for the GUI. Near-stdlib — the only UI-specific extra dep is `tkinterdnd2` for drag-and-drop support. Falls back to plain `tk.Tk` if not yet installed; the `_AppBase` variable is set at module load time so a restart is required after install to activate DnD.
- **Launcher files** - three files sit alongside the `.py` script:
  - `launch.bat` — the user-facing entry point. Checks for Python (embedded
    or system), installs embedded Python 3.12 if needed (into `_python\`),
    runs `gpu_setup.py` to handle GPU detection and PyTorch install, then
    launches the app.
  - `gpu_setup.py` — Python helper called by `launch.bat` and `cleanup.bat`.
    Detects NVIDIA GPU via `nvidia-smi`, checks whether torch is CPU or CUDA,
    and offers to install/upgrade/downgrade PyTorch accordingly. All GPU
    detection logic lives here rather than in the bat file to avoid batch
    variable expansion issues. Must be called with `--from-launcher` flag
    to suppress the "don't run directly" message; `--force-cpu` and
    `--force-offer` flags used by `cleanup.bat` for switching.
  - `cleanup.bat` — management tool. Shows what the app installed and where,
    with folder sizes. Section 4 lets users switch between CPU and GPU
    PyTorch versions by calling `gpu_setup.py --force-cpu` or
    `--force-offer`.
- **Title bar CPU/GPU indicator** - `_enable_run()` updates the window title
  to append `(GPU)` or `(CPU)` after deps are confirmed loaded, reflecting
  actual `torch.cuda.is_available()` state rather than what's installed.
- **Threading** - dependency install and image processing run on background
  threads; UI updates marshalled via `self.after(0, ...)`.
- **DPI passthrough** - `src.info.get("dpi", (300, 300))` is read per-image
  inside a `with Image.open(path) as src:` block (the context manager
  releases the file handle promptly, which matters on Windows for large
  batches) and passed to `Image.save(..., dpi=dpi)`. PNG and TIFF both
  support the tag.
- **TIFF compression** - `tiff_lzw` is lossless, supported everywhere, keeps
  file sizes in the 30–80 MB range per image at 24 MP rather than 100+ MB
  uncompressed.
- **WebP encoding** - `format="WEBP", lossless=True, quality=100`. `quality`
  in WebP's lossless mode tunes the encoder's compression effort (not
  visual quality, which is bit-perfect at lossless); 100 = best compression.
  Pillow handles WebP natively, no extra dependency. Typical file sizes
  are 25–35% smaller than PNG. The 16383px-per-axis ceiling is a hard
  limit baked into the WebP container.
- **Progress indication** - an indeterminate `ttk.Progressbar` runs while
  processing (visual liveness) and the status bar text cycles through a
  dots animation appended to a base message ("Image 3/12 – BEN2", etc.).
  Both stop together when the run finishes or errors. Implemented via
  `self.after()` calls so the main thread stays responsive while the
  worker thread updates the base message.
- **Window icon** - embedded as a base64 ICO constant (`LEMON_ICO_B64`,
  at the bottom of the file to keep it out of the way). On startup the
  bytes are written to a temp file via `tempfile.mkstemp(suffix=".ico")`
  and `iconbitmap(default=path)` is called. The .ico is a true
  multi-resolution Windows icon containing 16, 32, and 48 pixel renders
  each drawn separately at the right size - Windows picks the
  appropriate one for the title bar, taskbar, and Alt-Tab. An `atexit`
  handler removes the temp file on exit. Single-file convention preserved
  (no external .ico to ship).

  History: v3.4 tried iconphoto + embedded PNG → blank space at title-bar
  size because Tk couldn't render 96×97 RGBA into 16×16 well. v3.5
  switched to iconbitmap + embedded ICO, but the source .ico was a single
  96×97 image wrapped in an ICO container, so Windows still had to scale
  it down and got the same blank result. v3.6 uses a true multi-res .ico
  with native 16/32/48 renders - that's the correct shape of input for
  Windows iconbitmap.

  **Attribution:** the lemon icon is CC BY 4.0 licensed; credit must
  appear in README.md (see Credits section there).
- **BEN2 install via GitHub zip** - BEN2 isn't on PyPI. Rather than using
  a `git+https://` URL (which requires Git installed on PATH), we install
  from a pinned GitHub zip archive:
  `https://github.com/PramaLLC/BEN2/archive/{commit}.zip`
  pip can install directly from zip URLs without Git. This removes Git as
  a requirement entirely, which matters for the launcher work ahead.
- **InSPyReNet is lazy-loaded** - this is the key thing to know about
  InSPyReNet. The model is wrapped in the `transparent-background` PyPI
  package, and the obvious thing would be to drop it into `REQUIRED_DEPS`
  alongside `rembg` and `ben2`. **We don't.** The reason: its dep chain is
  `transparent-background` -> `albumentations` -> `albucore` -> `stringzilla`,
  and `stringzilla 4.x` doesn't ship a Python 3.14 wheel as of May 2026.
  On 3.14, pip falls back to building from source, which requires the
  Microsoft Visual C++ Build Tools - an enormous extra install nobody
  wants to do for a background remover. We tried `transparent-background`
  as a startup dep in early v3.9 and it broke the dependency check entirely
  on Python 3.14, blocking the other six models that were working fine.
  
  Solution: keep it out of `REQUIRED_DEPS`. The `_try_load_inspyrenet`
  helper handles the lazy path - try importing, prompt-to-install on
  ImportError, gracefully degrade on any failure. The caller drops every
  InSPyReNet target from the run if `_try_load_inspyrenet` returns None,
  and continues with the remaining models. This means: (a) users on 3.12
  who tick InSPyReNet get prompted, install succeeds, model works;
  (b) users on 3.14 who tick InSPyReNet get prompted, install fails, run
  continues with the other models they ticked, log explains the fix.
  
  The model itself, when it does load, is configured with `mode='base'`
  (full-quality checkpoint, not `fast`) and `resize='dynamic'` (sharper
  edges than default `static`, slightly less stable - appropriate for the
  high-DPI photography this tool targets, since edge quality is the whole
  reason for running multiple models in the first place). Its weights
  (~180 MB) download from Google Drive to `~/.transparent-background/` on
  first model construction. If that download is blocked by a proxy, the
  package supports an `http_proxy` field in its config file.
  
  **For future maintainers:** if a new backend has similar install fragility
  (e.g. depends on a not-yet-wheeled C extension), follow the same pattern.
  Don't add it to `REQUIRED_DEPS`; write a `_try_load_<name>` helper; have
  the caller drop the targets and continue on a None return.
- **Sessions loaded once** - rembg sessions, the BEN2 model, and the
  InSPyReNet model (when loaded) are instantiated once at the start of a
  run and reused across all images.

## Known issues / caveats

- **First-run download size**: PyTorch CPU wheels are ~250 MB, rembg models
  ~900 MB each on first use, BEN2 ~400 MB. Plus their transitive deps. Total
  first-run footprint is several GB; warn users accordingly.
- **Python 3.14 is bleeding-edge**. Most ML libraries support it as of May
  2026 but some transitive deps may not. If install fails on a specific
  package, suggest Python 3.12.
- **InSPyReNet on Python 3.14 doesn't work as of May 2026.** Documented
  above under Technical decisions. The lazy-load + graceful-degradation
  pattern means this doesn't break anything else; users get a clear
  message and the rest of the app keeps working. Revisit this once
  stringzilla ships 3.14 wheels (track at https://pypi.org/project/stringzilla/).
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
messages and tags - not in the filename. There are no other runtime
assets. The earlier batch-processing scripts (`compare_bg_removal.py`,
`compare_all_tiff.py`, etc.) remain in the user's working folder as a
reference / fallback for headless runs.

Two documentation files sit alongside the app:

- `README.md` - user-facing docs (what it does, how to install, how to
  use, troubleshooting). Written for someone arriving at the project cold,
  potentially via GitHub. Assumes no prior context.
- `SPEC.md` - developer/handover docs. Context, decisions, conventions,
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
  location. This keeps a run self-contained - copy the input folder
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

- **v3.12** - two user-experience additions: settings persistence and drag-and-drop.

  **Settings persistence:** the app now saves the last-used input folder,
  output format, and model checkbox state to `~/.ekbr_settings.json` on
  each run and restores them on startup. A missing or corrupt settings file
  is silently ignored so defaults always apply cleanly.

  **Drag and drop:** `tkinterdnd2` added as a required dependency. The App
  class subclasses `TkinterDnD.Tk` when the package is available
  (`_AppBase` variable, determined at import time; falls back to `tk.Tk`
  if not yet installed). Dropping a folder onto the window sets it as the
  folder input; dropping a single image file sets it as the image input;
  dropping multiple files sets their parent folder. If tkinterdnd2 is
  installed mid-session the user must restart the app to activate DnD,
  since the base class is fixed at import time.

  **Low-RAM warning:** `_get_total_ram_gb()` uses
  `ctypes.windll.kernel32.GlobalMemoryStatusEx` (no extra dependency) to
  check total physical RAM at startup. If below 24 GB, a note is logged
  advising the user to run one model at a time to avoid paging slowdowns.

  **UI polish:** model status label changed from "Ready" to "Installed"
  (clearer meaning); licence mentions removed from all model descriptions
  (licence info belongs in MODEL-LICENCES.md, not one-line UI labels);
  Models LabelFrame caption simplified from "Models (select one or more)"
  to "Models" (consistent with other section labels).

- **v3.11** - two changes: eliminated Git as a requirement, and added the
  launcher file set (`launch.bat`, `gpu_setup.py`, `cleanup.bat`).

  **Git removal:** BEN2 switched from `git+https://github.com/PramaLLC/BEN2.git`
  to a GitHub zip archive URL, which pip handles natively without Git.

  **Launcher files:** `launch.bat` is now the recommended entry point.
  It handles Python detection (embedded or system), installs embedded
  Python 3.12 into `_python\` if needed, runs `gpu_setup.py` for GPU
  detection and PyTorch install choice, then launches the app. All GPU
  detection logic lives in `gpu_setup.py` (Python) rather than the bat
  file — batch variable expansion made reliable detection impossible in
  pure batch. `gpu_setup.py` uses `nvidia-smi -q` for CUDA version,
  checks `torch.version.cuda` for install state, and offers GPU install
  on first run or upgrade/downgrade thereafter. Must be called with
  `--from-launcher` to skip the "don't run directly" message.

  `cleanup.bat` is the management tool — shows everything installed with
  sizes, and Section 4 switches between CPU/GPU PyTorch via
  `gpu_setup.py --force-cpu` or `--force-offer`.

  Title bar now shows `(GPU)` or `(CPU)` after deps load, set in
  `_enable_run()` from `torch.cuda.is_available()`.

  README gains a Getting Started section at the top, updated GPU tip,
  updated "not an exe" entry, and cleanup.bat mentioned in disk space
  section. SPEC Non-goals updated (GPU is now actively offered).

- **v3.10** - model cache status indicators and trash buttons. Each model
  row in the UI now shows a status label (e.g. "Installed  420 MB" or
  "Not downloaded") and a small × trash button on the right side of the
  header line. The trash button is always present but greyed out (disabled)
  when the model isn't cached, so the layout never shifts. Clicking the
  trash button asks for confirmation, deletes the cached weights, logs what
  was freed, and immediately updates the status label. Status is refreshed
  at startup, after each run (new weights may have been downloaded), and
  after any trash action.

  Cache locations per model:
  - rembg models (BiRefNet variants): `~/.u2net/{model-id}.onnx`
  - BEN2: `~/.cache/huggingface/hub/models--PramaLLC--BEN2/` (folder)
  - InSPyReNet: `~/.transparent-background/ckpt_base.pth`

  Trash deletes only the weight files/folders, not the Python packages.
  Deleting a model's weights is safe and reversible — they re-download
  automatically on the next run that uses that model.

  New module-level helpers: `_cache_path()`, `_is_cached()`,
  `_cache_size_mb()`, `_delete_cache()`. New App methods:
  `_refresh_model_status()`, `_trash_model()`. New instance vars:
  `model_status_vars`, `model_trash_btns`.
- **v3.9.2** - fix: progress bar invisible after adding the InSPyReNet
  model row in v3.9. The window height was a hardcoded 820px sized for
  six model rows; adding a seventh row (especially with the unusually
  long install-warning description that was originally on InSPyReNet)
  pushed the progress bar - which is packed just before the Log frame -
  off the bottom of the window. The Log frame's `expand=True` then ate
  the remaining vertical space, leaving the progress bar with zero pixels
  to draw into. Verified by checking `progress.winfo_geometry()`: in the
  broken build it reported `1x1+0+0`; after the fix, `300x14+240+837` as
  expected.
  
  Two changes: `WINDOW_SIZE` bumped from `780x820` to `780x880` (one
  extra row of headroom for the 7th model), and the InSPyReNet
  description shortened from a 350+ character paragraph (which wrapped to
  4 lines) to a single short sentence consistent with the other model
  descriptions (which wrap to 1-2 lines). The detailed Python 3.14
  install-failure warning lives in the install-prompt dialog and the
  README troubleshooting section, where it's more useful.
  
  Future-maintainer note: if more models are ever added, the window
  needs to grow or the model descriptions need to stay short. The pack
  order is Input -> Format -> Models (no expand) -> Run/Cancel buttons
  -> Progress bar (no expand) -> Log frame (expand=True) -> Status bar.
  Anything not-expand above the Log frame consumes from the same fixed
  pool of pixels; once that pool is exhausted, widgets below the Models
  frame get squeezed to zero, but the bug is silent - no error, no
  warning, the widget just doesn't render.
- **v3.9.1** - patch: renamed the bottom LabelFrame from "Output" to "Log",
  and the "Copy Output" button to "Copy Log". Both labels were doing
  double duty - "Output" meant both "the cutout files saved to disk"
  (in "Open Output Folder", "Output folders will be created in...") and
  "the run log shown in the text widget" (in "Copy Output", "Output"
  LabelFrame). The button sat right next to "Open Output Folder", which
  made the ambiguity actively confusing. Now "Output" unambiguously means
  the saved files and "Log" unambiguously means the run log. The
  `__version__` constant and `APP_TITLE` are bumped accordingly. No code
  behaviour changes.
- **v3.9** - added InSPyReNet as a seventh model, via the
  `transparent-background` PyPI package (MIT licence). Selected because the
  previous six models were really two architecture families (BEN2 plus
  five BiRefNet variants), and InSPyReNet is a meaningfully different third
  family - pyramid-based salient object detection rather than bilateral
  reference or confidence-guided matting. Useful for comparison runs on
  material where BEN2 and BiRefNet disagree.
  
  Configured with `mode='base'` and `resize='dynamic'` for best edge
  quality. Default off (to keep first-time runs at two models, consistent
  with the existing default policy).
  
  **The install is lazy-loaded.** First attempt was to add
  `transparent-background` to `REQUIRED_DEPS` like every other model
  dependency. That failed on Python 3.14: the transitive dep chain
  includes `stringzilla`, which has no 3.14 wheel as of May 2026, so pip
  tries to build it from source and fails for any user without MSVC Build
  Tools installed. The failure blocked the entire startup dependency check
  rather than just InSPyReNet, breaking the other six models that were
  working fine. The fix was to move InSPyReNet's install into a lazy
  `_try_load_inspyrenet` helper that runs only when the user actually
  ticks the InSPyReNet checkbox and clicks Run, with graceful degradation
  on any failure (import error, declined install, install error,
  instantiation error). On a failure, InSPyReNet is dropped from this run's
  targets and the other selected models continue. See the Technical
  decisions section for the full rationale and the pattern for future
  fragile-install backends.
- **v3.8** - fix progress bar animating at startup on some Windows themes;
  `progress.stop()` called immediately after widget creation.
- **v3.7.1** - patch: `REQUIRED_DEPS` auto-install targets now pinned to
  match `requirements.txt` (previously unpinned, so quick-start and venv
  routes could diverge); Python version requirement corrected to 3.12+ in
  docstring (was 3.10+, inconsistent with README); README install section
  reordered so venv route is presented first and explicitly labelled
  "Recommended for most users", quick-start labelled as the casual/own-machine
  route.
- **v3.7** - Cancel button stops the run cleanly after the current image
  finishes (sets a flag checked at the top of each image loop iteration);
  Open Output Folder button opens the input directory in Explorer after a
  run completes; `requirements.txt` added with pinned versions from a
  known-working environment (Python 3.14.3, May 2026); `MODEL-LICENCES.md`
  added documenting each bundled model's source, licence, and verification
  date; AI Slop disclaimer moved from top of README to a Provenance section
  at the bottom per reviewer feedback (the joke works, it just shouldn't
  be the first thing a non-technical stakeholder sees).
- **v3.6** - window icon properly working at last. Replaced the embedded
  .ico with a true multi-resolution version (16/32/48 px renders, each
  drawn at native size). Previous .ico in v3.5 was a single 96×97 image
  wrapped in ICO container format - Windows had to scale it down to 16
  for the title bar and the visible content collapsed to nothing. New
  icon is CC BY 4.0 licensed; attribution lives in README.md. Source
  file shrank from ~80 KB / 1300 lines to ~50 KB / 880 lines because
  the new ICO is smaller despite being multi-res.
- **v3.5** - window icon fixed. Previous (v3.4) approach used an embedded
  PNG via `iconphoto()`, which on Windows reserved title-bar space for an
  icon but rendered as blank (96×97 RGBA scaled down to 16px lost the
  visible shape). Replaced with an embedded multi-resolution .ico file
  written to a temp path on startup and applied via `iconbitmap()`. Adds
  ~51 KB of base64 to the source file; that's the cost of a working icon
  on Windows. Single-file convention preserved.
- **v3.4** - added WebP as an output format alongside PNG and TIFF
  (lossless, dpi-preserving, ~30% smaller files), with upfront validation
  against WebP's 16383px-per-axis canvas limit; format picker changed
  from radio buttons to a dropdown with inline description text; input
  picker now accepts either a folder or a single image (two buttons:
  Folder… / Image…); added an indeterminate progress bar and a
  dots-animated status message ("Image 3/12 – BEN2…") so the app shows
  liveness during long inference runs; Copy button renamed to "Copy
  Output"; window icon set from an embedded base64 PNG (a lemon).
- **v3.3** - added BiRefNet-HR model (mapped to rembg's `birefnet-hrsod`
  weights - high-resolution variant of the BiRefNet architecture, MIT
  licensed); added a Copy button above the output log that writes the
  entire log to the clipboard. At the time, the SPEC filename was versioned
  (e.g. `SPEC-v3.3.md`); this convention was later dropped in favour of a
  single `SPEC.md`.
- **v3.2** - file renamed to `Kool-Aid-Background-Remover-v{version}.py`;
  `__version__` constant introduced and surfaced in the title bar so the
  window identifies which build is running. No behavioural changes.
- **v3.1** - `Image.open` wrapped in a context manager (releases file
  handles promptly on Windows); output folders created lazily on first
  write so unused model folders no longer get left behind; docstring and
  this spec brought back in sync with the actual five-model lineup.
- **v3** - current five-model lineup (BEN2, BiRefNet General / Portrait /
  Massive / Lite); Tkinter GUI with auto-install of missing deps.
- **v2, v1** - earlier iterations (headless batch scripts kept as fallback
  in the working folder; see "File layout").
