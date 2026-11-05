"""Digital finishing applied to the simulated print (Lightroom-style Basic / Color Grading / Vignette).

Runs after the film simulation on the display-encoded output, so editing these controls never
re-runs the film: a refined preview updates in a fraction of a second. Works in OkLab (perceptual
lightness / chroma / hue) and linear light (vignette).

Every operation is pointwise except Clarity (a blur whose radius is a fraction of the frame) and
the vignette (needs the pixel's position in the whole frame), which is why callers pass `frame`.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from .settings import CURVE_FIELDS, FINISH_FIELDS, HSL_FIELDS, DevelopSettings

_DEF = DevelopSettings()

# OkLab (Björn Ottosson) on XYZ D65
_M1 = np.array([[0.8189330101, 0.3618667424, -0.1288597137],
                [0.0329845436, 0.9293118715, 0.0361456387],
                [0.0482003018, 0.2643662691, 0.6338517070]])
_M2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468],
                [1.9779984951, -2.4285922050, 0.4505937099],
                [0.0259040371, 0.7827717662, -0.8086757660]])


CLARITY_SIGMA = 0.006  # local-contrast radius as a fraction of the frame's long edge


def is_identity(s: DevelopSettings) -> bool:
    d = DevelopSettings()
    return all(getattr(s, f) == getattr(d, f) for f in FINISH_FIELDS)


@lru_cache(maxsize=8)
def _space(cs: str):
    import colour

    space = colour.RGB_COLOURSPACES[cs]
    rgb2xyz = np.asarray(space.matrix_RGB_to_XYZ, np.float64)
    wp = np.asarray(space.whitepoint, np.float64)
    d65 = np.array([0.3127, 0.3290])
    if np.abs(wp - d65).max() > 1e-3:  # e.g. ProPhoto (D50): adapt to D65 for OkLab
        cat = colour.adaptation.matrix_chromatic_adaptation_VonKries(
            colour.xy_to_XYZ(wp), colour.xy_to_XYZ(d65), transform="Bradford")
        rgb2xyz = cat @ rgb2xyz
    to_lms = (_M1 @ rgb2xyz).astype(np.float32)
    from_lms = np.linalg.inv(_M1 @ rgb2xyz).astype(np.float32)
    return (to_lms, from_lms, _M2.astype(np.float32), np.linalg.inv(_M2).astype(np.float32),
            space.cctf_decoding, space.cctf_encoding)


@lru_cache(maxsize=1)
def _hue_table():
    """Map a Lightroom-style hue (0 red, 120 green, 240 blue) to an OkLab hue angle."""
    import colorsys

    to_lms, _, m2, _, dec, _ = _space("sRGB")
    angles = []
    for h in range(0, 361, 5):
        rgb = np.array(colorsys.hsv_to_rgb((h % 360) / 360.0, 1.0, 1.0), np.float32)
        lin = np.asarray(dec(rgb), np.float32)
        lab = m2 @ np.cbrt(to_lms @ lin)
        angles.append(np.arctan2(lab[2], lab[1]))
    return np.unwrap(np.array(angles))


def hue_to_ab(hue_deg: float) -> tuple[float, float]:
    t = _hue_table()
    ang = float(np.interp(hue_deg % 360.0, np.arange(0, 361, 5), t))
    return float(np.cos(ang)), float(np.sin(ang))


def _smoothstep(e0, e1, x):
    t = np.clip((x - e0) / max(e1 - e0, 1e-6), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def tone_curve(s: DevelopSettings) -> np.ndarray:
    """1024-entry lightness curve from Contrast / Highlights / Shadows / Whites / Blacks."""
    from scipy.interpolate import PchipInterpolator

    c, h, sh, w, b = (getattr(s, k) / 100.0 for k in ("contrast", "highlights", "shadows", "whites", "blacks"))
    xs = np.array([0.0, 0.10, 0.25, 0.50, 0.75, 0.90, 1.0])
    ys = np.array([
        max(0.0, b) * 0.16,
        0.10 + b * 0.07 + sh * 0.03 - c * 0.025,
        0.25 + sh * 0.10 - c * 0.06 + b * 0.035,
        0.50 + (sh + h) * 0.02,
        0.75 + h * 0.10 + c * 0.06 + w * 0.035,
        0.90 + w * 0.07 + h * 0.03 + c * 0.025,
        1.0 + min(0.0, w) * 0.16,
    ])
    for i in range(1, len(ys)):  # keep it monotone
        ys[i] = max(ys[i], ys[i - 1] + 1e-3)
    grid = np.linspace(0, 1, 1024)
    return np.clip(PchipInterpolator(xs, ys)(grid), 0.0, 1.2).astype(np.float32)


def apply(img: np.ndarray, s: DevelopSettings, *, color_space: str = "sRGB", frame=None) -> np.ndarray:
    """img: display-encoded float HxWx3 in [0,1] (in `color_space`).
    frame: (x0, y0, frame_w, frame_h) of this image inside the whole photo, in this image's pixels
           (defaults to the image itself). Used by the vignette and to size Clarity."""
    if is_identity(s):
        return img
    h_img, w_img = img.shape[:2]
    if frame is None:
        frame = (0, 0, w_img, h_img)
    to_lms, from_lms, m2, m2i, dec, enc = _space(color_space)
    lin = np.asarray(dec(np.clip(img, 0, 1)), np.float32)

    # --- vignette (linear light, position in the whole frame)
    if s.vignette != 0:
        x0, y0, fw, fh = frame
        xs = (np.arange(w_img, dtype=np.float32) + x0 + 0.5) / fw * 2 - 1
        ys = (np.arange(h_img, dtype=np.float32) + y0 + 0.5) / fh * 2 - 1
        r = np.sqrt(xs[None, :] ** 2 + ys[:, None] ** 2) / np.sqrt(2.0)
        mid = s.vignette_midpoint / 100.0
        fall = _smoothstep(0.15 + 0.6 * mid, 1.05, r).astype(np.float32)
        amt = s.vignette / 100.0
        gain = 1.0 + amt * fall * (0.85 if amt < 0 else 0.6)
        lin = lin * gain[..., None]

    # --- OkLab
    lms = np.cbrt(np.maximum(lin.reshape(-1, 3) @ to_lms.T, 0.0))
    lab = lms @ m2.T
    L = lab[:, 0]
    a = lab[:, 1]
    bb = lab[:, 2]

    if any(getattr(s, k) for k in ("contrast", "highlights", "shadows", "whites", "blacks")):
        curve = tone_curve(s)
        Lc = np.interp(np.clip(L, 0, 1), np.linspace(0, 1, 1024), curve).astype(np.float32)
        Lc = np.where(L > 1, L + (curve[-1] - 1.0), Lc)
        ratio = np.minimum(1.0, Lc / np.maximum(L, 1e-4))  # keep darkened colours in gamut
        a, bb, L = a * ratio, bb * ratio, Lc

    if s.clarity:
        from spektrafilm.utils.fast_gaussian_filter import fast_gaussian_filter

        sigma = max(1.0, CLARITY_SIGMA * max(frame[2], frame[3]))
        L2 = L.reshape(h_img, w_img).astype(np.float64)
        blur = fast_gaussian_filter(L2, sigma).astype(np.float32).reshape(-1)
        wmid = np.clip(4 * L * (1 - L), 0, 1)
        L = L + (s.clarity / 100.0) * 1.2 * (L - blur) * wmid

    if s.saturation or s.vibrance:
        C = np.sqrt(a * a + bb * bb)
        f = 1.0 + s.saturation / 100.0
        if s.vibrance:
            low = 1.0 - _smoothstep(0.0, 0.18, C)
            f = f * (1.0 + (s.vibrance / 100.0) * 0.8 * low)
        a, bb = a * f, bb * f

    if s.cg_shadow_sat or s.cg_mid_sat or s.cg_high_sat:
        bal = s.cg_balance / 100.0
        blend = s.cg_blending / 100.0
        p = 0.5 - 0.25 * bal
        width = 0.08 + 0.35 * blend
        w_h = _smoothstep(p - width, p + width, L)
        w_s = 1.0 - w_h
        w_m = np.clip(1.0 - np.abs(L - 0.5) / (0.2 + 0.3 * blend), 0, 1)
        w_s = w_s * (1 - 0.5 * w_m)
        w_h = w_h * (1 - 0.5 * w_m)
        for w_, hue, sat in ((w_s, s.cg_shadow_hue, s.cg_shadow_sat), (w_m, s.cg_mid_hue, s.cg_mid_sat),
                             (w_h, s.cg_high_hue, s.cg_high_sat)):
            if sat:
                ca, cb = hue_to_ab(hue)
                k = (sat / 100.0) * 0.07
                a = a + w_ * k * ca
                bb = bb + w_ * k * cb

    if any(getattr(s, f) for f in HSL_FIELDS):
        L, a, bb = _hsl_mix(L, a, bb, s)

    lab = np.stack([L, a, bb], axis=1).astype(np.float32)
    lin = ((lab @ m2i.T) ** 3) @ from_lms.T
    lin = np.maximum(lin, 0.0).reshape(h_img, w_img, 3)
    out = np.asarray(enc(np.clip(lin, 0, 1)), np.float32)
    out = np.clip(out, 0.0, 1.0)

    if any(getattr(s, f) != getattr(_DEF, f) for f in CURVE_FIELDS):
        out = _apply_curves(out, s)
    if s.lut_name and s.lut_amount > 0:
        from . import luts

        out = luts.apply(out, s.lut_name, s.lut_amount)
    return out


# ------------------------------------------------------------------ tone curves

def curve_lut(points, n=1024) -> np.ndarray:
    """Smooth monotone curve through (x, y) points, sampled at n positions in 0..1."""
    from scipy.interpolate import PchipInterpolator

    pts = sorted((float(x), float(y)) for x, y in points)
    xs, ys = [], []
    for x, y in pts:  # strictly increasing x
        if xs and x <= xs[-1] + 1e-4:
            continue
        xs.append(x)
        ys.append(y)
    grid = np.linspace(0, 1, n)
    if len(xs) < 2:
        return grid.astype(np.float32)
    if len(xs) == 2:
        return np.clip(np.interp(grid, xs, ys), 0, 1).astype(np.float32)
    return np.clip(PchipInterpolator(xs, ys, extrapolate=True)(np.clip(grid, xs[0], xs[-1])), 0, 1).astype(np.float32)


def _apply_curves(out, s):
    grid = np.linspace(0, 1, 1024, dtype=np.float32)
    master = curve_lut(s.curve_master)
    res = np.empty_like(out)
    for c, pts in enumerate((s.curve_r, s.curve_g, s.curve_b)):
        chan = curve_lut(pts)
        composite = np.interp(master, grid, chan).astype(np.float32)  # channel curve after the master curve
        res[..., c] = np.interp(out[..., c], grid, composite)
    return res


# ------------------------------------------------------------------ HSL colour mixer

# Band centres as Lightroom-style hues (HSV degrees)
_BAND_HUES = {"red": 0, "orange": 30, "yellow": 60, "green": 120, "aqua": 180, "blue": 240, "purple": 270,
              "magenta": 300}


@lru_cache(maxsize=1)
def _band_angles():
    ang = []
    for band, h in _BAND_HUES.items():
        ca, cb = hue_to_ab(h)
        ang.append((float(np.arctan2(cb, ca)) % (2 * np.pi), band))
    ang.sort()
    return np.array([a for a, _ in ang]), [b for _, b in ang]


def _hsl_mix(L, a, bb, s):
    centres, bands = _band_angles()
    H = np.array([getattr(s, f"hsl_hue_{b}") for b in bands], np.float32) / 100.0
    S = np.array([getattr(s, f"hsl_sat_{b}") for b in bands], np.float32) / 100.0
    V = np.array([getattr(s, f"hsl_lum_{b}") for b in bands], np.float32) / 100.0
    theta = np.arctan2(bb, a) % (2 * np.pi)
    ext = np.concatenate([centres, [centres[0] + 2 * np.pi]])
    th = np.where(theta < centres[0], theta + 2 * np.pi, theta)
    i = np.clip(np.searchsorted(ext, th) - 1, 0, len(centres) - 1)
    j = (i + 1) % len(centres)
    w = ((th - ext[i]) / (ext[i + 1] - ext[i])).astype(np.float32)
    hue = H[i] * (1 - w) + H[j] * w
    sat = S[i] * (1 - w) + S[j] * w
    lum = V[i] * (1 - w) + V[j] * w
    C = np.sqrt(a * a + bb * bb)
    weight = np.clip(C / 0.08, 0, 1)  # greys are left alone
    ang = theta + hue * weight * (np.pi / 6)  # ±100 rotates up to ±30°
    C2 = C * np.maximum(1.0 + sat * weight, 0.0)
    L2 = L + lum * weight * 0.15
    return L2, (C2 * np.cos(ang)).astype(np.float32), (C2 * np.sin(ang)).astype(np.float32)
