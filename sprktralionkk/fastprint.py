"""Fast print + scan for full-resolution renders (exports, refined previews).

Everything spektrafilm does after the negative is developed is per-pixel except glare and the scanner's
sharpening: enlarger exposure through the filter pack, paper development, the scanner's spectral read-out,
the output colour space and its gamut compression. So for a given film / paper / enlarger setting that part
is one smooth function of the negative's three dye densities. It is baked once into a 65^3 table by running
spektrafilm itself on a grid of densities (exact spectral maths, no smaller internal tables), then every
pixel is a single multi-threaded table lookup instead of spectral maths and a CAM16 gamut compression.
Glare and sharpening are then applied exactly as spektrafilm applies them.

Accuracy against spektrafilm's own per-pixel path is checked by tests/test_fastprint.py (well below a
visible difference); a 42 MP print + scan drops from ~50 s of CPU to ~2 s.
"""

from __future__ import annotations

import threading
from collections import OrderedDict

import numpy as np
from numba import njit, prange

LUT_N = 65


@njit(parallel=True, fastmath=True, nogil=True, cache=True)
def _lut_kernel(neg, lut, dmin, dscale, out):
    """neg: HxWx3 dye densities; lut: NxNxNx3 holding cbrt(linear RGB); out: linear RGB (float32)."""
    H, W = neg.shape[0], neg.shape[1]
    top = lut.shape[0] - 1.0001
    for i in prange(H):
        for j in range(W):
            fx = min(max((neg[i, j, 0] - dmin[0]) * dscale[0], 0.0), top)
            fy = min(max((neg[i, j, 1] - dmin[1]) * dscale[1], 0.0), top)
            fz = min(max((neg[i, j, 2] - dmin[2]) * dscale[2], 0.0), top)
            x0, y0, z0 = int(fx), int(fy), int(fz)
            dx, dy, dz = fx - x0, fy - y0, fz - z0
            for c in range(3):
                c00 = lut[x0, y0, z0, c] + (lut[x0 + 1, y0, z0, c] - lut[x0, y0, z0, c]) * dx
                c10 = lut[x0, y0 + 1, z0, c] + (lut[x0 + 1, y0 + 1, z0, c] - lut[x0, y0 + 1, z0, c]) * dx
                c01 = lut[x0, y0, z0 + 1, c] + (lut[x0 + 1, y0, z0 + 1, c] - lut[x0, y0, z0 + 1, c]) * dx
                c11 = lut[x0, y0 + 1, z0 + 1, c] + (lut[x0 + 1, y0 + 1, z0 + 1, c] - lut[x0, y0 + 1, z0 + 1, c]) * dx
                c0 = c00 + (c10 - c00) * dy
                c1 = c01 + (c11 - c01) * dy
                v = c0 + (c1 - c0) * dz
                out[i, j, c] = v * v * v


def warmup():
    lut = np.zeros((3, 3, 3, 3), np.float32)
    out = np.empty((2, 2, 3), np.float32)
    _lut_kernel(np.zeros((2, 2, 3), np.float32), lut, np.zeros(3, np.float32), np.ones(3, np.float32), out)


def _grid(axes):
    a, b, c = np.meshgrid(*axes, indexing="ij")
    n = len(axes[0])
    return np.stack([a, b, c], -1).reshape(n * n, n, 3)


def _encoder(color_space: str):
    from . import engine

    if color_space == "sRGB":
        return lambda x: engine._srgb_oetf(x).astype(np.float32)
    import colour

    cs = colour.RGB_COLOURSPACES[color_space]
    return lambda x: np.asarray(cs.cctf_encoding(np.clip(x, 0.0, 1.0)), np.float32)


