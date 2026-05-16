"""
GPU setup helper for The Electric Kool-Aid Background Remover.

Checks whether torch is installed and whether it's CPU or CUDA,
detects NVIDIA GPU and CUDA version, then offers to install or
upgrade to the GPU-accelerated version of PyTorch.

Exit codes:
  0 = nothing to do (CUDA torch already installed, or no NVIDIA GPU,
      or user declined, or install succeeded)
  1 = error (install failed)
"""

import subprocess
import sys
import os

REPO = "https://github.com/dragnim/The-Electric-Kool-Aid-Background-Remover"

TORCH_VERSION        = "2.12.0"
TORCHVISION_VERSION  = "0.27.0"
ONNXRUNTIME_GPU_VERSION = "1.26.0"

# We use cu126 (CUDA 12.6) rather than cu130 (CUDA 13.0) because
# onnxruntime-gpu on PyPI is built for CUDA 12.x. Both work fine on
# any RTX card; the CUDA version is the toolkit version, not a driver limit.
INDEX_CUDA_126    = "https://download.pytorch.org/whl/cu126"
TORCH_CUDA_LABEL  = "CUDA 12.6"


def check_torch_state():
    """Return 'cuda', 'cpu', or 'missing'."""
    try:
        import torch
        return "cuda" if torch.version.cuda else "cpu"
    except ImportError:
        return "missing"


