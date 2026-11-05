"""Real-time preview on the CPU (any PC, no GPU needed).

The pointwise part of the film -> print -> scan chain is baked into lookup tables for the current
settings, then one compiled, multi-threaded pass maps the screen-sized photo through them:

  input (linear ProPhoto, camera WB) --[WB matrix x exposure gain]--> log2 RGB
      --[film LUT, 41^3]--> negative densities
      --[print LUT, 25^3 while dragging / 41^3 at rest]--> scanned print (display sRGB)
      --[vignette]--[finish LUT, 33^3: tone, presence, colour grading]--> screen

* Exposure and white balance never re-bake (they only move the input): ~10-20 ms per frame.
* Film chemistry re-bakes the film LUT (~30 ms); paper / enlarger re-bake the print LUT; finishing
  re-bakes the finish LUT (~10 ms).
* Spatial and random effects — halation, scatter, coupler diffusion, grain, glare, clarity,
  sharpening — are not pointwise: they arrive with the refined render a moment after you stop.
"""

from __future__ import annotations

import math
import threading
from collections import OrderedDict

import numpy as np
from numba import njit, prange

from . import engine, finish, profiles, wb
from .settings import (
    BORDER_FIELDS,
    FILM_FORMATS,
    FINISH_FIELDS,
    GEOMETRY_FIELDS,
    METER_FIELDS,
    NO_PRINT,
    DevelopSettings,
    effective_crop,
    geometry_key,
)

LO, HI = -14.0, 4.0  # log2 range of the (linear) exposure axis of the film LUT
FILM_N, PRINT_N_FAST, PRINT_N, FIN_N = 41, 25, 41, 33

FILM_LIVE = ("film", "negative_contrast", "couplers", "couplers_amount")
PRINT_LIVE = ("paper", "bw_grade", "print_brightness", "auto_print_compensation", "yellow", "magenta", "preflash",
              "print_contrast", "developer_exhaustion", "white_correction", "black_correction")
# Everything pointwise in the finishing stage (tone, presence, colour grading, HSL, curves, creative LUT);
# vignette runs in the kernel, clarity only in the refined render.
FINISH_LIVE = tuple(f for f in FINISH_FIELDS if f not in ("vignette", "vignette_midpoint", "clarity"))
# Only visible in the refined render (spatial / stochastic / image-global):
SPATIAL_ONLY = {"grain", "grain_size", "halation", "halation_amount", "scatter_amount", "highlight_boost",
                "diffusion", "diffusion_family", "diffusion_strength", "film_format", "glare", "glare_amount",
                "sharpen", "clarity", "lens_correction"}


# ------------------------------------------------------------------ the per-pixel kernel

@njit(inline="always")
def _tri(lut, fx, fy, fz, ch):
    n0, n1, n2 = lut.shape[0], lut.shape[1], lut.shape[2]
    fx = min(max(fx, 0.0), n0 - 1.0001)
    fy = min(max(fy, 0.0), n1 - 1.0001)
    fz = min(max(fz, 0.0), n2 - 1.0001)
    x0, y0, z0 = int(fx), int(fy), int(fz)
    dx, dy, dz = fx - x0, fy - y0, fz - z0
    c00 = lut[x0, y0, z0, ch] + (lut[x0 + 1, y0, z0, ch] - lut[x0, y0, z0, ch]) * dx
    c10 = lut[x0, y0 + 1, z0, ch] + (lut[x0 + 1, y0 + 1, z0, ch] - lut[x0, y0 + 1, z0, ch]) * dx
    c01 = lut[x0, y0, z0 + 1, ch] + (lut[x0 + 1, y0, z0 + 1, ch] - lut[x0, y0, z0 + 1, ch]) * dx
    c11 = lut[x0, y0 + 1, z0 + 1, ch] + (lut[x0 + 1, y0 + 1, z0 + 1, ch] - lut[x0, y0 + 1, z0 + 1, ch]) * dx
    c0 = c00 + (c10 - c00) * dy
    c1 = c01 + (c11 - c01) * dy
    return c0 + (c1 - c0) * dz


@njit(inline="always")
def _eotf(v):
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


