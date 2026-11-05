"""Headless engine checks: run with  .venv\\Scripts\\python.exe -I -X utf8 -W ignore app\\tests\\test_engine.py"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
from PIL import Image

from spektralionkk import engine, finish, wb
from spektralionkk.settings import DevelopSettings, NO_PRINT, effective_crop

OUT = os.path.join(os.path.dirname(__file__), "out")
os.makedirs(OUT, exist_ok=True)
fails = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


def timed(label, fn):
    t = time.perf_counter()
    r = fn()
    dt = time.perf_counter() - t
    print(f"     {label}: {dt:.3f}s", flush=True)
    return r, dt


def make_test_jpeg(path):
    h, w = 1600, 2400
    y, x = np.mgrid[0:h, 0:w]
    img = np.zeros((h, w, 3), np.float32)
    img[..., 0] = x / w
    img[..., 1] = y / h
    img[..., 2] = 0.5 + 0.5 * np.sin(x / 90.0) * np.cos(y / 70.0)
    colors = [(0.8, 0.2, 0.2), (0.2, 0.7, 0.3), (0.2, 0.3, 0.8), (0.9, 0.8, 0.3), (0.85, 0.6, 0.5), (0.5, 0.5, 0.5)]
    for i, c in enumerate(colors):
        img[1100:1450, 150 + i * 360:450 + i * 360] = c
    img[300:420, 1700:1820] = 1.0
    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(path, quality=95)


def save(arr, name):
    Image.fromarray(arr if arr.dtype == np.uint8 else (np.clip(arr, 0, 1) * 255).astype(np.uint8)).save(
        os.path.join(OUT, name))


def mean(img):
    return float(np.asarray(img, np.float32).mean() / (255.0 if img.dtype == np.uint8 else 1.0))


def rb(img):
    f = np.asarray(img, np.float32)
    return float(f[..., 0].mean() - f[..., 2].mean()) / (255.0 if img.dtype == np.uint8 else 1.0)


def main():
    src = os.path.join(OUT, "test_input.jpg")
    make_test_jpeg(src)
    from spektrafilm.utils.numba_warmup import warmup
    warmup()
    engine.configure_thread()
    eng = engine.Engine()
    s = DevelopSettings()

    # --- white balance model
    m = wb.adaptation_matrix((5500, 0), (5500, 0))
    check(np.allclose(m, np.eye(3)), "WB: scene == as-shot is identity")
    T, t = wb.xyz_to_kelvin_tint(wb.kelvin_tint_to_xyz(4200, 12))
    check(abs(T - 4200) < 5 and abs(t - 12) < 0.5, f"WB: Kelvin/tint round trip ({T:.0f}, {t:.1f})")
    grey = np.array([0.18, 0.18, 0.18])
    warm_m = wb.adaptation_matrix((3000, 0), (5500, 0))
    check((warm_m @ grey)[2] > (warm_m @ grey)[0], "WB: lower Kelvin makes the picture cooler")
    cast = np.array([0.25, 0.18, 0.12])  # warm cast
    T2, t2 = wb.neutralize(cast, (5500, 0))
    fixed = wb.adaptation_matrix((T2, t2), (5500, 0)) @ cast
    check(np.ptp(fixed / fixed.mean()) < 0.02, f"WB eyedropper neutralises a warm cast (T={T2:.0f})")

    # --- previews and caching
    a, t_draft = timed("draft (cold, incl. decode)", lambda: eng.render(src, s, "draft"))
    check(a.dtype == np.uint8 and a.shape[2] == 3, "draft renders uint8")
    f, t_fine = timed("fine 1600 (cold)", lambda: eng.render(src, s, "fine", 1600))
    check(max(f.shape[:2]) == 1600, "fine tier honours requested size")
    check(eng.last_info["grain_shown"] is False, "fit-size preview skips invisible grain (22 µm pixels)")
    save(f, "portra400_endura.png")
    _, t_hit = timed("same settings again (result cache)", lambda: eng.render(src, s, "fine", 1600))
    check(t_hit < 0.02, f"repeat render is instant ({t_hit*1000:.1f} ms)")

    s_fin = s.copy(); s_fin.saturation = 40; s_fin.contrast = 30; s_fin.vignette = -40
    g, t_fin = timed("finishing edit (no film re-run)", lambda: eng.render(src, s_fin, "fine", 1600))
    check(t_fin < 0.6, f"finishing edit under 0.6 s ({t_fin:.2f})")
    check(np.abs(g.astype(int) - f.astype(int)).mean() > 2, "finishing edit changes the image")
    corner, centre = g[:40, :40].mean(), g[700:760, 1000:1100].mean()
    check(corner < f[:40, :40].mean() - 5, "vignette darkens corners")
    save(g, "finish_edit.png")

    s_wb = s.copy(); s_wb.wb_mode = "custom"; s_wb.temperature = 3200
    cool, t_wb = timed("white balance 3200 K", lambda: eng.render(src, s_wb, "draft"))
    s_wb.temperature = 8000
    warm = eng.render(src, s_wb, "draft")
    check(rb(warm) > rb(cool) + 0.03, f"WB slider works on a JPEG (R-B {rb(cool):.3f} -> {rb(warm):.3f})")
    s_as = s.copy(); s_as.wb_mode = "custom"; s_as.temperature, s_as.tint = eng.last_info["as_shot"]
    same = eng.render(src, s_as, "draft")
    check(np.abs(same.astype(int) - a.astype(int)).mean() < 0.5, "custom WB at the as-shot values == As Shot")
    T3, t3 = eng.sample_wb(src, s, 0.5, 0.5)
    check(1500 <= T3 <= 50000, f"eyedropper returns a valid WB ({T3:.0f} K, {t3:.1f})")

    s_exp = s.copy(); s_exp.exposure_ev = 1.5
    e = eng.render(src, s_exp, "fine", 1600)
    check(mean(e) > mean(f) + 0.05, f"film exposure +1.5 brightens print ({mean(f):.3f} -> {mean(e):.3f})")

    # --- black & white
    s_bw = s.copy(); s_bw.film = "kodak_tri_x_400"; s_bw.paper = "ilford_multigrade_iv_rc"; s_bw.bw_grade = 2
    bw2 = eng.render(src, s_bw, "fine", 1600)
    chroma = float(np.abs(bw2.astype(int) - bw2.mean(axis=2, keepdims=True)).mean())
    check(chroma < 1.0, f"Tri-X on Multigrade is neutral (chroma {chroma:.2f})")
    s_bw.bw_grade = 4.5
    bw45 = eng.render(src, s_bw, "fine", 1600)
    check(bw45.std() > bw2.std() + 3, f"higher grade = more contrast ({bw2.std():.1f} -> {bw45.std():.1f})")
    save(bw45, "trix_grade45.png")
    s_cs = s.copy(); s_cs.film = "cinestill_800t"; s_cs.paper = "kodak_2383"
    cs = eng.render(src, s_cs, "fine", 1600)
    check(cs.shape == f.shape, "CineStill 800T renders")
    s_slide = s.copy(); s_slide.film = "fujifilm_velvia_100"; s_slide.paper = NO_PRINT
    check(np.abs(eng.render(src, s_slide, "fine", 1600).astype(int) - f.astype(int)).mean() > 2, "slide direct scan")
    s_negscan = s.copy(); s_negscan.paper = NO_PRINT  # negative + no print -> must not show a negative
    neg_img = eng.render(src, s_negscan, "fine", 1600)
    check(abs(mean(neg_img) - mean(f)) < 0.08, "negative film never displayed as an orange negative")

    # --- crop
    s_c = s.copy(); s_c.aspect = "Free"; s_c.crop_l, s_c.crop_t, s_c.crop_r, s_c.crop_b = 0.1, 0.2, 0.6, 0.9
    c = eng.render(src, s_c, "draft")
    check(abs(c.shape[1] / c.shape[0] - (0.5 * 2400) / (0.7 * 1600)) < 0.02, f"free crop rectangle {c.shape}")
    s_c.aspect = "1:1"
    l, t, r, b = effective_crop(s_c, 2400, 1600)
    check(abs((r - l) * 2400 - (b - t) * 1600) < 2, "aspect lock fits a square inside the rectangle")
    old = DevelopSettings.from_dict({"aspect": "3:2", "crop_zoom": 2.0, "crop_x": 0.5, "crop_y": 0.5, "tint": 1.0})
    check(abs(old.crop_l - 0.25) < 1e-6 and abs(old.crop_r - 0.75) < 1e-6 and old.tint == 0.0,
          "v2 crop/tint settings migrate")
    unc = eng.render_uncropped(src, s_c, "draft", 720)
    check(abs(unc.shape[1] / unc.shape[0] - 1.5) < 0.01, "crop tool gets the uncropped frame")

    # --- original, detail, export
    o, t_o = timed("original view", lambda: eng.original_display(src, s, 1600))
    _, t_o2 = timed("original view again", lambda: eng.original_display(src, s, 1600))
    check(o.shape == f.shape and t_o2 < 0.01, "original view matches size and is cached")
    tile, box, full = eng.detail(src, s, (0.6, 0.1, 0.25, 0.25))
    prev = f[int(0.1 * f.shape[0]):int(0.35 * f.shape[0]), int(0.6 * f.shape[1]):int(0.85 * f.shape[1])]
    check(abs(mean(tile) - mean(prev)) < 0.03, f"detail tile matches preview ({mean(tile):.3f} vs {mean(prev):.3f})")
    tile2, _, _ = eng.detail(src, s_fin, (0.0, 0.0, 0.2, 0.2))
    check(mean(tile2) < mean(eng.detail(src, s, (0.0, 0.0, 0.2, 0.2))[0]) - 0.02, "detail tile has the vignette")
    # below 100 % the tile is developed at the screen's resolution, not the photo's
    small_tile, sbox, _ = eng.detail(src, s, (0.6, 0.1, 0.25, 0.25), zoom=0.5)
    bw, bh = sbox[2] - sbox[0], sbox[3] - sbox[1]
    check(sbox == box and abs(small_tile.shape[1] - bw * 0.5) <= 2 and abs(small_tile.shape[0] - bh * 0.5) <= 2,
          f"50 % zoom: tile at screen resolution ({small_tile.shape[1]}x{small_tile.shape[0]} for a {bw}x{bh} box)")
    check(abs(mean(small_tile) - mean(tile)) < 0.02, f"...and the same picture ({mean(small_tile):.3f} vs {mean(tile):.3f})")
    vg_small = eng.detail(src, s_fin, (0.0, 0.0, 0.2, 0.2), zoom=0.4)[0]
    check(abs(mean(vg_small) - mean(tile2)) < 0.02, "...vignette placed the same at 40 %")
    full_img, t_exp = timed("export render (2400x1600)", lambda: engine.render_full(src, s_fin))
    small = engine.resize_long_edge(full_img, 1600)
    check(abs(mean(small) - mean(g)) < 0.02, f"export matches preview incl. finishing ({mean(small):.3f} vs {mean(g):.3f})")
    saved = engine.BAND_PIXELS
    engine.BAND_PIXELS = 900_000
    s_nogr = s_fin.copy(); s_nogr.grain = False; s_nogr.glare = False
    banded = engine.render_full(src, s_nogr)
    engine.BAND_PIXELS = saved
    whole = engine.render_full(src, s_nogr)
    check(np.abs(banded - whole).mean(axis=(1, 2)).max() < 0.01, "banded export seamless incl. vignette/clarity")
    for fmt, ext in (("jpeg", ".jpg"), ("tiff", ".tif"), ("png", ".png")):
        p = os.path.join(OUT, "export" + ext)
        engine.save_image(p, full_img, color_space="sRGB", fmt=fmt)
        check(os.path.getsize(p) > 10000, f"saved {ext}")
    check(engine.thumbnail(src, 200) is not None, "thumbnail")
    print("ENGINE TESTS", "FAILED: " + "; ".join(fails) if fails else "PASSED")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
