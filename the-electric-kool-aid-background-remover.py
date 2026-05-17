"""
The Electric Kool-Aid Background Remover  (v3.12)
==================================================

A single-file Tkinter app that runs background removal across multiple models
(BEN2, BiRefNet-General/HR/Portrait/Massive/Lite, InSPyReNet) and saves
outputs into labelled subfolders inside the chosen input location.

To run:
    py the-electric-kool-aid-background-remover.py

On first launch the app will detect missing Python dependencies and offer to
install them (rembg, BEN2, torch, opencv-python, Pillow). Git is NOT required
- BEN2 is installed from a GitHub zip archive rather than via git+https.

InSPyReNet is loaded lazily on first use rather than at startup, because the
`transparent-background` package has a heavy transitive dependency chain
(albumentations -> albucore -> stringzilla) that sometimes fails to build
on newer Python versions. Keeping it out of the startup deps means the
other six models always work, even when InSPyReNet's install fails.

Requires:
    - Python 3.12+ on Windows (Python 3.14 verified working with current
      PyTorch wheels for everything except InSPyReNet - see SPEC.md).
"""

import json
import os
import sys
import subprocess
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

try:
    from tkinterdnd2 import TkinterDnD as _TkinterDnD, DND_FILES as _DND_FILES
    _DND_AVAILABLE = True
except ImportError:
    _DND_AVAILABLE = False

# --- Constants ---------------------------------------------------------------

__version__ = "3.12"

APP_TITLE = f"The Electric Kool-Aid Background Remover v{__version__}"
WINDOW_SIZE = "780x880"

IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}

# WebP has a hard canvas-size limit baked into the format. Images larger
# than this on either axis cannot be encoded as WebP.
WEBP_MAX_DIM = 16383

SETTINGS_PATH = Path.home() / ".ekbr_settings.json"

# The embedded window icon (LEMON_ICO_B64) lives at the bottom of the file —
# it's bulky base64 and would dominate the top of the source if placed here.

# import-name -> pip-install-target (versions pinned to match requirements.txt)
def _rembg_pip_target():
    """Return the correct rembg pip target based on whether CUDA torch is installed."""
    try:
        import torch
        if torch.version.cuda:
            return "rembg[gpu]==2.0.75"
    except Exception:
        pass
    return "rembg[cpu]==2.0.75"


REQUIRED_DEPS = {
    "PIL":        "Pillow==12.2.0",
    "torch":      "torch==2.12.0",
    "cv2":        "opencv-python==4.13.0.92",
    "rembg":      None,   # determined at runtime by _rembg_pip_target()
    "ben2":       "https://github.com/PramaLLC/BEN2/archive/2c99a5da477b5523585bfa5c893888a6e818a8f6.zip",
    "tkinterdnd2": "tkinterdnd2",
}

