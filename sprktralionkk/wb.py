"""White balance in linear ProPhoto RGB.

Model (same convention as Lightroom): the photo is decoded with the camera's as-shot white
balance. Choosing a different scene illuminant (Kelvin + tint) applies a von Kries / CAT02
adaptation *from* that illuminant *to* the as-shot one, so:
  * lower Kelvin  -> the scene is assumed warmer -> the picture gets cooler
  * positive tint -> the scene is assumed greener -> the picture gets more magenta
  * Kelvin/tint equal to the as-shot values -> exactly no change.

Tint units: tint = Duv / 0.0003 (so ±150 spans about ±0.045 Duv).
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

TINT_SCALE = 0.0003
NOMINAL = (5500.0, 0.0)  # as-shot reference for already-rendered files (JPEG/TIFF/PNG)
PRESETS = {  # Kelvin, tint
    "daylight": (5500.0, 10.0),
    "cloudy": (6500.0, 10.0),
    "shade": (7500.0, 10.0),
    "tungsten": (2850.0, 0.0),
    "fluorescent": (3800.0, 21.0),
    "flash": (5500.0, 0.0),
}
WB_MODES = ["as_shot", "auto", "daylight", "cloudy", "shade", "tungsten", "fluorescent", "flash", "custom"]
WB_LABELS = ["As Shot", "Auto", "Daylight", "Cloudy", "Shade", "Tungsten", "Fluorescent", "Flash", "Custom"]


@lru_cache(maxsize=1)
def _mats():
    import colour

    pp = colour.RGB_COLOURSPACES["ProPhoto RGB"]
    cat = np.asarray(colour.adaptation.CAT_CAT02, dtype=np.float64)
    return (np.asarray(pp.matrix_RGB_to_XYZ, np.float64), np.asarray(pp.matrix_XYZ_to_RGB, np.float64),
            cat, np.linalg.inv(cat))


def kelvin_tint_to_xyz(kelvin: float, tint: float) -> np.ndarray:
    import colour
    from colour.temperature import CCT_to_uv_Ohno2013

    uv = CCT_to_uv_Ohno2013(np.array([float(np.clip(kelvin, 1500, 50000)), float(tint) * TINT_SCALE]))
    xy = colour.UCS_uv_to_xy(uv)
    return np.array([xy[0] / xy[1], 1.0, (1 - xy[0] - xy[1]) / xy[1]])


def xyz_to_kelvin_tint(xyz) -> tuple[float, float]:
    import colour
    from colour.temperature import uv_to_CCT_Ohno2013

    xyz = np.asarray(xyz, np.float64)
    xy = xyz[:2] / max(xyz.sum(), 1e-12)
    T, duv = uv_to_CCT_Ohno2013(colour.xy_to_UCS_uv(xy))
    return float(np.clip(T, 1500, 50000)), float(np.clip(duv / TINT_SCALE, -150, 150))


def adaptation_matrix(scene: tuple[float, float], as_shot: tuple[float, float]) -> np.ndarray:
    """3x3 matrix (ProPhoto linear) re-balancing a photo shot as `as_shot` for illuminant `scene`."""
    if abs(scene[0] - as_shot[0]) < 0.5 and abs(scene[1] - as_shot[1]) < 1e-3:
        return np.eye(3)
    rgb2xyz, xyz2rgb, cat, icat = _mats()
    lms_scene = cat @ kelvin_tint_to_xyz(*scene)
    lms_shot = cat @ kelvin_tint_to_xyz(*as_shot)
    gains = np.diag(lms_shot / lms_scene)
    return xyz2rgb @ icat @ gains @ cat @ rgb2xyz


def apply_matrix(img: np.ndarray, m: np.ndarray) -> np.ndarray:
    if np.allclose(m, np.eye(3)):
        return img
    out = img.reshape(-1, 3) @ m.T.astype(np.float32)
    return np.maximum(out, 0.0).reshape(img.shape).astype(np.float32)


def neutralize(rgb_sample, as_shot: tuple[float, float]) -> tuple[float, float]:
    """Kelvin/tint that make `rgb_sample` (as-shot linear ProPhoto) neutral — eyedropper and Auto WB."""
    rgb2xyz, xyz2rgb, cat, icat = _mats()
    c = np.maximum(np.asarray(rgb_sample, np.float64), 1e-6)
    lms_c = cat @ (rgb2xyz @ c)
    lms_white = cat @ (rgb2xyz @ np.ones(3))  # working-space white (D50)
    lms_shot = cat @ kelvin_tint_to_xyz(*as_shot)
    lms_scene = lms_shot * lms_c / lms_white
    return xyz_to_kelvin_tint(icat @ lms_scene)


def auto_sample(img: np.ndarray) -> np.ndarray:
    """Robust grey-world estimate: mean colour of mid-tone, unclipped pixels."""
    sub = img[::4, ::4].reshape(-1, 3).astype(np.float64)
    lum = sub @ np.array([0.2880, 0.7119, 0.0001])
    lo, hi = np.percentile(lum, [10, 97])
    keep = (lum > lo) & (lum < hi) & (sub.max(axis=1) < 0.98 * sub.max())
    sel = sub[keep] if keep.sum() > 100 else sub
    return sel.mean(axis=0)


def raw_as_shot(path: str) -> tuple[float, float] | None:
    """Estimate the as-shot Kelvin/tint from the camera white balance and colour matrix."""
    try:
        import rawpy

        with rawpy.imread(path) as raw:
            wb = np.asarray(raw.camera_whitebalance, np.float64)[:3]
            m = np.asarray(raw.rgb_xyz_matrix, np.float64)[:3, :3]
        if wb.min() <= 0 or not np.isfinite(m).all() or abs(np.linalg.det(m)) < 1e-9:
            return None
        neutral_cam = 1.0 / wb
        xyz = np.linalg.solve(m, neutral_cam / neutral_cam[1])
        if (xyz <= 0).any():
            return None
        return xyz_to_kelvin_tint(xyz)
    except Exception:
        return None


def target_for(mode: str, kelvin: float, tint: float, as_shot, auto) -> tuple[float, float]:
    """Scene illuminant (Kelvin, tint) for a WB mode."""
    if mode == "as_shot":
        return as_shot
    if mode == "auto":
        return auto or as_shot
    if mode in PRESETS:
        return PRESETS[mode]
    return (float(kelvin), float(tint))
