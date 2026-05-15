# The Electric Kool-Aid Background Remover

**TL;DR:** A designer got fed up with remove.bg (expensive), Figma and Photoshop background removal (crap results), the privacy and ethical concerns of uploading colleagues' photos to cloud AI services, and messing around with command line tools every time they wanted to run a model. So they built this. Drop your images in a folder, pick your models, click Run. Everything stays on your machine.

---

A free, local, privacy-respecting background remover for Windows. Runs
entirely on your own machine - no cloud upload, no subscription, no
images sent anywhere.

Supports batch processing of whole folders or single images, with a choice
of six AI models so you can find the one that works best on your material.
Output is PNG, TIFF, or WebP with transparency preserved and DPI metadata
carried through - ready for web, print, or further editing.

Built for professional photography (300 DPI source material) where edge
quality on hair, glasses, and complex backgrounds matters.

![The Electric Kool-Aid Background Remover v3.8](assets/screenshot.png)

## What it does

Pick a folder of images **or a single image**, pick a format, tick the
model(s) you want to use, and hit Run. The app removes the background from
every image and saves transparent cutouts into labelled subfolders next to
your input.

If you're not sure which model will work best on your material, tick
several and compare the results side-by-side - each model gets its own
output folder so they're easy to review. Once you've found the one you
like, just tick that one on future runs.

Output is PNG, TIFF, or WebP (your choice). All three are lossless and
preserve the source image's DPI metadata. TIFF uses LZW compression; WebP
files are typically 25–35% smaller than PNG. Existing outputs are skipped
on re-runs, so interrupted batches can be safely resumed.

## Models included

All bundled models are permissively licensed (MIT) and suitable for
commercial use.