# Display name -> metadata
MODELS = {
    "BEN2": {
        "backend": "ben2",
        "rembg_name": None,
        "description": "Strong on hair edges and 4K images. Confidence-guided matting refines low-confidence pixels.",
        "default_on": True,
        # Weights are downloaded by HuggingFace hub into a versioned folder
        # tree; presence of the top-level repo folder is enough to confirm
        # the model is cached.
        "cache_path": "~/.cache/huggingface/hub/models--PramaLLC--BEN2",
        "cache_is_dir": True,
    },
    "BiRefNet-General": {
        "backend": "rembg",
        "rembg_name": "birefnet-general",
        "description": "Reliable general-purpose default. Strong fine-edge detection across a wide variety of subjects.",
        "default_on": True,
        "cache_path": "~/.u2net/birefnet-general.onnx",
        "cache_is_dir": False,
    },
    "BiRefNet-HR": {
        "backend": "rembg",
        "rembg_name": "birefnet-hrsod",
        "description": "High-resolution variant (HRSOD), trained for sharp boundaries on large images. Useful for 300 DPI source material where General softens fine edges.",
        "default_on": False,
        "cache_path": "~/.u2net/birefnet-hrsod.onnx",
        "cache_is_dir": False,
    },
    "BiRefNet-Portrait": {
        "backend": "rembg",
        "rembg_name": "birefnet-portrait",
        "description": "Tuned for single-person portraits. May behave unpredictably on groups, animals, or non-human subjects.",
        "default_on": False,
        "cache_path": "~/.u2net/birefnet-portrait.onnx",
        "cache_is_dir": False,
    },
    "BiRefNet-Massive": {
        "backend": "rembg",
        "rembg_name": "birefnet-massive",
        "description": "Same architecture as General, trained on a larger dataset. Often slightly better quality at higher compute cost.",
        "default_on": False,
        "cache_path": "~/.u2net/birefnet-massive.onnx",
        "cache_is_dir": False,
    },
    "BiRefNet-Lite": {
        "backend": "rembg",
        "rembg_name": "birefnet-general-lite",
        "description": "Faster, lower-memory variant of General. Slightly lower quality; useful for quick passes or weaker hardware.",
        "default_on": False,
        "cache_path": "~/.u2net/birefnet-general-lite.onnx",
        "cache_is_dir": False,
    },
    "InSPyReNet": {
        "backend": "inspyrenet",
        "rembg_name": None,
        "description": "Different architecture entirely (pyramid-based salient object detection). Worth comparing alongside BEN2 and BiRefNet. Installed lazily on first use; see SPEC.md if install fails on Python 3.14.",
        "default_on": False,
        "cache_path": "~/.transparent-background/ckpt_base.pth",
        "cache_is_dir": False,
    },
}


# --- Model cache helpers -----------------------------------------------------

def _cache_path(model_name):
    """Return the resolved Path for a model's cache file or folder."""
    return Path(MODELS[model_name]["cache_path"]).expanduser()


def _is_cached(model_name):
    """Return True if the model's weights are present on disk."""
    p = _cache_path(model_name)
    if MODELS[model_name]["cache_is_dir"]:
        return p.is_dir()
    return p.is_file()


def _cache_size_mb(model_name):
    """Return the size of the model's cache in MB, or 0 if not cached."""
    p = _cache_path(model_name)
    if not p.exists():
        return 0
    if p.is_dir():
        total = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    else:
        total = p.stat().st_size
    return total / (1024 * 1024)


def _delete_cache(model_name):
    """Delete a model's cached weights. Returns (ok, message)."""
    import shutil
    p = _cache_path(model_name)
    if not p.exists():
        return False, "Not cached."
    try:
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        return True, f"Deleted {p}"
    except Exception as e:
        return False, f"Delete failed: {e}"


# --- System helpers ----------------------------------------------------------

