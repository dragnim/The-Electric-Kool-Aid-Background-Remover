"""
The Electric Kool-Aid Background Remover  (v3.7.1)
==================================================

A single-file Tkinter app that runs background removal across multiple models
(BEN2, BiRefNet-General/HR/Portrait/Massive/Lite) and saves outputs into
labelled subfolders inside the chosen input location.

To run:
    py the-electric-kool-aid-background-remover.py

On first launch the app will detect missing Python dependencies and offer to
install them (rembg, BEN2 from GitHub, torch, opencv-python, Pillow).

Requires:
    - Python 3.12+ on Windows (Python 3.14 verified working with current
      PyTorch wheels).
    - Git installed and on PATH (BEN2 ships from GitHub, not PyPI).
"""

import os
import sys
import subprocess
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

# --- Constants ---------------------------------------------------------------

__version__ = "3.7.1"

APP_TITLE = f"The Electric Kool-Aid Background Remover v{__version__}"
WINDOW_SIZE = "780x820"

IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}

# WebP has a hard canvas-size limit baked into the format. Images larger
# than this on either axis cannot be encoded as WebP.
WEBP_MAX_DIM = 16383

# The embedded window icon (LEMON_ICO_B64) lives at the bottom of the file —
# it's bulky base64 and would dominate the top of the source if placed here.

# import-name -> pip-install-target (versions pinned to match requirements.txt)
REQUIRED_DEPS = {
    "PIL":   "Pillow==12.2.0",
    "torch": "torch==2.12.0",
    "cv2":   "opencv-python==4.13.0.92",
    "rembg": "rembg[cpu]==2.0.75",
    "ben2":  "git+https://github.com/PramaLLC/BEN2.git@2c99a5da477b5523585bfa5c893888a6e818a8f6",
}

# Display name -> metadata
MODELS = {
    "BEN2": {
        "backend": "ben2",
        "rembg_name": None,
        "description": "Strong on hair edges and 4K images. Confidence-guided matting refines low-confidence pixels. MIT licence.",
        "default_on": True,
    },
    "BiRefNet-General": {
        "backend": "rembg",
        "rembg_name": "birefnet-general",
        "description": "Reliable general-purpose default. Strong fine-edge detection across a wide variety of subjects. MIT licence.",
        "default_on": True,
    },
    "BiRefNet-HR": {
        "backend": "rembg",
        "rembg_name": "birefnet-hrsod",
        "description": "High-resolution variant (HRSOD), trained for sharp boundaries on large images. Useful for 300 DPI source material where General softens fine edges. MIT licence.",
        "default_on": False,
    },
    "BiRefNet-Portrait": {
        "backend": "rembg",
        "rembg_name": "birefnet-portrait",
        "description": "Tuned for single-person portraits. May behave unpredictably on groups, animals, or non-human subjects.",
        "default_on": False,
    },
    "BiRefNet-Massive": {
        "backend": "rembg",
        "rembg_name": "birefnet-massive",
        "description": "Same architecture as General, trained on a larger dataset. Often slightly better quality at higher compute cost.",
        "default_on": False,
    },
    "BiRefNet-Lite": {
        "backend": "rembg",
        "rembg_name": "birefnet-general-lite",
        "description": "Faster, lower-memory variant of General. Slightly lower quality; useful for quick passes or weaker hardware.",
        "default_on": False,
    },
}


# --- Dependency handling -----------------------------------------------------

def check_missing_deps():
    """Return list of (module_name, pip_target) for any missing dependency."""
    missing = []
    for module, pip_target in REQUIRED_DEPS.items():
        try:
            __import__(module)
        except ImportError:
            missing.append((module, pip_target))
    return missing


def install_dep(pip_target, log_func):
    """Run `pip install <target>` and stream stdout/stderr to log_func."""
    log_func(f"  pip install {pip_target}")
    proc = subprocess.Popen(
        [sys.executable, "-m", "pip", "install", pip_target],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    for line in proc.stdout:
        log_func(f"    {line.rstrip()}")
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"pip install {pip_target} failed (exit {proc.returncode})")