@njit(inline="always")
def _oetf(v):
    v = min(max(v, 0.0), 1.0)
    return 12.92 * v if v <= 0.0031308 else 1.055 * v ** (1.0 / 2.4) - 0.055


@njit(parallel=True, fastmath=True, nogil=True, cache=True)
def live_kernel(img, M, gain, lut_a, lo_a, scale_a, lut_b, dmin, dscale, lut_c, use_c,
                vig_amt, vig_mid, fx0, fy0, fw, fh, out):
    H, W = img.shape[0], img.shape[1]
    nc = lut_c.shape[0] - 1.0
    e0 = 0.15 + 0.6 * vig_mid
    k = 0.85 if vig_amt < 0 else 0.6
    for i in prange(H):
        yy = (i + fy0 + 0.5) / fh * 2.0 - 1.0
        for j in range(W):
            r0, g0, b0 = img[i, j, 0], img[i, j, 1], img[i, j, 2]
            r = (M[0, 0] * r0 + M[0, 1] * g0 + M[0, 2] * b0) * gain
            g = (M[1, 0] * r0 + M[1, 1] * g0 + M[1, 2] * b0) * gain
            b = (M[2, 0] * r0 + M[2, 1] * g0 + M[2, 2] * b0) * gain
            ir = (math.log2(max(r, 1e-9)) - lo_a) * scale_a
            ig = (math.log2(max(g, 1e-9)) - lo_a) * scale_a
            ib = (math.log2(max(b, 1e-9)) - lo_a) * scale_a
            d0 = _tri(lut_a, ir, ig, ib, 0)
            d1 = _tri(lut_a, ir, ig, ib, 1)
            d2 = _tri(lut_a, ir, ig, ib, 2)
            jr = (d0 - dmin[0]) * dscale[0]
            jg = (d1 - dmin[1]) * dscale[1]
            jb = (d2 - dmin[2]) * dscale[2]
            o0 = _tri(lut_b, jr, jg, jb, 0)
            o1 = _tri(lut_b, jr, jg, jb, 1)
            o2 = _tri(lut_b, jr, jg, jb, 2)
            if vig_amt != 0.0:
                xx = (j + fx0 + 0.5) / fw * 2.0 - 1.0
                rr = math.sqrt(xx * xx + yy * yy) / 1.4142135
                t = min(max((rr - e0) / (1.05 - e0), 0.0), 1.0)
                vg = 1.0 + vig_amt * t * t * (3.0 - 2.0 * t) * k
                o0 = _oetf(_eotf(min(max(o0, 0.0), 1.0)) * vg)
                o1 = _oetf(_eotf(min(max(o1, 0.0), 1.0)) * vg)
                o2 = _oetf(_eotf(min(max(o2, 0.0), 1.0)) * vg)
            if use_c:
                p0, p1, p2 = o0 * nc, o1 * nc, o2 * nc
                o0 = _tri(lut_c, p0, p1, p2, 0)
                o1 = _tri(lut_c, p0, p1, p2, 1)
                o2 = _tri(lut_c, p0, p1, p2, 2)
            out[i, j, 0] = np.uint8(min(max(o0 * 255.0 + 0.5, 0.0), 255.0))
            out[i, j, 1] = np.uint8(min(max(o1 * 255.0 + 0.5, 0.0), 255.0))
            out[i, j, 2] = np.uint8(min(max(o2 * 255.0 + 0.5, 0.0), 255.0))


def warmup():
    img = np.full((4, 4, 3), 0.18, np.float32)
    lut = np.zeros((3, 3, 3, 3), np.float32)
    out = np.empty((4, 4, 3), np.uint8)
    live_kernel(img, np.eye(3, dtype=np.float32), np.float32(1), lut, np.float32(LO), np.float32(1), lut,
                np.zeros(3, np.float32), np.ones(3, np.float32), lut, True, np.float32(-0.5), np.float32(0.5),
                np.float32(0), np.float32(0), np.float32(4), np.float32(4), out)


# ------------------------------------------------------------------ baking

def _grid(axes):
    a, b, c = np.meshgrid(*axes, indexing="ij")
    n = len(axes[0])
    return np.stack([a, b, c], -1).reshape(n * n, n, 3)