def _get_total_ram_gb():
    """Return total physical RAM in GB via ctypes, or None on failure."""
    try:
        import ctypes
        class _MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength",                ctypes.c_ulong),
                ("dwMemoryLoad",            ctypes.c_ulong),
                ("ullTotalPhys",            ctypes.c_ulonglong),
                ("ullAvailPhys",            ctypes.c_ulonglong),
                ("ullTotalPageFile",        ctypes.c_ulonglong),
                ("ullAvailPageFile",        ctypes.c_ulonglong),
                ("ullTotalVirtual",         ctypes.c_ulonglong),
                ("ullAvailVirtual",         ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        stat = _MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(stat)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return stat.ullTotalPhys / (1024 ** 3)
    except Exception:
        return None


# --- Dependency handling -----------------------------------------------------

def check_missing_deps():
    """Return list of (module_name, pip_target) for any missing dependency."""
    missing = []
    for module, pip_target in REQUIRED_DEPS.items():
        # rembg pip target is determined at runtime based on CUDA availability
        if module == "rembg":
            pip_target = _rembg_pip_target()
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

_AppBase = _TkinterDnD.Tk if _DND_AVAILABLE else tk.Tk


class App(_AppBase):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry(WINDOW_SIZE)
        self._set_icon()
        self.deps_ready = False
        self._dots_job = None       # after() id for the processing-dots animation
        self._cancel_requested = False  # set True by Cancel button
        self._last_input_dir = None     # populated after each run for Open Folder
        self.model_status_vars = {}     # name -> StringVar for the status label
        self.model_trash_btns = {}      # name -> the trash Button widget

        self._build_ui()
        self._load_settings()
        self._setup_dnd()
        self._refresh_model_status()
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
        f = ttk.LabelFrame(self, text="Models")
        f.pack(fill="x", **pad)
        self.model_vars = {}
        for name, info in MODELS.items():
            sub = ttk.Frame(f)
            sub.pack(fill="x", padx=10, pady=4)

            # Top row: checkbox on the left, trash + status on the right.
            # Status and trash are packed right-to-left so trash stays flush
            # to the right edge and status sits just to its left.
            header = ttk.Frame(sub)
            header.pack(fill="x")

            var = tk.BooleanVar(value=info["default_on"])
            self.model_vars[name] = var
            ttk.Checkbutton(header, text=name, variable=var).pack(
                side="left", anchor="w")

            # Trash button — always present, enabled/disabled by cache state.
            # Use a closure to capture name correctly in the loop.
            def _make_trash_cmd(n):
                return lambda: self._trash_model(n)

            trash_btn = ttk.Button(header, text="✕", width=2,
                                   command=_make_trash_cmd(name))
            trash_btn.pack(side="right", padx=(4, 0))
            self.model_trash_btns[name] = trash_btn

            # Status label — shows "Ready  X MB" or "Not downloaded".
            status_var = tk.StringVar(value="\u2014")
            self.model_status_vars[name] = status_var
            ttk.Label(header, textvariable=status_var,
                      foreground="gray50", font=("", 9)).pack(
                side="right", padx=(0, 6))

            # Description row.
            ttk.Label(sub, text=info["description"], foreground="gray50",
                      wraplength=680, justify="left",
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

        # Progress bar (indeterminate; hidden until a run starts)
        self.progress = ttk.Progressbar(self, mode="indeterminate", length=300)
        self.progress.pack(pady=(0, 10))
        self.progress.pack_forget()  # hidden until processing starts

        # Log
        f = ttk.LabelFrame(self, text="Log")
        f.pack(fill="both", expand=True, **pad)
        log_toolbar = ttk.Frame(f)
        log_toolbar.pack(fill="x", padx=5, pady=(5, 0))
        ttk.Button(log_toolbar, text="Copy Log",
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

    # ---- Model cache status -------------------------------------------------

    def _refresh_model_status(self):
        """Update every model's status label and trash button state.

        Safe to call from any thread - marshals UI updates via after(0).
        Does only filesystem checks (no imports), so it's fast.
        """
        for name in MODELS:
            cached = _is_cached(name)
            if cached:
                mb = _cache_size_mb(name)
                text = f"Ready  {mb:.0f} MB"
                trash_state = "normal"
            else:
                text = "Not downloaded"
                trash_state = "disabled"
            # Capture loop vars correctly.
            def _apply(n=name, t=text, s=trash_state):
                self.model_status_vars[n].set(t)
                self.model_trash_btns[n].config(state=s)
            self.after(0, _apply)

    def _trash_model(self, name):
        """Ask for confirmation then delete a model's cached weights."""
        mb = _cache_size_mb(name)
        ok = messagebox.askyesno(
            "Delete model weights?",
            f"Delete the cached weights for {name}?\n\n"
            f"This will free approximately {mb:.0f} MB of disk space.\n"
            f"The weights will be re-downloaded automatically next time\n"
            f"you run this model.\n\n"
            f"Location: {_cache_path(name)}"
        )
        if not ok:
            return
        success, msg = _delete_cache(name)
        if success:
            self._log(f"[cache] {name}: weights deleted ({mb:.0f} MB freed).")
            self._status(f"{name} weights deleted.")
        else:
            self._log(f"[cache] {name}: delete failed — {msg}")
            self._status(f"Delete failed: {msg}")
        # Refresh status regardless so the UI reflects current state.
        self._refresh_model_status()

    # ---- Status bar ---------------------------------------------------------

    def _status(self, msg):
        self.after(0, self.status_var.set, msg)

    def _on_format_change(self, *_):
        """Update the format-description label when the dropdown changes."""
        fmt = self.format_var.get()
        self.format_desc_var.set(self.format_descriptions.get(fmt, ""))

    def _start_progress(self, base_status):
        """Show and start the indeterminate progress bar and dots-cycling status."""
        self._status_base = base_status
        self._dots_state = 0
        self.after(0, lambda: self.progress.pack(pady=(0, 10)))
        self.after(0, self.progress.start, 100)
        self._tick_dots()

    def _stop_progress(self, final_status=""):
        """Stop and hide the progress bar and dots animation."""
        if self._dots_job is not None:
            self.after_cancel(self._dots_job)
            self._dots_job = None
        self.after(0, self.progress.stop)
        self.after(0, self.progress.pack_forget)
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
        self._refresh_model_status()
        # Update title bar to show whether GPU acceleration is available.
        # Done here rather than at startup because torch isn't importable
        # until the dep check completes.
        try:
            import torch
            mode = "GPU" if torch.cuda.is_available() else "CPU"
        except Exception:
            mode = "CPU"
        self.after(0, lambda: self.title(f"{APP_TITLE}  ({mode})"))

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

    # ---- Drag and drop -----------------------------------------------------

    def _setup_dnd(self):
        if not _DND_AVAILABLE:
            return
        self.drop_target_register(_DND_FILES)
        self.dnd_bind("<<Drop>>", self._on_drop)

    def _on_drop(self, event):
        paths = [Path(p) for p in self.tk.splitlist(event.data)]
        if not paths:
            return
        first = paths[0]
        if first.is_dir():
            self.input_var.set(str(first))
        elif first.is_file():
            # Multiple files dropped → use their parent folder
            self.input_var.set(str(first) if len(paths) == 1
                               else str(first.parent))

    # ---- Settings persistence ----------------------------------------------

    def _load_settings(self):
        try:
            data = json.loads(SETTINGS_PATH.read_text())
            if last := data.get("last_folder"):
                self.input_var.set(last)
            if fmt := data.get("format"):
                if fmt in self.format_descriptions:
                    self.format_var.set(fmt)
                    self._on_format_change()
            for name, checked in data.get("models", {}).items():
                if name in self.model_vars:
                    self.model_vars[name].set(bool(checked))
        except Exception:
            pass

    def _save_settings(self):
        try:
            data = {
                "last_folder": self.input_var.get().strip(),
                "format": self.format_var.get(),
                "models": {n: v.get() for n, v in self.model_vars.items()},
            }
            SETTINGS_PATH.write_text(json.dumps(data, indent=2))
        except Exception:
            pass

    # ---- Dependency check --------------------------------------------------

    def _check_deps(self):
        self._status("Checking dependencies\u2026")
        self._log("Checking required dependencies\u2026")
        ram = _get_total_ram_gb()
        if ram is not None and ram < 24:
            self._log(
                f"\nNote: {ram:.0f} GB RAM detected. Running multiple models "
                f"simultaneously may cause slowdowns. For best performance on "
                f"low-RAM machines, run one model at a time."
            )
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

    # ---- Lazy InSPyReNet loader --------------------------------------------

    def _try_load_inspyrenet(self):
        """Attempt to import, install if needed, and instantiate InSPyReNet.

        Returns the Remover instance on success, or None on any failure
        (user declined install, pip failed, module failed to construct).
        Logs the reason and a recovery hint in every failure case. Never
        raises - the caller relies on a None return to drop InSPyReNet from
        the run while letting other models continue.
        """
        # Step 1: try the import. If it works, the package is already
        # installed and we can skip straight to model construction.
        try:
            from transparent_background import Remover
        except ImportError:
            self._log("\nInSPyReNet not installed. It can be installed now, "
                      "but the install pulls in several large dependencies "
                      "(~700 MB) and is known to fail on Python 3.14 due to "
                      "a transitive dependency (stringzilla) that needs a "
                      "C++ compiler. If install fails, the simplest fix is "
                      "to run this app under Python 3.12 instead.")
            ok = self._ask_yesno(
                "Install InSPyReNet?",
                "InSPyReNet isn't installed yet.\n\n"
                "Install it now? This will download several hundred MB of "
                "extra dependencies (albumentations, kornia, etc.) and may "
                "fail on Python 3.14 - see the log for details.\n\n"
                "If install fails, the other selected models will still run."
            )
            if not ok:
                self._log("InSPyReNet install declined. Skipping this model.")
                return None
            self._log("Installing transparent-background\u2026")
            try:
                install_dep("transparent-background==1.3.4", self._log)
            except Exception as e:
                self._log(f"\nInSPyReNet install FAILED: {e}")
                self._log("Continuing without InSPyReNet. Other models will "
                          "still run. To use InSPyReNet, try Python 3.12 "
                          "(see https://www.python.org/downloads/).")
                return None
            # Import again now that install has (hopefully) succeeded.
            try:
                from transparent_background import Remover
            except ImportError as e:
                self._log(f"\nInSPyReNet still not importable after install: {e}")
                self._log("Continuing without InSPyReNet.")
                return None

        # Step 2: construct the model. Failures here are unlikely but
        # possible (e.g. the first-run checkpoint download from Google Drive
        # is blocked by a proxy), so handle them the same way.
        self._log("Loading InSPyReNet\u2026")
        try:
            import torch
            device = "cuda:0" if torch.cuda.is_available() else "cpu"
            # `resize='dynamic'` produces sharper edges than the default
            # 'static' mode, at the cost of some stability. Worth it for
            # the high-resolution photography this tool targets - it's
            # the whole reason for running multiple models.
            model = Remover(mode="base", device=device, resize="dynamic")
            self._log(f"  InSPyReNet on {device}")
            return model
        except Exception as e:
            self._log(f"\nInSPyReNet failed to load: {e}")
            self._log("Continuing without InSPyReNet. Other models will "
                      "still run.")
            return None

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
        self._save_settings()
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
            inspyrenet_model = None

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

            # InSPyReNet is loaded lazily here rather than via REQUIRED_DEPS at
            # startup because `transparent-background` has a heavy transitive
            # dep chain (albumentations -> albucore -> stringzilla) that can
            # fail to install on newer Pythons (e.g. stringzilla 4.x has no
            # 3.14 wheel as of May 2026 and pip falls back to building from
            # source, which needs MSVC). If anything fails - user declines,
            # pip install fails, or the model won't construct - log clearly
            # and drop the InSPyReNet targets from this run. The other six
            # models continue normally.
            if any(t[0] == "inspyrenet" for t in targets.values()):
                inspyrenet_model = self._try_load_inspyrenet()
                if inspyrenet_model is None:
                    # Drop every inspyrenet target so the per-image loop
                    # below doesn't even try.
                    targets = {fn: t for fn, t in targets.items()
                               if t[0] != "inspyrenet"}
                    if not targets:
                        self._log("\nNo models left to run. Aborting.")
                        self._stop_progress(
                            "InSPyReNet was the only model and it failed to load.")
                        return

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
                        elif backend == "inspyrenet":
                            # Default `type='rgba'` returns a PIL Image with
                            # alpha-based transparency - same shape as BEN2
                            # and rembg outputs, so the save path below works
                            # unchanged.
                            result = inspyrenet_model.process(
                                image, type="rgba")
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
            # Refresh cache status after every run (new weights may have been
            # downloaded on first use, or InSPyReNet may have been installed).
            self._refresh_model_status()


# --- Embedded window icon ----------------------------------------------------
# Multi-resolution Windows .ico for the title bar and taskbar. Base64 of a
# 96x97 lemon graphic (Twemoji, CC BY 4.0). ~38 KB raw / ~51 KB encoded.
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
