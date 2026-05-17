# How to get AI help with The Electric Kool-Aid Background Remover

This document is for you — a designer or non-technical user who wants to
use an AI assistant (Claude, ChatGPT, etc.) to help them install or use
this tool. Copy and paste the text in the box below into your AI chat
before asking your question. The AI will then have all the context it
needs to give you relevant, accurate help.

---

## How to use this

1. Open your AI assistant (e.g. https://claude.ai or https://chatgpt.com)
2. Start a new conversation
3. Copy everything inside the box below and paste it in as your first message
4. Then describe your problem:
   - What you were trying to do
   - What you clicked
   - What happened
   - The exact error message from the log (if any)
   - Your Windows version and Python version
   - Whether you used launch.bat or a manual install

Example questions:
   - *"I'm on Windows 11 and I've never used Python. Walk me through installing this step by step."*
   - *"I double-clicked launch.bat and got this error: [paste your error here]. What do I do?"*
   - *"Which model should I use for portraits with complex hair?"*
   - *"How do I switch from the CPU version to the GPU version?"*

---

## Paste this into your AI chat:

```
I need help with a tool called The Electric Kool-Aid Background Remover.
Here is everything you need to know about it:

HELP FILE VERSION:
Updated: May 2026
Applies to: The Electric Kool-Aid Background Remover v3.12

WHAT IT IS:
A free, local, privacy-respecting background remover for Windows. It
removes backgrounds from images using AI models and saves transparent
cutouts as PNG, TIFF, or WebP files. Everything runs on your own machine
- nothing is uploaded to the internet.

THE TOOL:
- It is a single Python script: the-electric-kool-aid-background-remover.py
- It has a simple desktop GUI (a window with buttons - no command line needed once installed)
- It comes with launch.bat (double-click to start), cleanup.bat (remove everything it installed), and gpu_setup.py (GPU detection helper, used by launch.bat automatically)
- GitHub repo: https://github.com/dragnim/The-Electric-Kool-Aid-Background-Remover

SYSTEM REQUIREMENTS:
- Windows 10 or 11
- Python 3.12 or newer (Python 3.14 is confirmed working) - launch.bat will install Python automatically if needed
- Around 5-6 GB of free disk space for model weights and PyTorch on first run
- A GPU is not required - it runs on CPU by default
- If you have an NVIDIA GPU, launch.bat will detect it and offer a faster GPU-accelerated version of PyTorch

INSTALLATION - EASIEST (recommended for most users):
Download the zip from the releases page, unzip it, and double-click launch.bat.
It handles everything - Python setup, GPU detection, and launching the app.
If Windows shows a security warning, you can verify the file at https://www.virustotal.com before running.

INSTALLATION - VIRTUAL ENVIRONMENT (for technically-minded users):
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
py the-electric-kool-aid-background-remover.py

FIRST RUN - EXPECT A WAIT:
The first run downloads and installs PyTorch and the AI model weight files.
This can take a long time (15-30 minutes or more depending on your connection)
and several GB of files. The app is not frozen - watch the log for progress.
Later runs start quickly because everything is already installed.
Approximate download sizes on first run:
- PyTorch: ~250 MB (CPU) or ~2.5 GB (GPU version)
- Each BiRefNet model: ~900 MB (downloaded the first time that model is used)
- BEN2: ~400 MB
- InSPyReNet: ~700 MB (only if you tick that model)

SUPPORTED INPUT FORMATS:
JPEG, PNG, WebP, TIFF, and BMP are all supported.
Subfolders are not scanned - only the top level of the selected folder.
Animated GIFs are not supported.

GUI BUTTONS:
- Folder... — select a folder of images to process
- Image... — select a single image to process
- You can also drag and drop a folder or image directly onto the window
- Run — start background removal (asks for confirmation first)
- Cancel — stop the run after the current image finishes
- Open Output Folder — open the folder where results were saved
- Copy Log — copy the full log text to the clipboard
- x (next to each model) — delete that model's downloaded weight files

HOW TO USE IT:
1. Click Folder... to pick a folder of images, or Image... for a single image
   (or drag and drop either onto the window)
2. Pick an output format from the dropdown (PNG, TIFF, or WebP)
3. Tick the models you want to use (start with BEN2 and BiRefNet-General)
4. Click Run and confirm
5. Watch the log at the bottom - it shows progress
6. When done, click Open Output Folder to see your results

THE MODELS (AI engines it uses to remove backgrounds):
- BEN2 - good for hair edges and detailed subjects. Default on.
- BiRefNet-General - reliable all-rounder, good default. Default on.
- BiRefNet-HR - high-resolution variant, good for large/high-DPI photos
- BiRefNet-Portrait - tuned for single people; unpredictable on groups
- BiRefNet-Massive - like General but trained on more data
- BiRefNet-Lite - faster and lighter, slightly lower quality
- InSPyReNet - different architecture; useful to compare with BEN2/BiRefNet.
  Note: installed lazily on first use. The install can fail on Python 3.14
  due to a transitive dependency (stringzilla) that needs a C++ compiler.
  If install fails, switch to Python 3.12 or just use one of the other
  six models, which work fine on 3.14.

MODEL CHOICE - QUICK GUIDE:
- Not sure? Start with BEN2 and BiRefNet-General (the defaults)
- Portraits / people? Add BiRefNet-Portrait (single subjects only)
- Large high-resolution photos? Try BiRefNet-HR
- Need faster results or have a slower machine? Try BiRefNet-Lite
- Difficult images where results vary? Add InSPyReNet as a comparison

OUTPUT - WHERE FILES ARE SAVED:
Output folders are created inside your input folder, one per model.
Folder name format: ModelName-FORMAT (e.g. BEN2-PNG)
File name format: originalname_ModelName.ext (e.g. cat_BEN2.png)

Example:
  Input image:  C:\Users\Mike\Pictures\cat.jpg
  After running BEN2 with PNG output:
  Result:       C:\Users\Mike\Pictures\BEN2-PNG\cat_BEN2.png

- All output is lossless - PNG, TIFF and WebP are all full quality
- WebP is smaller than PNG but has a maximum image size of 16383px per side
- DPI metadata is preserved from the source image
- Re-running skips images that already have output, so you can safely resume interrupted jobs

LIMITATIONS:
- Does not edit images manually or add effects
- Only removes backgrounds - does not replace them
- Does not scan subfolders - only processes the top level of a folder
- WebP output fails if any image exceeds 16383px on either side (use PNG or TIFF instead)
- InSPyReNet may not install on Python 3.14 (see model notes above)
- Running multiple models at once uses more RAM; on machines with 16 GB or less,
  run one model at a time to avoid slowdowns

COMMON ISSUES:
- Install fails on a package - try Python 3.12 if you are on a newer version
- InSPyReNet install fails with "Microsoft Visual C++ 14.0 or greater is
  required" - this is a known issue on Python 3.14. Untick InSPyReNet and
  use the other six models, or switch to Python 3.12 where InSPyReNet works.
- "No images found" - only the top level of the folder is scanned, not subfolders
- WebP "image too large" error - your image exceeds 16383px, use PNG or TIFF instead
- Processing is very slow or the machine is unresponsive - you may be low on RAM;
  run one model at a time

RESETTING / FIXING A BAD INSTALL:
If the app gets into a bad state, run cleanup.bat. It shows everything
the app installed and lets you remove it selectively or entirely. Then
run launch.bat again to reinstall cleanly.

REMOVING THE APP:
Double-click cleanup.bat. It shows everything installed and how to remove it,
including an option to switch between CPU and GPU versions of PyTorch.

WHEN ASKING FOR HELP, INCLUDE:
- Your Windows version
- Your Python version
- Whether you used launch.bat or manual install
- Whether you chose CPU or GPU PyTorch
- Which model(s) you selected
- The exact error message from the log
- Whether the issue happened during install, model download, or image processing

Please help me with the following question:
```

---

After pasting that, add your question at the end and the AI will have
everything it needs to help you properly.

---

*This document was written by Claude (Anthropic) as part of the
Electric Kool-Aid Background Remover project.*
