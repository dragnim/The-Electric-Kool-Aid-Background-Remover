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
4. Then ask your question, for example:
   - *"I'm on Windows 11 and I've never used Python. Walk me through installing this step by step."*
   - *"The install failed with this error: [paste your error here]. What do I do?"*
   - *"Which model should I use for portraits with complex hair?"*
   - *"How do I set up a virtual environment for this?"*

---

## Paste this into your AI chat:

```
I need help with a tool called The Electric Kool-Aid Background Remover.
Here is everything you need to know about it:

WHAT IT IS:
A free, local, privacy-respecting background remover for Windows. It
removes backgrounds from images using AI models and saves transparent
cutouts as PNG, TIFF, or WebP files. Everything runs on your own machine
- nothing is uploaded to the internet.

THE TOOL:
- It is a single Python script: the-electric-kool-aid-background-remover.py
- It has a simple desktop GUI (a window with buttons - no command line needed once installed)
- GitHub repo: https://github.com/dragnim/The-Electric-Kool-Aid-Background-Remover

SYSTEM REQUIREMENTS:
- Windows 10 or 11
- Python 3.12 or newer (Python 3.14 is confirmed working)
- Around 5 GB of free disk space for model weights on first run
- A GPU is not required - it runs on CPU by default

THE MODELS (AI engines it uses to remove backgrounds):
- BEN2 - good for hair edges and detailed subjects
- BiRefNet-General - reliable all-rounder, good default
- BiRefNet-HR - high-resolution variant, good for large photos
- BiRefNet-Portrait - tuned for single people, not great for groups
- BiRefNet-Massive - like General but trained on more data
- BiRefNet-Lite - faster and lighter, slightly lower quality
- InSPyReNet - different architecture; useful to compare with BEN2/BiRefNet.
  Note: installed lazily on first use. The install can fail on Python 3.14
  due to a transitive dependency (stringzilla) that needs a C++ compiler.
  If install fails, switch to Python 3.12 or just use one of the other
  six models, which work fine on 3.14.
BEN2 and BiRefNet-General are ticked by default.

INSTALLATION - RECOMMENDED (virtual environment):
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
py the-electric-kool-aid-background-remover.py

INSTALLATION - QUICK START (system Python, easier but less isolated):
Just run: py the-electric-kool-aid-background-remover.py
On first launch it will detect missing packages and offer to install them.
Accept and wait - the first install is several GB and can take 10-20 minutes.

HOW TO USE IT:
1. Click Folder... to pick a folder of images, or Image... for a single image
2. Pick an output format from the dropdown (PNG, TIFF, or WebP)
3. Tick the models you want to use (start with BEN2 and BiRefNet-General)
4. Click Run and confirm
5. Watch the log at the bottom - it shows progress
6. When done, click Open Output Folder to see your results
7. Output goes into labelled subfolders next to your input (e.g. BEN2-PNG/)

OUTPUT:
- All output is lossless - PNG, TIFF and WebP are all full quality
- WebP is smaller than PNG but has a maximum image size of 16383px per side
- DPI metadata is preserved from the source image
- Output filenames include the model name (e.g. photo_01_BEN2.png)
- Re-running skips images that already have output, so you can safely resume

COMMON ISSUES:
- Install fails on a package - try Python 3.12 if you are on a newer version
- InSPyReNet install fails with "Microsoft Visual C++ 14.0 or greater is
  required" - this is a known issue on Python 3.14. Untick InSPyReNet and
  use the other six models, or switch to Python 3.12 where InSPyReNet works.
- "No images found" - only the top level of the folder is scanned, not subfolders
- WebP "image too large" error - your image exceeds 16383px, use PNG or TIFF instead

Please help me with the following question:
```

---

After pasting that, add your question at the end and the AI will have
everything it needs to help you properly.

---

*This document was written by Claude (Anthropic) as part of the
Electric Kool-Aid Background Remover project.*
