"""Compressed RAW formats through the whole app pipeline (decode, live preview, refined preview, export).

Samples (CC0, from raw.pixls.us) go in <repo>\\rawsamples\\<format>\\, or in the folder named by the
SPRK_RAWSAMPLES environment variable; the test is skipped without them.
Run: .venv\\Scripts\\python.exe -I -X utf8 -W ignore app\\tests\\test_rawformats.py
"""
import glob
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="sprk_rawfmt_")
sys.path.insert(0, os.path.join(HERE, ".."))
import numpy as np
from PIL import Image

from spektralionkk import engine, live
from spektralionkk.settings import DevelopSettings

ROOT = os.environ.get("SPRK_RAWSAMPLES") or os.path.abspath(os.path.join(HERE, "..", "..", "rawsamples"))
OUT = os.path.join(HERE, "out")
fails = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


def main():
    files = sorted(f for f in glob.glob(os.path.join(ROOT, "*", "*")) if engine.is_raw(f))
    if not files:
        print("SKIP: no samples in", ROOT)
        return 0
    from spektrafilm.utils.numba_warmup import warmup

    warmup()
    live.warmup()
    eng = engine.Engine()
    lp = live.LivePreview(eng)
    tiles = []
    for f in files:
        fmt = os.path.basename(os.path.dirname(f))
        t0 = time.perf_counter()
        try:
            src = eng.proxy(f, DevelopSettings())
        except Exception as exc:
            check(False, f"{fmt}: decode failed: {type(exc).__name__}: {exc}")
            continue
        t_dec = time.perf_counter() - t0
        he = fmt == "nikon_he"
        if he:
            check(not src.raw and src.note == engine.UNSUPPORTED_RAW_NOTE and max(src.full_size) > 7000,
                  f"{fmt}: unsupported codec falls back to the embedded full-size JPEG {src.full_size}")
        else:
            check(src.raw and not src.note, f"{fmt}: decoded as RAW {src.full_size} in {t_dec:.1f}s, as-shot "
                                            f"{src.as_shot[0]:.0f} K / {src.as_shot[1]:+.0f}")
        s = DevelopSettings()
        t0 = time.perf_counter()
        lv = lp.render(f, s, 1200)
        t_live = time.perf_counter() - t0
        t0 = time.perf_counter()
        img = eng.render(f, s, "fine", 1200)
        t_fine = time.perf_counter() - t0
        m, sd = img.mean() / 255, img.std() / 255
        check(0.12 < m < 0.85 and sd > 0.05, f"{fmt}: film render looks like a photo (mean {m:.2f}, std {sd:.2f}); "
                                            f"live {t_live:.2f}s, refined {t_fine:.2f}s")
        # the refined render adds sharpening / halation / coupler diffusion: compare tones and colours (low-pass)
        def lowpass(x):
            return np.asarray(Image.fromarray(x).resize((x.shape[1] // 8, x.shape[0] // 8), Image.Resampling.BOX),
                              float)

        d = np.abs(lowpass(lv) - lowpass(img)).mean() if lv.shape == img.shape else -1
        check(0 <= d < 4, f"{fmt}: live preview ≈ refined render (low-pass diff {d:.2f}/255)")
        th = engine.thumbnail(f, 256)
        check(th is not None and th.ndim == 3, f"{fmt}: filmstrip thumbnail")
        tile = Image.fromarray(img)
        tile.thumbnail((360, 360))
        tiles.append((fmt, tile))
    # export path (full-resolution decode) on the fallback file and one real RAW
    for fmt in ("nikon_he", "canon_cr3_craw"):
        hits = [f for f in files if os.path.basename(os.path.dirname(f)) == fmt]
        if not hits:
            continue
        t0 = time.perf_counter()
        out = engine.render_full(hits[0], DevelopSettings(), long_edge=1600)
        check(out.shape[1] == 1600 or out.shape[0] == 1600, f"{fmt}: export works ({out.shape[1]}x{out.shape[0]}, "
                                                            f"{time.perf_counter() - t0:.0f}s)")
    if tiles:
        w = 370 * min(5, len(tiles))
        rows = (len(tiles) + 4) // 5
        sheet = Image.new("RGB", (w, rows * 280), (24, 24, 26))
        for i, (fmt, tile) in enumerate(tiles):
            sheet.paste(tile, ((i % 5) * 370 + 5, (i // 5) * 280 + 5))
        sheet.save(os.path.join(OUT, "raw_formats.png"))
    print("RAW FORMAT TESTS", "FAILED: " + "; ".join(fails) if fails else "PASSED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
