"""Live (LUT) preview: speed and accuracy against the per-pixel chain and the refined render.

Run: .venv\\Scripts\\python.exe -I -X utf8 -W ignore app\\tests\\test_live.py [photo]
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import numpy as np

from spektralionkk import engine, live
from spektralionkk.settings import DevelopSettings

SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "out", "test_input.jpg")
fails = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


def timed(fn, reps=1):
    t = time.perf_counter()
    for _ in range(reps):
        r = fn()
    return r, (time.perf_counter() - t) / reps


def per_pixel_reference(eng, s, size):
    """The exact pointwise chain (spatial/stochastic effects off), rendered per pixel."""
    from spektrafilm import Simulator, digest_params

    src = eng.proxy(SRC, s)
    _, _, geo, ev, _ = eng._stages(SRC, s, src)
    work = engine.resize_long_edge(geo, size).astype(np.float64) * 2.0 ** ev
    p = live._bake_params(s, keep_exposure=True)
    out = Simulator(digest_params(p)).process(work)
    from spektralionkk import finish
    f = s.copy(); f.clarity = 0.0
    out = finish.apply(np.clip(out, 0, 1).astype(np.float32), f)
    return engine.to_u8(out)


def main():
    from spektrafilm.utils.numba_warmup import warmup
    warmup()
    live.warmup()
    engine.configure_thread()
    eng = engine.Engine()
    lp = live.LivePreview(eng)
    s = DevelopSettings()
    size = 1600
    img, t0 = timed(lambda: lp.render(SRC, s, size))
    print(f"     first live frame (decode + bakes): {t0:.2f}s")
    _, t = timed(lambda: lp.render(SRC, s, size), 10)
    check(t < 0.05, f"repeat live frame {t * 1000:.1f} ms")
    for k, v in (("exposure_ev", 0.7), ("temperature", 3800), ("vignette", -40)):
        s2 = s.copy(); setattr(s2, k, v)
        if k == "temperature":
            s2.wb_mode = "custom"
        _, t = timed(lambda: lp.render(SRC, s2, size), 5)
        check(t < 0.05, f"live {k} change, no re-bake: {t * 1000:.1f} ms per frame")
    s3 = s.copy(); s3.contrast, s3.saturation = 30, 25
    _, t = timed(lambda: lp.render(SRC, s3, size))
    check(t < 0.1, f"live finishing change (finish LUT re-bake): {t * 1000:.0f} ms")
    s4 = s.copy(); s4.couplers_amount = 1.5
    _, t = timed(lambda: lp.render(SRC, s4, size))
    check(t < 0.15, f"live film-chemistry change (film LUT re-bake): {t * 1000:.0f} ms")
    s5 = s.copy(); s5.yellow = 20
    _, t = timed(lambda: lp.render(SRC, s5, size, dragging=True))
    check(t < 0.2, f"live paper/enlarger change while dragging (25^3 print LUT): {t * 1000:.0f} ms")
    s6 = s.copy(); s6.film = "kodak_ektar_100"
    _, t = timed(lambda: lp.render(SRC, s6, size))
    print(f"     live film change (film + print LUTs): {t * 1000:.0f} ms")

    # accuracy
    for name, st in (("default", s), ("finishing", s3), ("B&W Tri-X", DevelopSettings(
            film="kodak_tri_x_400", paper="ilford_multigrade_iv_rc", bw_grade=3)),
                     ("slide Velvia", DevelopSettings(film="fujifilm_velvia_100", paper="none")),
                     ("WB 3800K", DevelopSettings(wb_mode="custom", temperature=3800)),
                     ("auto-print on", DevelopSettings(auto_print_compensation=True, exposure_ev=1.0))):
        a = lp.render(SRC, st, size).astype(int)
        ref = per_pixel_reference(eng, st, size).astype(int)
        d = np.abs(a - ref)
        check(d.mean() < 1.5 and np.percentile(d, 99.5) < 10,
              f"live vs exact pointwise chain [{name}]: mean {d.mean():.2f}/255, 99.5% {np.percentile(d, 99.5):.0f}/255")
        fine = eng.render(SRC, st, "fine", size).astype(int)
        if fine.shape == a.shape:
            print(f"     live vs refined render [{name}]: mean {np.abs(a - fine).mean():.2f}/255 "
                  "(difference = halation, coupler diffusion, glare, sharpening)")
    sb = s.copy(); sb.border = "135"
    b = lp.render(SRC, sb, size)
    fb = eng.render(SRC, sb, "fine", size)
    check(b.shape == fb.shape and lp.last_info["inset"] == eng.last_info["inset"], f"live film edge matches {b.shape}")
    unc = lp.render(SRC, DevelopSettings(aspect="1:1"), size, uncropped=True)
    check(abs(unc.shape[1] / unc.shape[0] - eng.render(SRC, DevelopSettings(), "draft").shape[1] /
              eng.render(SRC, DevelopSettings(), "draft").shape[0]) < 0.02, "uncropped frame for the crop tool")

    # quick full-resolution view while zooming in: from the tables, the moment the full photo is decoded
    sv = s.copy(); sv.vignette = -40
    lp.render(SRC, sv, size)
    eng.drop_full()
    check(lp.detail_tile(SRC, sv, (0.6, 0.1, 0.25, 0.25)) is None, "no quick detail before the full decode (it never waits)")
    eng.prefetch_full(SRC, sv)
    for rect, zoom in (((0.6, 0.1, 0.25, 0.25), 1.0), ((0.0, 0.0, 0.5, 0.5), 0.4)):
        res, t = timed(lambda: lp.detail_tile(SRC, sv, rect, zoom))
        if res is None:
            check(False, f"quick detail at {zoom:.0%} after the full decode")
            continue
        q, qbox, _ = res
        d, dbox, _ = eng.detail(SRC, sv, rect, zoom=zoom)
        diff = np.abs(q.reshape(-1, 3).mean(0) - d.reshape(-1, 3).mean(0)).max()
        check(qbox == dbox and q.shape == d.shape and diff < 6 and t < 0.5,
              f"quick detail at {zoom:.0%}: {t * 1000:.0f} ms, same tile as the developed one "
              f"({q.shape[1]}x{q.shape[0]}), mean colour within {diff:.1f}/255")
    print("LIVE TESTS", "FAILED: " + "; ".join(fails) if fails else "PASSED")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