- **[BEN2](https://github.com/PramaLLC/BEN2)** - strong on fine edges like hair; good default for portrait or
  product photography.
- **[BiRefNet-General](https://huggingface.co/ZhengPeng7/BiRefNet)** - reliable general-purpose model; the safe default
  for mixed subject matter.
- **[BiRefNet-HR](https://huggingface.co/ZhengPeng7/BiRefNet-HRSOD-DHU)** - high-resolution variant. Worth trying on large
  source images (e.g. 24 MP professional photography) where General can
  soften fine edges.
- **[BiRefNet-Portrait](https://huggingface.co/ZhengPeng7/BiRefNet-portrait)** - tuned specifically for single-person portraits.
  Can behave unpredictably on group photos or non-human subjects.
- **[BiRefNet-Massive](https://huggingface.co/ZhengPeng7/BiRefNet_massive)** - same architecture as General, trained on more
  data. Often slightly better quality at higher compute cost.
- **[BiRefNet-Lite](https://huggingface.co/ZhengPeng7/BiRefNet-lite)** - faster, lower-memory variant of General. Slightly
  lower quality; useful for quick passes or weaker hardware.

BEN2 and BiRefNet-General are selected by default. Tick others as needed
to compare.

## Requirements

- Windows 10 or 11.
- Python 3.12 or newer. Python 3.14 is tested and works.
- Git installed and on PATH. One of the models (BEN2) is installed from
  GitHub rather than PyPI, which requires Git.
- ~5 GB of free disk space for model weights and PyTorch on first run.
- A GPU is **not** required. The tool runs on CPU by default and uses CUDA
  automatically if a compatible NVIDIA GPU is present.

## Installation

### Recommended for most users: virtual environment

A virtual environment keeps the dependencies isolated from the rest of your
Python installation and gives you a reproducible setup from pinned versions.

```
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
py the-electric-kool-aid-background-remover.py
```

`requirements.txt` contains pinned versions from a known-working environment
(Python 3.14.3, Windows 11, May 2026). See the file for notes on GPU support.

### Quick start (for your own machine, installs into system Python)

If you just want to get going and aren't worried about dependency isolation:

1. Install Python from <https://www.python.org/downloads/> if you don't
   already have it. During install, tick "Add Python to PATH".
2. Install Git from <https://git-scm.com/download/win> if you don't
   already have it. Use the default options.
3. Download `the-electric-kool-aid-background-remover.py` and put it
   anywhere convenient.
4. Open a Command Prompt or PowerShell window in that folder and run:

   ```
   py the-electric-kool-aid-background-remover.py
   ```

5. On first launch the app detects missing Python packages (PyTorch, rembg,
   BEN2, Pillow, OpenCV) and offers to install them. Accept; the install
   runs to several gigabytes and can take 10–20 minutes on a reasonable
   connection. Subsequent launches start instantly.

## Usage

1. Pick your input. Click **Folder…** to process every image in a folder,
   or **Image…** to process just one image. Supported formats:
   `.jpg .jpeg .png .webp .tif .tiff .bmp`.
2. Pick an output format from the dropdown (PNG, TIFF, or WebP). A short
   description of each format appears next to the picker.
3. Tick the models you want to run. You can pick one or several.
4. Click **Run** and confirm.
5. Watch the log and the status bar. The progress bar pulses while the
   app is working and the status bar shows which image and model is
   currently being processed (e.g. "Image 3/12 – BEN2…"). Click
   **Cancel** at any time to stop after the current image finishes.
6. When the run finishes, click **Open Output Folder** to go straight to
   the results in Explorer, or look inside the input location manually.
   You'll find subfolders named like `BEN2-PNG`, `BiRefNet-General-WebP`,
   etc., each containing one cutout per input image.

Output filenames carry the model name as a suffix
(`photo_01_BEN2.png`, `photo_01_BiRefNet-General.png`) so the files stay
self-identifying even if you move them out of their folders.

## Tips

- The first time you run a given model, its weights are downloaded
  (300 MB – 1 GB depending on model). Subsequent runs reuse the cached
  weights and start quickly.
- **GPU acceleration:** if you have an NVIDIA GPU and CUDA-enabled PyTorch,
  the tool will use it automatically - no configuration needed. Processing
  time drops from 10–30 seconds per image to 1–3 seconds.
- To find the best model for your material, tick several on a representative
  image and compare the results. Once you know which works best, tick only
  that one for your main batch run.
- The **Copy Output** button above the output log copies the entire run
  log to your clipboard - useful for sharing timing data or error messages.
- WebP has a hard 16383px-per-axis size limit. If your source images are
  larger than that on either axis (rare, but possible with very large
  scans or panoramas), the app will refuse to start a WebP run and list
  the oversized files. Pick PNG or TIFF instead, or downscale the input.

## Troubleshooting

**"Git is not recognized…" during install.** Git isn't on your PATH.
Reinstall Git with the default options, or open a fresh terminal after
installing it.

**Install fails on a specific package.** Python 3.14 is bleeding-edge and
the occasional ML library lags behind. Try installing Python 3.12 and
running with `py -3.12 the-electric-kool-aid-background-remover.py`.

**"No images found."** The folder you picked has no files with a
supported extension. Subfolders are not scanned - only the top level of
the folder.

**Output folder for a model is empty.** That model produced no new
output. Either every image was skipped because the output already existed,
or every image failed. Check the log for `FAILED` lines.

**"Image too large for WebP."** WebP cannot encode images bigger than
16383px on either axis. The dialog lists which images are over the limit.
Either pick PNG or TIFF, or remove/downscale the listed images.

## What this tool is not

- Not a web service. Everything runs locally; nothing is uploaded anywhere.
  This is the point.
- Not a compression tool. All output formats are configured for maximum
  quality and lossless encoding. PNG and TIFF are inherently lossless.
  WebP output also uses lossless mode - the files are smaller than PNG
  due to better compression, not because quality has been sacrificed.
  None of the outputs are "web-optimised" in the sense of being compressed
  for fast page loads; they are full-quality cutouts intended for further
  use in design, print, or web pipelines where you control the final
  compression step.
- Not bundled as an `.exe`. PyTorch makes a bundled build several GB; the
  `.py` file plus auto-install of dependencies is the intended distribution.
- Not cross-platform. The auto-install assumes Windows. The underlying
  Python code is not Windows-specific and could plausibly run on macOS or
  Linux with manual dependency setup, but is not tested there.
- Not fast. A 24 MP image on CPU takes 10–30 seconds per model. If you
  need speed, see the Tips section on GPU support.

## Credits

Window icon: lemon graphic from [Twemoji](https://github.com/twitter/twemoji),
copyright 2020 Twitter Inc. and other contributors, licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Packaged into a
multi-resolution `.ico` via [favicon.io](https://favicon.io/emoji-favicons/lemon/).

## Licence

MIT - see [LICENSE](LICENSE).

The models bundled with this tool are also MIT-licensed and free for
commercial use. See [MODEL-LICENCES.md](MODEL-LICENCES.md) for the full
details on each model.

## Provenance

> **100% Prime AI Slop** 🍋
>
> This tool - every line of code, every comment, and every doc - was
> written entirely by [Claude](https://claude.ai) (Anthropic). The design
> decisions were the human's: what the tool needed to do, which models to
> include, the privacy framing, the output formats, when to stop adding
> features, and the name. The human's other contributions were knowing what
> they wanted, asking good questions, and the occasional "that's rubbish,
> try again."
>
> No code was written by hand. No docs were written by hand. Vibe coding
> is real, it works, and this is what it looks like when you don't pretend
> otherwise. If you find a bug, Claude probably wrote it. If you like it,
> the human probably decided it should exist.