# --- App ---------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry(WINDOW_SIZE)
        self._set_icon()
        self.deps_ready = False
        self._dots_job = None       # after() id for the processing-dots animation
        self._cancel_requested = False  # set True by Cancel button
        self._last_input_dir = None     # populated after each run for Open Folder

        self._build_ui()
        threading.Thread(target=self._check_deps, daemon=True).start()

    def _set_icon(self):
        """Set the window icon from the embedded ICO via a temp file.

        Windows needs an actual .ico file path for iconbitmap() to produce a
        good title-bar AND taskbar icon (iconphoto with a PNG sets only the
        title bar, and even that renders poorly at small sizes when the
        source PNG has heavy alpha). The .ico contains the canonical
        multi-resolution Windows icon, so we just write it to disk once and
        point Tk at the file.
        """
        try:
            import base64
            import tempfile
            import atexit
            ico_bytes = base64.b64decode(LEMON_ICO_B64)
            fd, path = tempfile.mkstemp(suffix=".ico", prefix="kabr_")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(ico_bytes)
            except Exception:
                os.close(fd)
                raise
            self._icon_path = path
            # Clean up the temp file when the process exits.
            atexit.register(lambda p=path: os.path.exists(p) and os.remove(p))
            # iconbitmap on Windows reads the ICO and Windows handles the
            # title-bar/taskbar/Alt-Tab variants from a single call.
            self.iconbitmap(default=path)
        except Exception:
            # Icon failure is cosmetic — never let it stop the app starting.
            pass

    # ---- UI construction ---------------------------------------------------

    def _build_ui(self):
        pad = {"padx": 10, "pady": 5}

        # Input (folder or single image)
        f = ttk.LabelFrame(self, text="Input")
        f.pack(fill="x", **pad)
        self.input_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.input_var).pack(
            side="left", fill="x", expand=True, padx=5, pady=5)
        ttk.Button(f, text="Image\u2026", command=self._browse_image,
                   width=10).pack(side="right", padx=(0, 5), pady=5)
        ttk.Button(f, text="Folder\u2026", command=self._browse_folder,
                   width=10).pack(side="right", padx=(5, 0), pady=5)

        # Output format
        f = ttk.LabelFrame(self, text="Output format")
        f.pack(fill="x", **pad)
        self.format_var = tk.StringVar(value="PNG")
        self.format_descriptions = {
            "PNG": "Lossless. Preserves DPI. Universally supported.",
            "TIFF": "Lossless (LZW). Preserves DPI. Best for print workflows.",
            "WebP": "Lossless. ~30% smaller than PNG. Max 16383px per axis.",
        }
        fmt_row = ttk.Frame(f)
        fmt_row.pack(fill="x", padx=10, pady=5)
        ttk.Combobox(fmt_row, textvariable=self.format_var, state="readonly",
                     values=list(self.format_descriptions.keys()),
                     width=12).pack(side="left")
        self.format_desc_var = tk.StringVar(
            value=self.format_descriptions["PNG"])
        ttk.Label(fmt_row, textvariable=self.format_desc_var,
                  foreground="gray50", font=("", 9)).pack(
            side="left", padx=10)
        self.format_var.trace_add("write", self._on_format_change)

        # Models
        f = ttk.LabelFrame(self, text="Models (select one or more)")
        f.pack(fill="x", **pad)
        self.model_vars = {}
        for name, info in MODELS.items():
            sub = ttk.Frame(f)
            sub.pack(fill="x", padx=10, pady=4)
            var = tk.BooleanVar(value=info["default_on"])
            self.model_vars[name] = var
            ttk.Checkbutton(sub, text=name, variable=var).pack(anchor="w")
            ttk.Label(sub, text=info["description"], foreground="gray50",
                      wraplength=700, justify="left",
                      font=("", 9)).pack(anchor="w", padx=22)

        # Run / Cancel buttons
        btn_row = ttk.Frame(self)
        btn_row.pack(pady=10)
        self.run_btn = ttk.Button(btn_row, text="Run", command=self._run,
                                  state="disabled")
        self.run_btn.pack(side="left", padx=5)
        self.cancel_btn = ttk.Button(btn_row, text="Cancel",
                                     command=self._cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=5)

        # Progress bar (indeterminate; runs while processing)
        self.progress = ttk.Progressbar(self, mode="indeterminate", length=300)
        self.progress.pack(pady=(0, 10))

        # Log
        f = ttk.LabelFrame(self, text="Output")
        f.pack(fill="both", expand=True, **pad)
        log_toolbar = ttk.Frame(f)
        log_toolbar.pack(fill="x", padx=5, pady=(5, 0))
        ttk.Button(log_toolbar, text="Copy Output",
                   command=self._copy_log, width=14).pack(side="right")
        self.open_folder_btn = ttk.Button(
            log_toolbar, text="Open Output Folder",
            command=self._open_output_folder, state="disabled", width=20)
        self.open_folder_btn.pack(side="right", padx=(0, 5))
        self.log = scrolledtext.ScrolledText(f, height=12,
                                             font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, padx=5, pady=5)

        # Status bar
        self.status_var = tk.StringVar(value="Starting\u2026")
        ttk.Label(self, textvariable=self.status_var, anchor="w",
                  relief="sunken").pack(side="bottom", fill="x")

    # ---- Thread-safe UI helpers --------------------------------------------

    def _log(self, msg):
        self.after(0, self._log_now, msg)

    def _log_now(self, msg):
        self.log.insert("end", msg + "\n")
        self.log.see("end")

    def _copy_log(self):
        """Copy the entire log contents to the clipboard."""
        text = self.log.get("1.0", "end-1c")
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        # On Windows the clipboard is owned by the process, so force Tk to
        # hand the data over to the OS clipboard before the app exits.
        self.update()
        self._status("Log copied to clipboard.")

    def _cancel(self):
        """Request cancellation of the current run."""
        self._cancel_requested = True
        self._log("Cancellation requested — stopping after current image.")
        self._status("Cancelling\u2026")
        self.after(0, lambda: self.cancel_btn.config(state="disabled"))

    def _open_output_folder(self):
        """Open the last input directory in Windows Explorer."""
        if self._last_input_dir and Path(self._last_input_dir).exists():
            os.startfile(self._last_input_dir)
        else:
            self._status("No output folder to open yet.")

    def _status(self, msg):
        self.after(0, self.status_var.set, msg)

    def _on_format_change(self, *_):
        """Update the format-description label when the dropdown changes."""
        fmt = self.format_var.get()
        self.format_desc_var.set(self.format_descriptions.get(fmt, ""))

    def _start_progress(self, base_status):
        """Start the indeterminate progress bar and dots-cycling status."""
        self._status_base = base_status
        self._dots_state = 0
        self.after(0, self.progress.start, 100)  # 100ms per step
        self._tick_dots()

    def _stop_progress(self, final_status=""):
        """Stop the progress bar and dots animation."""
        if self._dots_job is not None:
            self.after_cancel(self._dots_job)
            self._dots_job = None
        self.after(0, self.progress.stop)
        if final_status:
            self._status(final_status)

    def _tick_dots(self):
        """Cycle the status bar text through base, base+'.', base+'..', base+'...'."""
        dots = "." * self._dots_state
        self.status_var.set(f"{self._status_base}{dots}")
        self._dots_state = (self._dots_state + 1) % 4
        self._dots_job = self.after(500, self._tick_dots)

    def _set_status_base(self, base):
        """Update the rolling-dots base message mid-run."""
        self._status_base = base

    def _enable_run(self):
        self.deps_ready = True
        self.after(0, lambda: self.run_btn.config(state="normal"))
        self._status("Ready.")

    def _ask_yesno(self, title, message):
        """Run messagebox.askyesno on the main thread, wait for the answer."""
        result = {}
        event = threading.Event()
        def ask():
            result["answer"] = messagebox.askyesno(title, message)
            event.set()
        self.after(0, ask)
        event.wait()
        return result["answer"]

    # ---- Browse ------------------------------------------------------------

    def _browse_folder(self):
        d = filedialog.askdirectory(title="Select input folder")
        if d:
            self.input_var.set(d)

    def _browse_image(self):
        types = [
            ("Images", "*.jpg *.jpeg *.png *.webp *.tif *.tiff *.bmp"),
            ("All files", "*.*"),
        ]
        f = filedialog.askopenfilename(title="Select input image",
                                       filetypes=types)
        if f:
            self.input_var.set(f)

    # ---- Dependency check --------------------------------------------------

    def _check_deps(self):
        self._status("Checking dependencies\u2026")
        self._log("Checking required dependencies\u2026")
        try:
            missing = check_missing_deps()
            if not missing:
                self._log("All dependencies present.")
                self._enable_run()
                return

            names = ", ".join(t for _, t in missing)
            ok = self._ask_yesno(
                "Install dependencies?",
                f"The following Python packages need to be installed:\n\n"
                f"{names}\n\nInstall now? (large download on first run)"
            )
            if not ok:
                self._log("User declined dependency install.")
                self._status("Missing dependencies.")
                return

            self._status("Installing dependencies\u2026")
            self._log(f"\nInstalling {len(missing)} missing package(s)\u2026")
            for module, target in missing:
                self._log(f"\n[{module}]")
                install_dep(target, self._log)

            self._log("\nAll dependencies installed.")
            self._enable_run()
        except Exception as e:
            self._log(f"\nDependency check failed: {e}")
            self._status("Error during dependency check.")

    # ---- Run ---------------------------------------------------------------

    def _run(self):
        if not self.deps_ready:
            return

        path = self.input_var.get().strip()
        if not path:
            messagebox.showerror(
                "Missing input",
                "Select an input folder or a single image.")
            return
        input_path = Path(path)
        if not input_path.exists():
            messagebox.showerror("Invalid path",
                                 f"Path does not exist:\n{input_path}")
            return

        # Resolve input to a list of images and a "base directory" where
        # output subfolders will live.
        if input_path.is_dir():
            input_dir = input_path
            images = sorted(p for p in input_dir.iterdir()
                            if p.is_file() and p.suffix.lower() in IMG_EXTS)
            if not images:
                messagebox.showerror(
                    "No images found",
                    f"No images found in:\n{input_dir}\n\n"
                    f"Supported extensions: {', '.join(sorted(IMG_EXTS))}"
                )
                return
        elif input_path.is_file():
            if input_path.suffix.lower() not in IMG_EXTS:
                messagebox.showerror(
                    "Unsupported file",
                    f"{input_path.name} isn't a supported image type.\n\n"
                    f"Supported extensions: {', '.join(sorted(IMG_EXTS))}"
                )
                return
            input_dir = input_path.parent
            images = [input_path]
        else:
            messagebox.showerror("Invalid path",
                                 f"Not a file or folder:\n{input_path}")
            return

        selected = [name for name, v in self.model_vars.items() if v.get()]
        if not selected:
            messagebox.showerror("No models selected",
                                 "Select at least one model.")
            return

        fmt = self.format_var.get()

        # WebP has a hard 16383px-per-axis limit. Validate upfront so we
        # don't surprise the user partway through a run.
        if fmt == "WebP":
            oversized = self._find_webp_oversized(images)
            if oversized:
                lines = [
                    f"  - {p.name}  ({w}\u00d7{h})"
                    for p, w, h in oversized
                ]
                messagebox.showerror(
                    "Image too large for WebP",
                    f"WebP cannot encode images larger than "
                    f"{WEBP_MAX_DIM}px on either axis. "
                    f"{len(oversized)} image(s) exceed this:\n\n"
                    + "\n".join(lines)
                    + "\n\nChoose PNG or TIFF, or remove these images."
                )
                return

        if not messagebox.askyesno(
            "Confirm run",
            f"Process {len(images)} image(s)?\n\n"
            f"Models: {', '.join(selected)}\n"
            f"Format: {fmt}\n\n"
            f"Output folders will be created in:\n{input_dir}"
        ):
            return

        self.run_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.open_folder_btn.config(state="disabled")
        self._cancel_requested = False
        self._last_input_dir = str(input_dir)
        self._start_progress("Processing")
        threading.Thread(
            target=self._process,
            args=(input_dir, images, selected, fmt),
            daemon=True,
        ).start()

    def _find_webp_oversized(self, images):
        """Return [(path, width, height), ...] for any image too big for WebP."""
        from PIL import Image
        oversized = []
        for p in images:
            try:
                with Image.open(p) as im:
                    w, h = im.size
                if w > WEBP_MAX_DIM or h > WEBP_MAX_DIM:
                    oversized.append((p, w, h))
            except Exception:
                # Unreadable images will get caught and logged during the
                # main run; don't block the pre-flight check on them.
                pass
        return oversized

    # ---- Processing --------------------------------------------------------

    def _process(self, input_dir, images, selected_models, fmt):
        import time
        try:
            from PIL import Image

            # fmt is one of "PNG", "TIFF", "WebP" (from the dropdown).
            fmt_meta = {
                "PNG":  (".png",  "PNG"),
                "TIFF": (".tif",  "TIFF"),
                "WebP": (".webp", "WebP"),
            }
            ext, suffix = fmt_meta[fmt]

            # folder_name -> (backend, model_name, display_name)
            targets = {}
            for name in selected_models:
                info = MODELS[name]
                targets[f"{name}-{suffix}"] = (
                    info["backend"], info["rembg_name"], name)

            out_dirs = {n: input_dir / n for n in targets}

            self._log("\n=== Run started ===")
            self._log(f"Input:  {input_dir}")
            self._log(f"Format: {suffix}")
            self._log(f"Models: {', '.join(selected_models)}")
            self._log(f"Images: {len(images)}\n")

            ben2_model = None
            rembg_sessions = {}

            if any(t[0] == "ben2" for t in targets.values()):
                self._log("Loading BEN2\u2026")
                import torch
                from ben2 import AutoModel
                device = torch.device("cuda" if torch.cuda.is_available()
                                      else "cpu")
                ben2_model = AutoModel.from_pretrained(
                    "PramaLLC/BEN2").to(device).eval()
                self._log(f"  BEN2 on {device}")

            from rembg import remove, new_session
            for folder_name, (backend, model_name, _display) in targets.items():
                if backend == "rembg":
                    self._log(f"Loading {model_name}\u2026")
                    rembg_sessions[folder_name] = new_session(model_name)

            self._log("")
            t_total = time.time()
            for idx, img_path in enumerate(images, 1):
                if self._cancel_requested:
                    self._log("\n=== Cancelled by user ===")
                    break
                base = img_path.stem
                self._log(f"[{idx}/{len(images)}] {img_path.name}")
                self._set_status_base(
                    f"Processing image {idx}/{len(images)}")

                try:
                    with Image.open(img_path) as src:
                        dpi = src.info.get("dpi", (300, 300))
                        image = src.convert("RGB")
                except Exception as e:
                    self._log(f"  ! Could not open: {e}")
                    continue

                for folder_name, (backend, model_name, display_name) in targets.items():
                    self._set_status_base(
                        f"Image {idx}/{len(images)} \u2013 {display_name}")
                    out_path = out_dirs[folder_name] / f"{base}_{display_name}{ext}"
                    if out_path.exists():
                        self._log(f"  {folder_name}: skipped (exists)")
                        continue
                    try:
                        t = time.time()
                        if backend == "ben2":
                            result = ben2_model.inference(
                                image, refine_foreground=True)
                        else:
                            result = remove(
                                image, session=rembg_sessions[folder_name])
                        out_dirs[folder_name].mkdir(parents=True, exist_ok=True)
                        if ext == ".tif":
                            result.save(out_path, format="TIFF",
                                        compression="tiff_lzw", dpi=dpi)
                        elif ext == ".webp":
                            # lossless=True preserves edge quality; quality=100
                            # tunes the lossless encoder for best compression.
                            result.save(out_path, format="WEBP",
                                        lossless=True, quality=100, dpi=dpi)
                        else:
                            result.save(out_path, dpi=dpi)
                        self._log(f"  {folder_name}: "
                                  f"done in {time.time() - t:.1f}s")
                    except Exception as e:
                        self._log(f"  {folder_name}: FAILED - {e}")

            total = time.time() - t_total
            m, s = divmod(int(total), 60)
            self._log(f"\n=== Finished in {m}m {s}s ===")
            self._stop_progress("Done.")
        except Exception as e:
            self._log(f"\nERROR: {e}")
            self._stop_progress(f"Error: {e}")
        finally:
            def _restore_buttons():
                self.run_btn.config(state="normal")
                self.cancel_btn.config(state="disabled")
                if self._last_input_dir:
                    self.open_folder_btn.config(state="normal")
            self.after(0, _restore_buttons)