def _bake_params(s: DevelopSettings, *, keep_exposure: bool):
    p = engine.build_params(s, grain=False)
    if not keep_exposure:
        p.camera.exposure_compensation_ev = 0.0
    p.film_render.halation.boost_ev = 0.0
    p.debug.deactivate_spatial_effects = True
    p.debug.deactivate_stochastic_effects = True
    return p


def bake_film(s: DevelopSettings, n: int = FILM_N):
    from spektrafilm import Simulator, digest_params
    from spektrafilm.runtime.topology import Tap

    if engine.is_digital(s):  # identity: the "density" axis is just log2 exposure
        ax = np.linspace(LO, HI, n)
        return np.ascontiguousarray(_grid([ax, ax, ax]).reshape(n, n, n, 3), dtype=np.float32)
    ax = 2.0 ** np.linspace(LO, HI, n)
    sim = Simulator(digest_params(_bake_params(s, keep_exposure=False)))
    dens = sim._pipeline.process(_grid([ax, ax, ax]), collect=Tap.CMY_FILM)
    return np.ascontiguousarray(dens.reshape(n, n, n, 3), dtype=np.float32)


def density_range(s: DevelopSettings):
    if engine.is_digital(s):
        return np.full(3, LO, np.float32), np.full(3, HI, np.float32)
    prof = profiles.load(s.film)
    dmax = np.nanmax(np.asarray(prof.data.density_curves, np.float64), axis=0)
    dmax = np.where(np.isfinite(dmax), dmax, 3.0) * max(1.0, float(s.negative_contrast)) * 1.15 + 0.1
    return np.full(3, -0.05, np.float32), dmax.astype(np.float32)


def bake_print(s: DevelopSettings, dmin, dmax, n: int = PRINT_N):
    from spektrafilm import Simulator, digest_params
    from spektrafilm.runtime.topology import Tap

    axes = [np.linspace(dmin[c], dmax[c], n) for c in range(3)]
    if engine.is_digital(s):  # the digital tone map on a grid of log2 exposures
        lin = 2.0 ** _grid(axes)
        out = engine.digital_render(lin)
        return np.ascontiguousarray(out.reshape(n, n, n, 3), dtype=np.float32)
    sim = Simulator(digest_params(_bake_params(s, keep_exposure=s.auto_print_compensation)))
    out = sim._pipeline.process(_grid(axes), inject=Tap.CMY_FILM)
    return np.ascontiguousarray(np.clip(out, 0, 1).reshape(n, n, n, 3), dtype=np.float32)


def bake_finish(s: DevelopSettings, n: int = FIN_N):
    f = s.copy()
    f.vignette, f.clarity = 0.0, 0.0
    if finish.is_identity(f):
        return None
    e = np.linspace(0, 1, n, dtype=np.float32)
    out = finish.apply(_grid([e, e, e]).astype(np.float32), f)
    return np.ascontiguousarray(out.reshape(n, n, n, 3), dtype=np.float32)


class _LRU(OrderedDict):
    def __init__(self, cap):
        super().__init__()
        self.cap = cap

    def get_(self, k):
        if k in self:
            self.move_to_end(k)
            return self[k]
        return None

    def put(self, k, v):
        self[k] = v
        self.move_to_end(k)
        while len(self) > self.cap:
            self.popitem(last=False)


