"""Change each control from its default and measure the effect on the rendered image.

Run: .venv\\Scripts\\python.exe -I -X utf8 -W ignore app\\tests\\test_controls.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import numpy as np

from spektralionkk import engine
from spektralionkk.looks import LOOKS, look_values
from spektralionkk.settings import DevelopSettings

SRC = os.path.join(HERE, "out", "test_input.jpg")  # the colour chart: has texture, shadows and highlights

CASES = {
    "exposure_ev": 1.5, "auto_exposure": False, "metering": "highlight_weighted",
    "wb_mode": "tungsten", "temperature": 4000, "tint": 40,
    "contrast": 60, "highlights": -70, "shadows": 70, "whites": -60, "blacks": 60, "clarity": 80,
    "vibrance": 70, "saturation": -60, "cg_shadow_sat": 60, "cg_mid_sat": 60, "cg_high_sat": 60,
    "vignette": -70, "film": "kodak_ektar_100", "paper": "kodak_2383", "couplers": False,
    "couplers_amount": 2.0, "negative_contrast": 1.3, "print_brightness": 1.0,
    "yellow": 30, "magenta": 30, "preflash": 0.05, "print_contrast": 1.4, "developer_exhaustion": 0.8,
    "glare_amount": 0.2, "white_correction": True, "black_correction": True, "straighten": 5.0,
    "aspect": "1:1", "border": "135",
}


def main():
    from spektrafilm.utils.numba_warmup import warmup
    warmup()
    eng = engine.Engine()
    base_s = DevelopSettings()
    base = eng.render(SRC, base_s, "fine", 1400).astype(np.float32) / 255
    dead = []
    for field, val in CASES.items():
        s = base_s.copy()
        setattr(s, field, val)
        if field in ("temperature", "tint"):
            s.wb_mode = "custom"
            if field == "tint":
                s.temperature = 5500
        img = eng.render(SRC, s, "fine", 1400).astype(np.float32) / 255
        d = float("inf") if img.shape != base.shape else float(np.abs(img - base).mean())
        ok = d > 0.003
        if not ok:
            dead.append(field)
        print(f"{field:22s} -> {str(val):18s} mean|Δ| = {d:.4f}  {'ok' if ok else 'DEAD'}", flush=True)
    # spatial film effects act around bright lights at film scale: check them at 100% (grain off)
    night = os.path.join(HERE, "out", "test_night.png")
    if not os.path.exists(night):
        from PIL import Image as _I
        hh, ww = 1000, 1500
        im = np.full((hh, ww, 3), 0.04, np.float32)
        yy, xx = np.mgrid[0:hh, 0:ww]
        for cx, cy, r in ((300, 300, 18), (750, 260, 12), (1200, 320, 25)):
            im[(yy - cy) ** 2 + (xx - cx) ** 2 < r * r] = 1.0
        _I.fromarray((im * 255).astype(np.uint8)).save(night)
    g = base_s.copy(); g.grain = False; g.auto_exposure = False
    ref, _, _ = eng.detail(night, g, (0.12, 0.2, 0.15, 0.2))
    for field, val in (("halation", False), ("halation_amount", 3.0), ("scatter_amount", 2.5),
                       ("highlight_boost", 4.0), ("film_format", "6×7"), ("diffusion", True)):
        t = g.copy(); setattr(t, field, val)
        tile, _, _ = eng.detail(night, t, (0.12, 0.2, 0.15, 0.2))
        d = int(np.abs(tile.astype(int) - ref.astype(int)).max())
        ok = d >= 8
        if not ok:
            dead.append(field)
        print(f"{field:22s} -> {str(val):18s} at 100% around a lamp: max Δ {d:3d}/255  {'ok' if ok else 'DEAD'}")
    s = base_s.copy(); s.film = "kodak_tri_x_400"; s.paper = "ilford_multigrade_iv_rc"
    a = eng.render(SRC, s, "fine", 1400).astype(np.float32); s.bw_grade = 4.5
    b = eng.render(SRC, s, "fine", 1400).astype(np.float32)
    print(f"bw_grade 2 -> 4.5        std {a.std():.1f} -> {b.std():.1f}  {'ok' if b.std() > a.std() + 3 else 'DEAD'}")
    if not b.std() > a.std() + 3:
        dead.append("bw_grade")
    looks_imgs = {}
    for name, (_, _, values) in LOOKS.items():
        s = base_s.copy()
        for k, v in look_values(values).items():
            setattr(s, k, v)
        looks_imgs[name] = eng.render(SRC, s, "draft").astype(np.float32)
    names = list(looks_imgs)
    dup = [(x, y) for i, x in enumerate(names) for y in names[i + 1:]
           if looks_imgs[x].shape == looks_imgs[y].shape and np.abs(looks_imgs[x] - looks_imgs[y]).mean() < 1.0]
    print(f"{len(names)} looks render; indistinguishable pairs: {dup or 'none'}")
    print("DEAD CONTROLS:", dead or "none")
    sys.exit(1 if dead or dup else 0)


if __name__ == "__main__":
    main()