def get_nvidia_gpu():
    """Return (gpu_name, cuda_major) or (None, None) if no NVIDIA GPU."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return None, None
        gpu_name = result.stdout.strip().splitlines()[0].strip()
        if not gpu_name:
            return None, None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None, None

    # Get CUDA version from nvidia-smi -q
    try:
        result = subprocess.run(
            ["nvidia-smi", "-q"],
            capture_output=True, text=True, timeout=10
        )
        cuda_ver = None
        for line in result.stdout.splitlines():
            if "CUDA Version" in line:
                parts = line.split(":")
                if len(parts) >= 2:
                    cuda_ver = parts[-1].strip()
                    break
        if not cuda_ver:
            return gpu_name, None
        major = int(cuda_ver.split(".")[0])
        return gpu_name, major
    except Exception:
        return gpu_name, None


def pick_index_url(cuda_major):
    """Return the PyTorch index URL if the driver is new enough, or None."""
    if cuda_major is None:
        return None, None
    # Require driver CUDA 12+ (very old drivers won't support cu126 torch)
    if cuda_major >= 12:
        return INDEX_CUDA_126, TORCH_CUDA_LABEL
    return None, None


def install_torch(index_url, cuda_label, uninstall_first=False):
    """Install GPU PyTorch and onnxruntime-gpu. Returns True on success."""
    if uninstall_first:
        print("\n  Uninstalling CPU PyTorch and onnxruntime...")
        subprocess.run(
            [sys.executable, "-m", "pip", "uninstall",
             "torch", "torchvision", "onnxruntime", "-y"],
            capture_output=True
        )

    print(f"\n  Installing GPU-accelerated PyTorch ({cuda_label})...")
    print(f"  This is about 2.5 GB and will take several minutes.\n")

    result = subprocess.run([
        sys.executable, "-m", "pip", "install",
        f"torch=={TORCH_VERSION}",
        f"torchvision=={TORCHVISION_VERSION}",
        "--index-url", index_url
    ])
    if result.returncode != 0:
        return False

    print(f"\n  Installing onnxruntime-gpu (for BiRefNet GPU acceleration)...")
    result = subprocess.run([
        sys.executable, "-m", "pip", "install",
        f"onnxruntime-gpu=={ONNXRUNTIME_GPU_VERSION}"
    ])
    return result.returncode == 0


def main():
    args = sys.argv[1:]

    # If run directly with no recognised arguments (e.g. double-clicked),
    # show a friendly message rather than silently exiting.
    if not args or args == [] :
        print()
        print("  This file is a helper used by launch.bat.")
        print("  You don't need to run it directly.")
        print()
        print("  To start the app, double-click launch.bat instead.")
        print()
        print(f"  For more information visit:")
        print(f"  {REPO}")
        print()
        input("  Press Enter to close...")
        sys.exit(0)

    # Strip the launcher flag — it's just an "I'm legitimate" signal
    args = [a for a in args if a != "--from-launcher"]

    force_cpu   = "--force-cpu"   in args
    force_offer = "--force-offer" in args

    # --force-cpu: uninstall GPU versions, install CPU versions
    if force_cpu:
        print("\n  Uninstalling GPU PyTorch and onnxruntime-gpu...")
        subprocess.run(
            [sys.executable, "-m", "pip", "uninstall",
             "torch", "torchvision", "onnxruntime-gpu", "-y"],
            capture_output=True
        )
        print("  Installing CPU PyTorch...")
        result = subprocess.run([
            sys.executable, "-m", "pip", "install",
            f"torch=={TORCH_VERSION}",
            f"torchvision=={TORCHVISION_VERSION}",
            "--index-url", "https://download.pytorch.org/whl/cpu"
        ])
        if result.returncode == 0:
            print("  Installing onnxruntime (CPU)...")
            subprocess.run([
                sys.executable, "-m", "pip", "install",
                f"onnxruntime=={ONNXRUNTIME_GPU_VERSION}"
            ])
            print("\n  Switched to CPU version successfully.")
        else:
            print("\n  Switch failed. For help visit:")
            print(f"  {REPO}")
        sys.exit(0)

    torch_state = check_torch_state()

    # --force-offer: skip the cuda check, always offer GPU install
    if not force_offer:
        # CUDA torch already installed — nothing to do
        if torch_state == "cuda":
            sys.exit(0)

    gpu_name, cuda_major = get_nvidia_gpu()

    # No NVIDIA GPU detected — nothing to offer
    if gpu_name is None:
        if force_offer:
            print("\n  No NVIDIA GPU detected. Cannot offer GPU version.")
            input("  Press Enter to continue...")
        sys.exit(0)

    index_url, cuda_label = pick_index_url(cuda_major)

    # GPU found but driver too old for supported CUDA build
    if index_url is None:
        if force_offer:
            print("\n  Your GPU driver is too old for a supported CUDA build.")
            print("  Update your NVIDIA drivers and try again.")
            input("  Press Enter to continue...")
        sys.exit(0)

    # Show the appropriate prompt
    print(f"\n  NVIDIA GPU detected: {gpu_name}")
    print(f"  Your driver supports CUDA {cuda_major}.x\n")

    if torch_state == "cpu":
        print("  PyTorch is currently installed in CPU-only mode.")
        print("  A GPU-accelerated version is available which would")
        print("  make processing faster on your NVIDIA GPU.\n")
        print("  [1] Upgrade to GPU version  (could make things faster)")
        print("      The CPU version will be uninstalled and replaced.")
        print(f"      Download size: ~2.5 GB.\n")
        print("  [2] Keep CPU version\n")
    else:
        print("  PyTorch can be installed in two versions:\n")
        print("  [1] GPU version  (could make things faster)")
        print("      Uses your NVIDIA GPU for processing.")
        print(f"      Download size: ~2.5 GB.\n")
        print("  [2] CPU version  (works on any computer, slower)\n")

    try:
        choice = input("  Enter 1 or 2: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n  Cancelled.")
        sys.exit(0)

    if choice != "1":
        sys.exit(0)

    success = install_torch(
        index_url, cuda_label,
        uninstall_first=(torch_state == "cpu")
    )

    if not success:
        print("\n  GPU install failed. The app will still work - just slower.")
        print(f"\n  For help visit:\n    {REPO}\n")
        input("  Press Enter to continue...")

    sys.exit(0)


if __name__ == "__main__":
    main()