class LivePreview:
    """Owns the baked tables and screen-sized base images. Use from one thread."""

    def __init__(self, eng: engine.Engine):
        self.eng = eng
        self._base = _LRU(3)
        self._film = _LRU(6)
        self._print = _LRU(8)
        self._fin = _LRU(8)
        self._ev = _LRU(32)
        self._border = _LRU(4)
        self._dummy = np.zeros((2, 2, 2, 3), np.float32)
        self._inset = (0, 0)
        self.last_info: dict = {}

    def _base_image(self, path, s, size, uncropped):
        src = self.eng.proxy(path, s)
        key = (path, bool(s.lens_correction), geometry_key(s), size, uncropped)
        hit = self._base.get_(key)
        if hit is None:
            frame = engine.frame_geometry(src.image, s)
            geo = frame if uncropped else engine.crop_frame(frame, s)
            img = np.ascontiguousarray(engine.resize_long_edge(geo, size), np.float32)
            small = engine.resize_long_edge(geo, 256).astype(np.float32)
            scale = src.full_size[0] / src.image.shape[1]
            hit = (img, small, frame.shape[:2], geo.shape[:2], scale)
            self._base.put(key, hit)
        return src, hit

    def _tables(self, s: DevelopSettings, dragging: bool = False, *, bake: bool = True, cancel=lambda: False):
        """(film table, print table, finishing table or None, density minimum, density scale) for these
        settings; baked on demand, or None when bake=False and one is missing."""
        fkey = s.subset(FILM_LIVE)
        lut_a = self._film.get_(fkey)
        if lut_a is None:
            if not bake:
                return None
            lut_a = bake_film(s)
            self._film.put(fkey, lut_a)
        if cancel():
            raise engine.RenderCancelled
        dmin, dmax = density_range(s)
        paper = engine.effective_paper(s)
        n_print = PRINT_N_FAST if dragging else PRINT_N
        pkey = (s.film, s.negative_contrast, paper, s.subset(PRINT_LIVE),
                float(s.exposure_ev) if s.auto_print_compensation else 0.0)
        lut_b = self._print.get_((pkey, PRINT_N))  # prefer the precise table if it exists
        if lut_b is None:
            lut_b = self._print.get_((pkey, n_print))
        if lut_b is None:
            if not bake:
                return None
            ps = s.copy()
            ps.paper = paper
            lut_b = bake_print(ps, dmin, dmax, n_print)
            self._print.put((pkey, n_print), lut_b)
        if cancel():
            raise engine.RenderCancelled
        ckey = s.subset(FINISH_LIVE)
        lut_c = self._fin.get_(ckey)
        if lut_c is None and ckey not in self._fin:
            if not bake:
                return None
            lut_c = bake_finish(s)
            self._fin.put(ckey, lut_c)
        nb = lut_b.shape[0]
        dscale = ((nb - 1) / (dmax - dmin)).astype(np.float32)
        return lut_a, lut_b, lut_c, dmin, dscale

    def detail_tile(self, path: str, s: DevelopSettings, rect, zoom: float = 1.0):
        """A quick full-resolution view of rect (fractions of the framed photo) from the real-time tables —
        sharp and in the right colours, without grain, halation, clarity or sharpening yet — shown while the
        film is being developed. Same geometry as Engine.detail. None until the full-resolution photo has been
        decoded and the tables for these settings exist (it never decodes or bakes)."""
        hit = self.eng.full_cached(path, s)
        tables = self._tables(s, bake=False) if hit is not None else None
        if tables is None:
            return None
        (full, ev), (lut_a, lut_b, lut_c, dmin, dscale) = hit, tables
        H, W = full.shape[:2]
        x, y, w, h = rect
        x0, y0 = max(0, int(x * W)), max(0, int(y * H))
        x1, y1 = min(W, int(math.ceil((x + w) * W))), min(H, int(math.ceil((y + h) * H)))
        if x1 - x0 < 8 or y1 - y0 < 8:
            return None
        tile = full[y0:y1, x0:x1]
        f = min(1.0, max(float(zoom), 0.02))
        if f < 0.9:
            tile = engine.resize_to(tile, max(8, round((x1 - x0) * f)), max(8, round((y1 - y0) * f)))
        img = np.ascontiguousarray(tile, np.float32)
        fx, fy = img.shape[1] / (x1 - x0), img.shape[0] / (y1 - y0)
        out = np.empty(img.shape[:2] + (3,), np.uint8)
        live_kernel(img, np.eye(3, dtype=np.float32), np.float32(2.0 ** (ev + float(s.exposure_ev))), lut_a,
                    np.float32(LO), np.float32((lut_a.shape[0] - 1) / (HI - LO)), lut_b, dmin, dscale,
                    lut_c if lut_c is not None else self._dummy, lut_c is not None,
                    np.float32(float(s.vignette) / 100.0), np.float32(s.vignette_midpoint / 100.0),
                    np.float32(x0 * fx), np.float32(y0 * fy), np.float32(W * fx), np.float32(H * fy), out)
        text = engine.stamp_text(s, engine.read_exif(path))
        if text and not engine.date_in_margin(s, engine.PREFS["show_frame"]):
            from .borders import date_stamp

            out = date_stamp(out, text, frame=(x0 * fx, y0 * fy, W * fx, H * fy))
        return out, (x0, y0, x1, y1), (W, H)

    def render(self, path: str, s: DevelopSettings, size: int, *, dragging: bool = False,
               uncropped: bool = False, cancel=lambda: False) -> np.ndarray:
        self._inset = (0, 0)
        src, (img, small, frame_hw, geo_hw, scale) = self._base_image(path, s, size, uncropped)
        target = wb.target_for(s.wb_mode, s.temperature, s.tint, src.as_shot, src.auto)
        M = wb.adaptation_matrix(target, src.as_shot).astype(np.float32)
        ekey = (path, geometry_key(s), uncropped, round(target[0], 1), round(target[1], 2),
                s.subset(METER_FIELDS))
        ev = self._ev.get_(ekey)
        if ev is None:  # metered exactly like the refined render (WB and resizing are linear, so they commute)
            ev = engine.meter(wb.apply_matrix(small, M.astype(np.float64)), s)
            self._ev.put(ekey, ev)
        # film exposure is a gain on the film's input; only the print table depends on it, and only when
        # 'Lab auto-print' makes the enlarger compensate it
        gain = np.float32(2.0 ** (ev + float(s.exposure_ev)))
        lut_a, lut_b, lut_c, dmin, dscale = self._tables(s, dragging, cancel=cancel)
        h, w = img.shape[:2]
        out = np.empty((h, w, 3), np.uint8)
        vig = 0.0 if uncropped else float(s.vignette) / 100.0
        live_kernel(img, M, gain, lut_a, np.float32(LO), np.float32((lut_a.shape[0] - 1) / (HI - LO)),
                    lut_b, dmin, dscale, lut_c if lut_c is not None else self._dummy, lut_c is not None,
                    np.float32(vig), np.float32(s.vignette_midpoint / 100.0), np.float32(0), np.float32(0),
                    np.float32(w), np.float32(h), out)
        if not uncropped:
            kind, kw, text = engine.border_options(s, src.exif, engine.PREFS["show_frame"])
            if text:
                from .borders import date_stamp

                out = date_stamp(out, text)
            if kind != "none":
                out = self._with_border(out, kind, kw)
        l, t = self._inset
        fh, fw = frame_hw
        self.last_info = {
            "full_size": src.full_size,
            "frame_size": (round(fw * scale), round(fh * scale)),
            "crop_size": (round(geo_hw[1] * scale), round(geo_hw[0] * scale)),
            "crop_rect": effective_crop(s, fw, fh),
            "inset": (l, t, w, h), "image_size": (w, h),
            "as_shot": src.as_shot, "auto": src.auto, "wb": target, "raw": src.raw, "exif": src.exif,
            "note": src.note, "live": True,
        }
        return out

    def _with_border(self, photo: np.ndarray, kind: str, kw: dict) -> np.ndarray:
        """Composite the photo into a cached film-edge template (template + alpha, built once per size)."""
        h, w = photo.shape[:2]
        key = (kind, tuple(sorted(kw.items())), w, h)
        hit = self._border.get_(key)
        if hit is None:
            from .borders import apply_border, border_inset

            black = apply_border(np.zeros((h, w, 3), np.float32), kind, **kw)
            white = apply_border(np.ones((h, w, 3), np.float32), kind, **kw)
            alpha = np.clip(white - black, 0, 1)[..., :1].astype(np.float32)
            l, t, _, _ = border_inset(kind, w, h, kw.get("film_format", "135 (24×36)"))
            hit = ((black * 255).astype(np.float32), alpha, (l, t))
            self._border.put(key, hit)
        tmpl, alpha, (l, t) = hit
        out = tmpl.copy()
        region = out[t:t + h, l:l + w]
        a = alpha[t:t + h, l:l + w]
        region += photo.astype(np.float32) * a
        self._inset = (l, t)
        return np.clip(out + 0.5, 0, 255).astype(np.uint8)
