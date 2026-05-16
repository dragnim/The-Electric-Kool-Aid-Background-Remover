# Model Licences

All models bundled with The Electric Kool-Aid Background Remover are
permissively licensed and suitable for commercial use. This file records
each model, its source, licence, and the date the licence was verified.

BRIA-RMBG was deliberately excluded because its CC BY-NC 4.0 licence
forbids commercial use. Any future model added should have its licence
confirmed here before inclusion.

---

## BEN2

| Field   | Detail |
|---------|--------|
| Display name | BEN2 |
| Source | https://huggingface.co/PramaLLC/BEN2 |
| Install | `pip install https://github.com/PramaLLC/BEN2/archive/2c99a5da477b5523585bfa5c893888a6e818a8f6.zip` (Git not required) |
| Licence | MIT |
| Licence URL | https://huggingface.co/PramaLLC/BEN2/blob/main/LICENSE |
| Verified | May 2026 |

---

## BiRefNet-General

| Field   | Detail |
|---------|--------|
| Display name | BiRefNet-General |
| rembg identifier | `birefnet-general` |
| Source | https://huggingface.co/ZhengPeng7/BiRefNet |
| Licence | MIT |
| Licence URL | https://huggingface.co/ZhengPeng7/BiRefNet/blob/main/LICENSE |
| Verified | May 2026 |

---

## BiRefNet-HR

| Field   | Detail |
|---------|--------|
| Display name | BiRefNet-HR |
| rembg identifier | `birefnet-hrsod` |
| Source | https://huggingface.co/ZhengPeng7/BiRefNet-HRSOD-DHU |
| Licence | MIT |
| Licence URL | https://huggingface.co/ZhengPeng7/BiRefNet-HRSOD-DHU/blob/main/LICENSE |
| Verified | May 2026 |
| Note | Display name is "HR" but rembg's internal identifier is `birefnet-hrsod`. |

---

## BiRefNet-Portrait

| Field   | Detail |
|---------|--------|
| Display name | BiRefNet-Portrait |
| rembg identifier | `birefnet-portrait` |
| Source | https://huggingface.co/ZhengPeng7/BiRefNet-portrait |
| Licence | MIT |
| Licence URL | https://huggingface.co/ZhengPeng7/BiRefNet-portrait/blob/main/LICENSE |
| Verified | May 2026 |

---

## BiRefNet-Massive

| Field   | Detail |
|---------|--------|
| Display name | BiRefNet-Massive |
| rembg identifier | `birefnet-massive` |
| Source | https://huggingface.co/ZhengPeng7/BiRefNet_massive |
| Licence | MIT |
| Licence URL | https://huggingface.co/ZhengPeng7/BiRefNet_massive/blob/main/LICENSE |
| Verified | May 2026 |

---

## BiRefNet-Lite

| Field   | Detail |
|---------|--------|
| Display name | BiRefNet-Lite |
| rembg identifier | `birefnet-general-lite` |
| Source | https://huggingface.co/ZhengPeng7/BiRefNet-lite |
| Licence | MIT |
| Licence URL | https://huggingface.co/ZhengPeng7/BiRefNet-lite/blob/main/LICENSE |
| Verified | May 2026 |

---

## InSPyReNet

| Field   | Detail |
|---------|--------|
| Display name | InSPyReNet |
| Source | https://github.com/plemeri/transparent-background (package) / https://github.com/plemeri/InSPyReNet (model) |
| Install | `pip install transparent-background` (lazy - on first use of this model in the app) |
| Licence | MIT |
| Licence URL | https://github.com/plemeri/transparent-background/blob/main/LICENSE |
| Verified | May 2026 |
| Note | Pyramid-based salient object detection (ACCV 2022). Different architecture family from BEN2 and BiRefNet, so a useful third comparison point. Configured with `resize='dynamic'` for sharper edges. Installed lazily because `transparent-background` pulls in `albumentations -> albucore -> stringzilla`, and `stringzilla` has no Python 3.14 wheel, so installing on 3.14 needs an MSVC build toolchain. If your install fails for this reason, fall back to Python 3.12. |
