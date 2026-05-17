# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**The Electric Kool-Aid Background Remover (v3.11)** — a free, local, privacy-respecting Windows desktop app that removes image backgrounds using multiple AI models. Everything runs locally; no cloud, no subscription.

- **Single-file app:** `the-electric-kool-aid-background-remover.py` (all logic in one file)
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

- `launch.bat` — Detects Python, offers embedded Python 3.12 install, runs `gpu_setup.py`, launches app
- `gpu_setup.py` — Detects NVIDIA GPU via `nvidia-smi`, manages PyTorch CPU/GPU switching
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

### Threading Model

- Dependency install and image processing run on **daemon background threads**
- All UI updates marshalled back to main thread via `self.after(0, callback)`
- Block on `threading.Event` when a worker thread needs a dialog answer from the user

### Models (`MODELS` dict)

Each entry has: display name, backend, rembg identifier (if applicable), description, default-on state, cache path, cache-is-dir flag.

| Model | Backend | Default |
|-------|---------|---------|
| BEN2 | direct import (`ben2`) | On |
| BiRefNet-General | rembg | On |
| BiRefNet-HR | rembg | Off |
| BiRefNet-Portrait | rembg | Off |
| BiRefNet-Massive | rembg | Off |
| BiRefNet-Lite | rembg | Off |
| InSPyReNet | direct import (`transparent_background`), lazy | Off |

All models are MIT-licensed. BRIA-RMBG was deliberately excluded (CC BY-NC 4.0 forbids commercial use).

### InSPyReNet Lazy-Load Pattern

InSPyReNet is **not** in startup deps. `_try_load_inspyrenet()` tries the import, prompts to install if missing, and returns `None` on failure — processing continues with other models. On Python 3.14, `stringzilla` (transitive dep) has no wheel and the install fails; advise users to untick InSPyReNet or switch to Python 3.12.

### Output Conventions

- Output folders: `{ModelDisplayName}-{FORMAT}/` inside the input folder (e.g., `BEN2-PNG/`)
- Output filenames: `{input_stem}_{ModelDisplayName}{ext}` (e.g., `photo_01_BEN2.png`)
- Formats: PNG, TIFF (LZW-compressed), WebP (lossless). All preserve alpha channel and source DPI (default 300 if missing).
- **WebP hard limit: 16383px per axis.** Validated upfront; user is blocked and shown offending files.
- Skip-existing pattern: if output file exists, skip it (allows safe resume of interrupted batches).

## Key Technical Decisions (from SPEC.md)

- **Tkinter** chosen for GUI: stdlib-only, no extra dep, native Windows look.
- **BEN2 installed from GitHub zip URL** to avoid requiring Git on user's PATH.
- **DPI passthrough**: read per-image, default 300 if missing, passed to output save.
- **Embedded window icon**: base64-encoded ICO constant written to temp file at startup (PNG failed at title-bar size on Windows).
- **`with Image.open(path):` context manager** used throughout to release file handles promptly (important for large Windows batches).

## Adding a New Model

1. Add one entry to `MODELS` dict with all required fields.
2. If using `rembg` backend — no other changes needed.
3. If new backend: add a load block and inference branch in `_process()`.
4. If install is fragile: follow the `_try_load_inspyrenet()` pattern (lazy import, prompt-to-install, return `None` on failure).
5. Verify the model license is permissive (MIT/Apache-2.0); exclude any CC BY-NC.

## Version Bumps

Edit `__version__` constant in the main file, update `README.md` and `SPEC.md`, add a version history entry in SPEC.md, and use the version in the Git commit message.