# --- Embedded window icon ----------------------------------------------------
# Multi-resolution Windows .ico for the title bar and taskbar. Base64 of a
# 96x97 lemon graphic from the Dyalog assets. ~38 KB raw / ~51 KB encoded.
# Kept at the bottom of the file so it doesn't dominate the constants block.

LEMON_ICO_B64 = (
    "AAABAAMAEBAAAAEAIABoBAAANgAAACAgAAABACAAKBEAAJ4EAAAwMAAAAQAgAGgmAADGFQAA"
    "KAAAABAAAAAgAAAAAQAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAE3M/wpMzP9oTcv/t03M/+FMzP/tTcz/4EzM/8JNy/+ZTMv/oVDP/yAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAEzL/0BNzP/hTcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9Oyv9IAAAAAAAAAAAAAAAAAAAAAEzN/1dMzP/6Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcr/dAAAAAAAAAAAAAAAAEzJ/zlMzP/6Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//0zN/8VSuHoZUrZ2HAD//wFNzf/QTcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9Ny//yVLN1RlWyd81NyfNCTcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//1WyeGBVsnf/"
    "Ubyt5U3M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03N"
    "//RVsnecVbJ3/1WyeP9PxuD/Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9MzP/MVbJ3zVWyd/9Vsnf/U7mc/03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcv/hVWyd9JVsnf/VbJ3/1Wyef9Nyvj/Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz/+UjH/yBUsnabVbJ3/1Wyd/9Vsnf/Tsfm/03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//07M/30AAAAAV7V5JlWyd/VVsnf/"
    "VbJ3/07H5f9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M/5sAgP8CAAAAAAAA"
    "AABStHhEVbJ33lWzff9Ny/n/Tcz//03M//9NzP//Tcz//03M//9NzP//Tcv/6EzM/2QAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAFOxdjRVsXffRJ1p+T+egP9Drar/RrXA/0a2w/9EsLP/Qq2qpUC/"
    "/wgAAAAAAAAAAAAAAAAAAAAAU7J3VlWzd65VsnfQVbN0OTuRWkE7kVuUOpFbqzyRXJ47kVx0"
    "PJFbWjqRW20AAAAAAAAAAAAAAAAAAAAAAAAAAFSyd3pStHhEAICAAgAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAKAAAACAA"
    "AABAAAAAAQAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEDU/wxNzP9QTMv/jUzL"
    "/7VNzP/RTMz/3E3N/9pNzP/NTcv/t03L/5lNy/9wTsz/QUrJ/yZMzP88Tcv/SWbM/wUAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAE3M"
    "/yhNzP+fTcz/9E3M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tc3/ewAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAFXG/wlMzP+MTsz/+k3M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9Ny/+eAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABMyP8lTsz/0k3M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "/4EAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAATMv/Nk3L/+xNzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tsz/tAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAEzQ/zZNzP/xTcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP/9TMz/HgAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAABKzv8fTcz/6k3M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9Mzf9sAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAID/AkzM/8JNzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//0zM/6oAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AABLy/9jTcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz/1gAA"
    "AABSsnVmVbF3cgAAAAAAAAAAM8z/BU3N/+BNzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9Nzf/zAAAAAFWzd41Vsnf+U7N2UAAAAABNzP9QTcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//8AAAAAVbF2ilWyd/9Vsnfn"
    "WbNzFE3L/6NNzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//wAAAABUsXamVbJ3/1Wyd/9UsnizTcv+4k3M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9MzP/3AAAAAFWyd9pVsnf/VbJ3/1Wyd/9QwMH/Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M/91Vs3sbVbJ2/lWy"
    "d/9Vsnf/VbJ3/1Wze/9Ox+n/Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//TMv/tVS0d1hVsnf/VbJ3/1Wyd/9Vsnf/VbJ3/1O5m/9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP9+VLJ3i1Wyd/9Vsnf/VbJ3/1Wyd/9Vsnf/"
    "VbJ3/0/F3f9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//0rM/zdWs3iq"
    "VbJ3/1Wyd/9Vsnf/VbJ3/1Wyd/9Vsnf/Urul/03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9MzP/cAP//AVWzeLFVsnf/VbJ3/1Wyd/9Vsnf/VbJ3/1Wyd/9Us37/Tcv8/03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//0vM/3MAAAAAVLN3mlWyd/9Vsnf/VbJ3/1Wy"
    "d/9Vsnf/VbJ3/1Wyd/9Ox+b/Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9MzP/mQL//DAAA"
    "AABVsnZjVbJ3/1Wyd/9Vsnf/VbJ3/1Wyd/9Vsnf/VbJ3/1DE0/9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//0zN/1cAAAAAAAAAAE2zcxRVsXf2VbJ3/1Wyd/9Vsnf/VbJ3/1Wyd/9Vsnf/"
    "UMHJ/03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP+fAAAAAAAAAAAAAAAAAAAAAFWxdo1Vsnf/"
    "VbJ3/1Wyd/9Vsnf/VbJ3/1Wyd/9Qwcf/Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz/ukm2/wcAAAAA"
    "AAAAAAAAAAAAAAAATrF2DVWzd9lVsnf/VbJ3/1Wyd/9Vsnf/VbJ3/1DD0f9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03N/6w5xv8JAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAUK91I1Wydt5Vsnf/VbJ3/1Wy"
    "d/9Vsnf/Tsjt/03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//hMzf91AP//AQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAS7R4EVayd45Vs3ftVbJ3/1S2jv9Ny/v/Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03L//xNzP+mTs3/JAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEC/gARUsXaXVbJ3/1Owd/9Am3D/"
    "QKKK/0W0vv9Kw+j/Tcz+/03M//9NzP//Tcz//03M//9NzP//TMr6/0rC5etMzP95SMf/IAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABSrXYc"
    "VbJ3sFWyd/9VsnfnQZdh6TuRXP87kVz/O5Fc/zuRXP88lGb/Ppx7/0ChiP9Aoov/QJ+F/z6a"
    "df87kmD/O5Fb+zmSWjYAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAABTsncrVLJ4kVWyd/VVsnf/VbJ2xFWydx46kFs1O5Fc0DuRXP87kVz/O5Fc/zuR"
    "XP87kVz/O5Fc/zuRXPk7kVzQO5BcsTqSW7g7kVzvOpFcrAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAABUsXiAVLJ22lWyd/9Vsnf/VbJ35VazdmhVqlUDAAAAAAAA"
    "AAAAAAAAN5BZFzuSXD06kltUOZJcWTyQW0w9kFkuJJJJBwAAAAAAAAAAAAAAACqAVQY9kmEV"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFSxd+NVsnfzVbN3tFSz"
    "dltJtm0HAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAARrl0C1WqgAYAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAKAAAADAAAABgAAAAAQAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAASbb/B07I/xdLzf8pTcv/T03L"
    "/3pMy/+eTcv/t03M/8RNzf/GTcv/wE7N/7FOzP+aTs3/gE7M/19Myf85UMz/I0fM/xlVzP8P"
    "TsT/DUfV/xJHzP8ZTsj/F1Wq/wMAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAEfV/xJNy/9TTMz/kE3M/8RNzf/uTcz//k3M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9Ny//8Tcz/503M/8lNzf+sTcv/pk3N/7ZMy//JTcz/xEzM/1oAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABA3/8ITMz/ZEzM/9JMzP/wTcz//k3M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//0zM/9JDyf8TAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM8z/BVDN"
    "/zNNzP+6Tcz//E3M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03N"
    "/99Ly/8iAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAABR0f8WTcv/e03L/+dNzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M/9hQz/8QAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAE7I/xdNy/+t"
    "Tc3/+E3M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//0zL/81V//8DAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAA//8BScX/I03L/8pNzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//07M/99QzP8jAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD//wFMyf85Tcz/zE3M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//ZMzf9rAID/AgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAEvS/yJNzP/NTs3//U3M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9OzP+rRMz/DwAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAR8b/Ek7N/8VNzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9MzP/gTdH/IQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAABJyP8OTc3/n03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP/8"
    "Tsv/RQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD//wFMyv9hTcz/803M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//TMv/gAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAEnI/xxMzP/ITcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcv/sgAAAAAAAAAAU7B5N1qzdSUAAAAAAAAAAAAAAAAAAAAAAAAAAEzM/3JNzP/8"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz/1wAAAABAv4AIVLF3xVWy"
    "d8xRs3cvAAAAAAAAAAAAAAAATsT/DU3M/+dNzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz/8gAAAABQr4AQVbN42VWyd/9Vs3iuUa55EwAAAAAAAAAATM3/a03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//wAAAABNs2YK"
    "VbJ311Wyd/9Vsnf5VLJ3dAAAAABVxv8JTcz/w03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//wAAAABVqoAMVbJ32FWyd/9Vsnf/VbJ38FeydjhMzv8v"
    "Tcz/5E3M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//wAA"
    "AABSrXMfVbF331Wyd/9Vsnf/VbJ3/1Wyd9BNw913Tcz/8k3M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//TMz/+AAAAABSsXc+VbJ36VWyd/9Vsnf/VbJ3/1Wx"
    "d/pRu6fpTsv5/E3M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tc3/3wAAAABWsXdlVbJ39lWyd/9Vsnf/VbJ3/1Wyd/9Vs33/UMPQ/03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//TMz/vlWqgAZVsXeQVbJ3/1Wyd/9Vsnf/"
    "VbJ3/1Wyd/9Vsnf/VLSB/07I7v9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//TMz/kFG8eRNVsne6VbJ3/1Wyd/9Vsnf/VbJ3/1Wyd/9Vsnf/VbJ3/1K6pP9Ny/j/"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//TMz/WlWydCFVsnbiVbJ3/1Wy"
    "d/9Vsnf/VbJ3/1Wyd/9Vsnf/VbJ3/1Szf/9Qw9L/Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9MzP/xT87/KlWzdjZVsnf8VbJ3/1Wyd/9Vsnf/VbJ3/1Wyd/9Vsnf/VbJ3/1Wy"
    "d/9SuqT/Tcr3/03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP/ETsj/F1Wydl1Vsnf/"
    "VbJ3/1Wyd/9Vsnf/VbJ3/1Wyd/9Vsnf/VbJ3/1Wyd/9UtIH/T8fj/03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//1MzP+MVdT/BlaydndVsnf/VbJ3/1Wyd/9Vsnf/VbJ3/1Wyd/9Vsnf/"
    "VbJ3/1Wyd/9Vsnf/Ub62/03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03N/+5Ly/9OAAAAAFSz"
    "dn9Vsnf/VbJ3/1Wyd/9Vsnf/VbJ3/1Wyd/9Vsnf/VbJ3/1Wyd/9Vsnf/VLWJ/03M/v9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03L/8tVzP8PAAAAAFayeHFVsnf/VbJ3/1Wyd/9Vsnf/VbJ3/1Wy"
    "d/9Vsnf/VbJ3/1Wyd/9Vsnf/VbJ3/07I6/9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//kzM/1oAAAAA"
    "AAAAAFWxdk5Vsnf/VbJ3/1Wyd/9Vsnf/VbJ3/1Wyd/9Vsnf/VbJ3/1Wyd/9Vsnf/VbJ3/0/D"
    "0P9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Ts3/u0m2/wcAAAAAAAAAAFWxdidVsnfuVbJ3/1Wyd/9Vsnf/"
    "VbJ3/1Wyd/9Vsnf/VbJ3/1Wyd/9Vsnf/VbJ3/1G/uv9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9Nzf/pS83/MwAA"
    "AAAAAAAAAAAAAFmzcxRVsne6VbJ3/1Wyd/9Vsnf/VbJ3/1Wyd/9Vsnf/VbJ3/1Wyd/9Vsnf/"
    "VbJ3/1K8rP9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//dMzf9/Sdv/BwAAAAAAAAAAAAAAAFWqVQNVsnd4VbF3+lWy"
    "d/9Vsnf/VbJ3/1Wyd/9Vsnf/VbJ3/1Wyd/9Vsnf/VbJ3/1K6o/9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//0zN/7hHxv8S"
    "AAAAAAAAAAAAAAAAAAAAAAAAAABRtHYpVbJ321Wyd/9Vsnf/VbJ3/1Wyd/9Vsnf/VbJ3/1Wy"
    "d/9Vsnf/VbJ3/1K6of9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP/9Tc3/ykPJ/xMAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/wAB"
    "VbF2bFWyd/xVsnf/VbJ3/1Wyd/9Vsnf/VbJ3/1Wyd/9Vsnf/VbJ3/1K7qP9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//xMzP+4Ssn/JgAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAASbZtB1Szd5pVsnf/VbJ3/1Wyd/9Vsnf/"
    "VbJ3/1Wyd/9Vsnf/VbJ3/1G+uP9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M/7NMzP8eAP//AQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAE2zcxRVs3euVbJ3+1Wyd/9Vsnf/VbJ3/1Wyd/9Vsnf/VbJ3/0/E1v9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//5MzP/tTc7/iFX//wMAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABStXMfVrJ3j1Wy"
    "du9Vsnf/VbJ3/1Wyd/9Vsnf/VLWH/03K+P9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M"
    "//9NzP//TMz/+k3M/7VLy/9OVdT/BgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAVcZxCVWzdjZUsXehVLJ38lWyd/9Vsnf/U7qi/07K"
    "9f9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//"
    "Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03N//1Nzf/KS87/TlHJ/xMA//8BAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAATbNmClSxd1hVs3faVbJ3/1WyeP9NrHz/QZ9+/0KonP9Iu8//S8Xr/0zI"
    "9f9Ny/z/Tcz//03M//9NzP//Tcz//03M//9NzP//Tcz//03M//9NzP//Tcv8/0zJ9v1My/zl"
    "Tc3/r0vO/05J2/8HAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABJtm0HVLJ3T1Wyd8pVsnf+"
    "VbJ3/0+qcf9Al2H/O5Fc/zuRXP87kl//Ppp1/0GkkP9DrKf/RbO7/0e5yf9IvNT/Sb/b/0nA"
    "3f9Jv9r/SLzU/0e5yv9Fs7v/Q6yn/0GkkvdAoYp4M8zMBQAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAFW4cRJWsneSVbJ37FWyd/9Vsnf/VbJ3vT+XYME7kVz/O5Fc/zuRXP87kVz/"
    "O5Fc/zuRXP87kV3/O5Nh/zyUZf88lmn/PZZr/z2XbP89lmv/PJZp/zyUZv87k2H/O5Fc/zuR"
    "XP86kFzNOY5eGwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFXGcQlVsnQhVbR3aVWyeORVsnf/VbJ3/1Wy"
    "d/RUsneeS7R4ETeRWiU7kVzDO5Fc9TuRXP87kVz/O5Fc/zuRXP87kVz/O5Fc/zuRXP87kVz/"
    "O5Fc/zuRXP47klz3O5Fb7TuRXOY7kFzkO5Jc6TuRXPY7kVz/OpBbZQAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFWqcQlSsnY4"
    "UrJ1ZlWyd5xVs3fZVbF3/VWyd/9Vsnf9VbN3zFOxd2VVqncPAAAAAAAAAAA3klscOZJbYjuQ"
    "W488kVyrO5FcwTuRXNE7kVzYO5Fc2TuRXM87kly/PJFcpzyRW4k6j1ppO5NbSTuTXTQ9kF4u"
    "OpBaPjuRW2g6kFyWOpJbVAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAFSzd55VsnfnVbJ39lWyd/9Vsnf/VbJ3/1Wzdu1TsHZ7"
    "Uq1zH////wEAAAAAAAAAAAAAAAAAAAAAAAAAADOZZgUziFUPOpddFjmXXhs7kF0eO5BdHjmO"
    "Xhs9kmEVO4liDUCAQAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFAgGAIQIBABAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFWz"
    "d+pVsnf/VbJ3+VWzd+pVsXbPU7J2e1mzcxQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFS0d1hVsXeQVbN3b1WyeEJLtHgRAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAD/AAFVqoAGAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAA=="
)


if __name__ == "__main__":
    App().mainloop()
