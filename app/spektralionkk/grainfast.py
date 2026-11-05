"""Faster film grain with the same statistics as spektrafilm's particle model.

spektrafilm develops each emulsion sub-layer as a particle count per pixel: seeds ~ Poisson(n / saturation),
developed grains ~ Binomial(seeds, p). A binomially thinned Poisson count is itself Poisson, so the developed
count is exactly Poisson(n * p / saturation) (same mean, same variance, same distribution). Drawing that one
variate with numba's exact Poisson sampler replaces two loops of up to 30 uniform draws per pixel per layer,
which is where most of a full-resolution render's time went. Everything around it (dye-cloud blur, sub-layers,
micro-structure, final blur) is spektrafilm's own code.
"""

from __future__ import annotations

import numpy as np
from numba import njit, prange


@njit(parallel=True, nogil=True, cache=True)
def _grain_poisson(density, density_max, n_particles, uniformity, out):
    H, W = density.shape
    od = density_max / n_particles
    for i in prange(H):
        for j in range(W):
            p = density[i, j] / density_max
            if not p >= 1e-6:  # also catches NaN
                p = 1e-6
            elif p > 1.0 - 1e-6:
                p = 1.0 - 1e-6
            sat = 1.0 - p * uniformity * (1.0 - 1e-6)
            out[i, j] = np.random.poisson(n_particles / sat * p) * od * sat


def warmup():
    _grain_poisson(np.full((2, 2), 0.5), 2.0, 10.0, 0.97, np.empty((2, 2)))


def install():
    from spektrafilm.model import grain as grain_mod
    from spektrafilm.utils.fast_gaussian_filter import fast_gaussian_filter

    if getattr(grain_mod, "_sprk_fast", False):
        return
    original = grain_mod.layer_particle_model

    def layer_particle_model(density, density_max=2.2, n_particles_per_pixel=10, grain_uniformity=0.98, seed=None,
                             blur_particle=0.0, method="poisson_binomial", use_fast_stats=False):
        if method != "poisson_binomial" or np.ndim(density) != 2 or n_particles_per_pixel <= 0:
            return original(density, density_max, n_particles_per_pixel, grain_uniformity, seed, blur_particle,
                            method, use_fast_stats)
        out = np.empty(np.shape(density), np.float64)
        _grain_poisson(np.ascontiguousarray(density, dtype=np.float64), float(density_max),
                       float(n_particles_per_pixel), float(grain_uniformity), out)
        if blur_particle > 0:
            out = fast_gaussian_filter(out, blur_particle * np.sqrt(density_max / n_particles_per_pixel))
        return out

    grain_mod.layer_particle_model = layer_particle_model
    grain_mod._sprk_fast = True
