# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**The Electric Kool-Aid Background Remover** — a free, local, privacy-respecting Windows desktop app that removes image backgrounds using multiple AI models. Everything runs locally; no cloud, no subscription.

- **Single-file app:** `the-electric-kool-aid-background-remover.py` (all logic in one file)
- **Current version:** `__version__` constant near top of the main file; also in `APP_TITLE`, `README.md`, `SPEC.md`
- **Platform:** Windows 10/11 only
- **Python:** 3.12–3.14

## Running the App

```bat
# User entry point (handles Python detection, GPU setup, launch)
launch.bat

# Direct run
py the-electric-kool-aid-background-remover.py

# Development venv
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
py the-electric-kool-aid-background-remover.py
```

No build step, no test suite, no linter configured. Run the app directly.

## Architecture

### Single-File Design

The entire application is `the-electric-kool-aid-background-remover.py`. No sub-modules, no separate packages — everything is in one file by design (simplicity, auditability, single maintenance point).

### Helper Scripts (not imported by the app)

- `launch.bat` — Detects Python, offers embedded Python 3.12 install into `_python\`, runs `gpu_setup.py`, launches app
- `gpu_setup.py` — Detects NVIDIA GPU via `nvidia-smi`, manages PyTorch CPU/GPU switching. Flags:
  - `--from-launcher` — suppresses "don't run directly" message (required for legitimate callers)
  - `--force-cpu` — uninstalls GPU torch, installs CPU torch (used by `cleanup.bat`)
  - `--force-offer` — skips the cuda-already-installed check, always prompts (used by `cleanup.bat`)
- `cleanup.bat` — Shows installed model sizes, manages cleanup and PyTorch version switching

### Core Class: `App(tk.Tk)`

The whole application is one `App` class. Key methods:

| Method | Purpose |
|--------|---------|
| `_check_deps()` | Background thread on startup; detects missing packages and prompts to install |
| `_run()` | Validates input, shows confirmation, starts processing thread |
| `_process(input_dir, images, selected_models, fmt)` | Core processing loop on background thread |
| `_try_load_inspyrenet()` | Lazy loader for InSPyReNet; graceful None on failure |
| `_refresh_model_status()` | Checks disk for cached weights, updates status labels |
| `_trash_model(name)` | Confirms, deletes cached weights, refreshes status |

Module-level cache helpers (not methods): `_cache_path(name)`, `_is_cached(name)`, `_cache_size_mb(name)`, `_delete_cache(name)`.

### Threading Model

- Dependency install and image processing run on **daemon background threads**
- All UI updates marshalled back to main thread via `self.after(0, callback)`
- Block on `threading.Event` when a worker thread needs a dialog answer from the user

### Models (`MODELS` dict)

Each entry has: display name, backend, rembg identifier (if applicable), description, default-on state, cache path, cache-is-dir flag.

| Model | Backend | Default | Cache location |
|-------|---------|---------|----------------|
| BEN2 | direct (`ben2`) | On | `~/.cache/huggingface/hub/models--PramaLLC--BEN2/` (dir) |
| BiRefNet-General | rembg | On | `~/.u2net/birefnet-general.onnx` |
| BiRefNet-HR | rembg | Off | `~/.u2net/birefnet-hrsod.onnx` |
| BiRefNet-Portrait | rembg | Off | `~/.u2net/birefnet-portrait.onnx` |
| BiRefNet-Massive | rembg | Off | `~/.u2net/birefnet-massive.onnx` |
| BiRefNet-Lite | rembg | Off | `~/.u2net/birefnet-general-lite.onnx` |
| InSPyReNet | direct (`transparent_background`), lazy | Off | `~/.transparent-background/ckpt_base.pth` |

All models are MIT-licensed. BRIA-RMBG was deliberately excluded (CC BY-NC 4.0 forbids commercial use).

Rembg sessions, the BEN2 model, and InSPyReNet are instantiated **once per run** at the start of `_process()` and reused across all images.

### `REQUIRED_DEPS` and rembg's pip target

`rembg`'s entry in `REQUIRED_DEPS` is `None` — its pip target is determined at runtime by `_rembg_pip_target()`, which returns `rembg[gpu]` when CUDA torch is installed and `rembg[cpu]` otherwise. Any change to rembg's install target must update both `_rembg_pip_target()` and `requirements.txt`.

### InSPyReNet Lazy-Load Pattern

InSPyReNet is **not** in `REQUIRED_DEPS`. `_try_load_inspyrenet()` tries the import, prompts to install if missing, and returns `None` on failure — processing continues with other models. On Python 3.14, `stringzilla` (transitive dep) has no wheel and the install fails; advise users to untick InSPyReNet or switch to Python 3.12.

### Output Conventions

- Output folders: `{ModelDisplayName}-{FORMAT}/` inside the input folder (e.g., `BEN2-PNG/`)
- Output filenames: `{input_stem}_{ModelDisplayName}{ext}` (e.g., `photo_01_BEN2.png`)
- Folders are created lazily on first write — unused model folders leave nothing behind
- Formats: PNG, TIFF (LZW-compressed), WebP (lossless). All preserve alpha channel and source DPI (default 300 if missing).
- **WebP hard limit: 16383px per axis.** Validated upfront; user is blocked and shown offending files.
- Skip-existing pattern: if output file exists, skip it (allows safe resume of interrupted batches).

### UI Layout Constraint

`WINDOW_SIZE` is a fixed pixel size. The pack order from top to bottom is: Input → Format → Models (no expand) → Run/Cancel buttons → Progress bar (no expand) → Log frame (`expand=True`) → Status bar. Anything above the Log frame that grows (e.g. adding model rows) steals from the fixed pixel pool; once exhausted, widgets below the Models frame squeeze to zero pixels **silently** — no error, the widget simply doesn't render. If you add model rows, bump `WINDOW_SIZE` height accordingly and keep model descriptions to one or two lines.

## Key Technical Decisions

- **Tkinter** chosen for GUI: stdlib-only, no extra dep, native Windows look.
- **BEN2 installed from GitHub zip URL** (pinned commit) to avoid requiring Git on user's PATH.
- **DPI passthrough**: `src.info.get("dpi", (300, 300))` read per-image and passed to `Image.save()`.
- **Embedded window icon**: base64-encoded ICO constant (`LEMON_ICO_B64`) written to a temp file at startup via `iconbitmap()`. Must be a true multi-resolution ICO (16/32/48 px) — a single large image wrapped in ICO format renders blank at title-bar size on Windows.
- **`with Image.open(path):` context manager** used throughout to release file handles promptly (important for large Windows batches).
- **Title bar CPU/GPU indicator**: `_enable_run()` appends `(GPU)` or `(CPU)` based on `torch.cuda.is_available()`.

## Adding a New Model

1. Add one entry to `MODELS` dict with all required fields including `cache_path` and `cache_is_dir`.
2. If using `rembg` backend — no other changes needed.
3. If new backend: add a load block and inference branch in `_process()`.
4. If install is fragile (e.g. deps lack wheels for newer Python): follow the `_try_load_inspyrenet()` pattern (lazy import, prompt-to-install, return `None` on failure). Do **not** add it to `REQUIRED_DEPS`.
5. Verify the model license is permissive (MIT/Apache-2.0); exclude any CC BY-NC.
6. Check whether adding a row requires bumping `WINDOW_SIZE` (see UI Layout Constraint above).

## Known Issues

- **InSPyReNet on Python 3.14** — `stringzilla` has no 3.14 wheel as of May 2026; install fails. The lazy-load pattern means the other six models are unaffected. Revisit when stringzilla ships 3.14 wheels.
- **First-run download sizes** — PyTorch CPU ~250 MB, each rembg model ~900 MB, BEN2 ~400 MB. Total first-run footprint can be several GB.
- **Python 3.14 is bleeding-edge** — most ML libraries support it but transitive deps may not. Suggest Python 3.12 if installs fail.
- **BiRefNet-Portrait on group photos** — model was trained on single-subject portraits; behaviour on groups is unpredictable.

## Version Bumps

Edit `__version__` constant in the main file, update `README.md` and `SPEC.md`, add a version history entry in `SPEC.md`, and use the version in the Git commit message.