class Printer:
    """Print + scan of one film / paper / enlarger setting into one output colour space."""

    def __init__(self, s, output_color_space: str = "sRGB", n: int = LUT_N):
        import colour
        from opt_einsum import contract
        from spektrafilm import Simulator, digest_params
        from spektrafilm.config import STANDARD_OBSERVER_CMFS
        from spektrafilm.model.illuminants import standard_illuminant
        from spektrafilm.runtime.topology import Tap

        from . import engine, live

        self.color_space = output_color_space
        # the settings spektrafilm would use for this render (glare, sharpening, encoding)
        ref = Simulator(digest_params(engine.build_params(s, output_color_space=output_color_space)))._pipeline
        self.scan_film = bool(ref.io.scan_film)
        glare = ref.print_render.glare
        self.glare = (glare.percent, glare.roughness, glare.blur) if (glare.active and glare.percent > 0
                                                                      and not self.scan_film) else None
        self.lens_blur = float(ref.scanner.lens_blur or 0.0)
        self.unsharp = tuple(float(v) for v in ref.scanner.unsharp_mask)
        self.encode = _encoder(output_color_space) if ref.io.output_cctf_encoding else None
        if self.glare:
            prof = ref.print
            ill = standard_illuminant(prof.info.viewing_illuminant)
            ill_xyz = contract("k,kl->l", ill, STANDARD_OBSERVER_CMFS[:]) / np.sum(ill * STANDARD_OBSERVER_CMFS[:, 1])
            self.glare_rgb = np.asarray(colour.XYZ_to_RGB(ill_xyz, colourspace=output_color_space,
                                                          apply_cctf_encoding=False,
                                                          illuminant=colour.XYZ_to_xy(ill_xyz)), np.float32)

        # the pointwise rest, baked: exact spectral maths (no internal 17^3 tables), linear output
        p = engine.build_params(s, output_color_space=output_color_space)
        p.settings.use_enlarger_lut = False
        p.settings.use_scanner_lut = False
        p.io.output_cctf_encoding = False
        p.debug.deactivate_spatial_effects = True
        p.debug.deactivate_stochastic_effects = True
        sim = Simulator(digest_params(p))
        dmin, dmax = live.density_range(s)
        axes = [np.linspace(float(dmin[c]), float(dmax[c]), n) for c in range(3)]
        lin = sim._pipeline.process(_grid(axes), inject=Tap.CMY_FILM)
        lin = np.clip(np.nan_to_num(np.asarray(lin, np.float64), nan=0.0), 0.0, None)
        self.lut = np.ascontiguousarray(np.cbrt(lin).reshape(n, n, n, 3), dtype=np.float32)
        self.dmin = np.asarray(dmin, np.float32)
        self.dscale = np.asarray((n - 1) / (np.asarray(dmax, np.float64) - np.asarray(dmin, np.float64)), np.float32)

    def linear(self, neg: np.ndarray) -> np.ndarray:
        """Linear output RGB (gamut compressed, no glare / sharpening) of a block of the negative."""
        neg = np.ascontiguousarray(neg, dtype=np.float32)
        out = np.empty(neg.shape, np.float32)
        _lut_kernel(neg, self.lut, self.dmin, self.dscale, out)
        return out

    def apply(self, neg: np.ndarray) -> np.ndarray:
        """Block of the negative (dye densities) -> output-encoded RGB in [0, 1], float32."""
        from spektrafilm.model.diffusion import apply_gaussian_blur, apply_unsharp_mask
        from spektrafilm.model.glare import compute_random_glare_amount

        rgb = self.linear(neg)
        if self.glare:
            amount = compute_random_glare_amount(*self.glare, rgb.shape[:2]).astype(np.float32)
            rgb += amount[..., None] * self.glare_rgb
        sigma, amount = self.unsharp
        if self.lens_blur > 0 or (sigma > 0 and amount > 0):
            rgb = np.asarray(rgb, np.float64)
            rgb = apply_gaussian_blur(rgb, self.lens_blur)
            if sigma > 0 and amount > 0:
                rgb = apply_unsharp_mask(rgb, sigma=sigma, amount=amount)
        if self.encode is not None:
            rgb = self.encode(rgb)
        return np.clip(np.nan_to_num(np.asarray(rgb, np.float32), nan=0.0), 0.0, 1.0)


_cache: OrderedDict = OrderedDict()
_lock = threading.Lock()


def printer_for(s, output_color_space: str = "sRGB") -> Printer:
    """Cached per print-relevant settings (a batch export with one look bakes once). The print depends on the
    film's dye and curve data, the negative's gamma (it sets the enlarger's mid-grey balance), the film
    exposure only when the lab auto-print compensates it, and the print / scan settings."""
    from .settings import PRINT_FIELDS

    key = (s.film, round(float(s.negative_contrast), 4),
           round(float(s.exposure_ev), 4) if s.auto_print_compensation else None,
           s.subset(PRINT_FIELDS), output_color_space)
    with _lock:
        hit = _cache.get(key)
        if hit is not None:
            _cache.move_to_end(key)
            return hit
    pr = Printer(s, output_color_space)
    with _lock:
        _cache[key] = pr
        while len(_cache) > 6:
            _cache.popitem(last=False)
    return pr
