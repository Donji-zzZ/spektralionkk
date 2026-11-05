"""Speed paths match spektrafilm: baked print + scan (fastprint), fused-Poisson grain, cached RGB->XYZ matrix,
and the banded full-resolution render.

Run: .venv\\Scripts\\python.exe -I -X utf8 -W ignore app\\tests\\test_fastprint.py
"""
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="sprk_fp_")
sys.path.insert(0, os.path.join(HERE, ".."))
import colour
import numpy as np
from PIL import Image

from spektralionkk import engine, fastprint
from spektralionkk.settings import DevelopSettings

OUT = os.path.join(HERE, "out")
SRC = os.path.join(OUT, "test_input.jpg")
fails = []
D65 = colour.CCS_ILLUMINANTS["CIE 1931 2 Degree Standard Observer"]["D65"]


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


def lab(rgb, cs):
    xyz = colour.RGB_to_XYZ(np.asarray(rgb, np.float64), cs, apply_cctf_decoding=True)
    return colour.XYZ_to_Lab(xyz, D65)


def source():
    if os.path.exists(SRC):
        img = np.asarray(Image.open(SRC).convert("RGB"), np.float32) / 255.0
    else:  # colour patches over a grey ramp
        h, w = 600, 900
        x = np.linspace(0, 1, w, dtype=np.float32)
        img = np.repeat(np.repeat(x[None, :, None], h, 0), 3, 2)
        rng = np.random.default_rng(3)
        for _ in range(40):
            y0, x0 = rng.integers(0, h - 80), rng.integers(0, w - 80)
            img[y0:y0 + 80, x0:x0 + 80] = rng.uniform(0.05, 0.95, 3)
    return engine.to_working(img, "sRGB", True)


def main():
    engine.install_speedups()
    work = source().astype(np.float64)

    # 1. the RGB -> XYZ matrix shortcut gives spektrafilm's numbers
    import spektrafilm.utils.spectral_upsampling as su

    sample = np.abs(np.random.default_rng(0).normal(0.3, 0.3, (64, 64, 3)))
    for cs, ill in (("ProPhoto RGB", "D55"), ("sRGB", "D65"), ("ProPhoto RGB", "T")):
        try:
            tc_a, b_a = su._rgb_to_tc_b(sample, cs, False, ill)
        except Exception as exc:  # unknown illuminant label in this spektrafilm version
            print(f"skip {cs}/{ill}: {exc}")
            continue
        import colour as c

        xyz = c.RGB_to_XYZ(sample, colourspace=cs, apply_cctf_decoding=False, illuminant=su._illuminant_to_xy(ill),
                           chromatic_adaptation_transform="CAT16")
        b_ref = np.sum(xyz, axis=-1)
        tc_ref = su._tri2quad(xyz[..., 0:2] / np.fmax(b_ref[..., None], 1e-10))
        check(np.abs(tc_a - tc_ref).max() < 1e-9 and np.abs(b_a - b_ref).max() < 1e-9,
              f"camera RGB->XYZ shortcut = colour-science ({cs}, {ill})")

    # 2. fused-Poisson grain has spektrafilm's statistics
    from spektrafilm.model import grain as grain_mod
    from spektrafilm.utils.fast_stats import fast_binomial, fast_poisson

    for n, d in ((4.0, 0.3), (25.0, 1.2), (90.0, 1.9)):
        dens = np.full((500, 500), d)
        p = np.clip(dens / 2.2, 1e-6, 1 - 1e-6)
        sat = 1 - p * 0.97 * (1 - 1e-6)
        ref = fast_binomial(fast_poisson(n / sat), p) * (2.2 / n) * sat
        new = grain_mod.layer_particle_model(dens, 2.2, n, 0.97, None, 0.0, "poisson_binomial", True)
        check(abs(new.mean() - ref.mean()) < 0.01 * d + 2e-3 and abs(new.std() / ref.std() - 1) < 0.03,
              f"grain n={n:g} density {d}: mean {new.mean():.4f}/{ref.mean():.4f}, std {new.std():.4f}/{ref.std():.4f}")

    # 3. baked print + scan vs spektrafilm per pixel (glare off: its noise is random in both)
    cases = [("Portra 400 / Endura", dict(), "sRGB"), ("Portra 400 / Endura", dict(), "Display P3"),
             ("Gold 200 +1 EV Y+20", dict(film="kodak_gold_200", paper="kodak_ektacolor_edge", exposure_ev=1.0,
                                          yellow=20.0), "sRGB"),
             ("Vision3 500T / 2383", dict(film="kodak_vision3_500t", paper="kodak_2383"), "ProPhoto RGB"),
             ("Velvia 100 slide", dict(film="fujifilm_velvia_100", paper="none"), "sRGB"),
             ("Tri-X / Multigrade 3", dict(film="kodak_tri_x_400", paper="ilford_multigrade_iv_rc", bw_grade=3.0),
              "sRGB"),
             ("Ektar, paper contrast 1.3, auto print", dict(film="kodak_ektar_100", print_contrast=1.3,
                                                            auto_print_compensation=True, exposure_ev=-1.0), "sRGB")]
    for label, kw, cs in cases:
        s = DevelopSettings(glare=False, **kw)
        sim = engine._simulator(s, output_color_space=cs)
        neg = engine._film_half(sim, work * 2.0)
        exact = engine._print_half(sim, neg)
        t0 = time.perf_counter()
        fast = fastprint.Printer(s, cs).apply(neg)
        de = colour.delta_E(lab(exact, cs), lab(fast, cs), method="CIE 2000")
        check(de.mean() < 0.12 and np.percentile(de, 99) < 0.8,
              f"print table {label} ({cs}): dE00 mean {de.mean():.3f}, p99 {np.percentile(de, 99):.3f}, "
              f"max {de.max():.2f}  ({time.perf_counter() - t0:.1f}s incl. bake)")

    # 4. banded full render == one-piece render (bands must not show)
    src_path = os.path.join(tempfile.mkdtemp(), "band.png")
    Image.fromarray((np.clip(engine._srgb_oetf(work[..., [0, 1, 2]].astype(np.float32)), 0, 1) * 255).astype(
        np.uint8)).save(src_path)
    s = DevelopSettings(grain=False, glare=False)
    old_band = engine.BAND_PIXELS
    try:
        whole = engine.render_full(src_path, s)
        engine.BAND_PIXELS = 60_000  # force many thin bands
        banded = engine.render_full(src_path, s)
    finally:
        engine.BAND_PIXELS = old_band
    diff = np.abs(whole.astype(np.float64) - banded) * 255
    check(whole.shape == banded.shape and diff.mean() < 0.15 and diff.max() < 3.0,
          f"banded render matches one piece: mean {diff.mean():.3f}, max {diff.max():.2f} (8-bit levels)")

    print("\n" + ("ALL PASSED" if not fails else f"{len(fails)} FAILED"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
