"""RAW checks on a real camera file (read-only).

Run: .venv\\Scripts\\python.exe -I -X utf8 -W ignore app\\tests\\test_raw.py <file.ARW>
"""
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import numpy as np
import psutil

from spektralionkk import engine, wb
from spektralionkk.settings import DevelopSettings

SRC = sys.argv[1]
fails = []
proc = psutil.Process()


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


class Peak:
    def __enter__(self):
        self.peak, self._run = proc.memory_info().rss, True
        self._t = threading.Thread(target=self._poll, daemon=True)
        self._t.start()
        return self

    def _poll(self):
        while self._run:
            self.peak = max(self.peak, proc.memory_info().rss)
            time.sleep(0.05)

    def __exit__(self, *a):
        self._run = False
        self._t.join()


def timed(label, fn):
    t = time.perf_counter()
    r = fn()
    dt = time.perf_counter() - t
    print(f"     {label}: {dt:.2f}s", flush=True)
    return r, dt


def main():
    from spektrafilm.utils.numba_warmup import warmup
    warmup()
    engine.configure_thread()
    as_shot = wb.raw_as_shot(SRC)
    print(f"     as-shot white balance from metadata: {as_shot}")
    check(as_shot is not None and 2000 < as_shot[0] < 9000 and abs(as_shot[1]) < 60, "plausible as-shot Kelvin/tint")
    eng = engine.Engine()
    s = DevelopSettings()
    src, _ = timed("open RAW (half-size decode + auto WB)", lambda: eng.proxy(SRC, s))
    a, _ = timed("draft", lambda: eng.render(SRC, s, "draft"))
    f, t_f = timed("fine 1600", lambda: eng.render(SRC, s, "fine", 1600))
    check(f.shape[0] > f.shape[1], f"portrait orientation {f.shape}")
    s2 = s.copy(); s2.saturation = 30; s2.contrast = 20
    _, t_fin = timed("finishing edit", lambda: eng.render(SRC, s2, "fine", 1600))
    check(t_fin < 0.8, "finishing edit fast on a 42 MP RAW")
    s3 = s.copy(); s3.exposure_ev = 0.5
    _, t_exp = timed("exposure edit (draft)", lambda: eng.render(SRC, s3, "draft"))
    _, t_hit = timed("reset (cached)", lambda: eng.render(SRC, s, "fine", 1600))
    check(t_hit < 0.05, "reset from cache")
    o, t_o = timed("original view", lambda: eng.original_display(SRC, s, 1600))
    check(t_o < 1.0 and o.shape == f.shape, "original view fast and aligned")
    sw = s.copy(); sw.wb_mode = "custom"; sw.temperature, sw.tint = as_shot
    same = eng.render(SRC, sw, "draft")
    check(np.abs(same.astype(int) - a.astype(int)).mean() < 0.5, "Custom at the as-shot values == As Shot")
    sw.temperature = as_shot[0] - 1500
    cooler = eng.render(SRC, sw, "draft")
    check((cooler[..., 2].astype(float) - cooler[..., 0]).mean() > (a[..., 2].astype(float) - a[..., 0]).mean() + 3,
          "lower Kelvin cools the RAW")
    sb = s.copy(); sb.film = "kodak_tri_x_400"; sb.paper = "ilford_multigrade_iv_rc"; sb.bw_grade = 3
    bw, _ = timed("B&W Tri-X grade 3", lambda: eng.render(SRC, sb, "fine", 1600))
    check(np.abs(bw.astype(int) - bw.mean(axis=2, keepdims=True)).mean() < 1.0, "B&W on the RAW is neutral")
    with Peak() as pk:
        (tile, box, full), _ = timed("1:1 detail (first, full decode)", lambda: eng.detail(SRC, s, (0.4, 0.3, 0.2, 0.15)))
    print(f"     detail peak memory {pk.peak / 2**30:.2f} GB")
    eng.drop_full()
    with Peak() as pk:
        out, t_x = timed(f"FULL 42 MP EXPORT ({engine.band_workers()} band worker(s))",
                         lambda: engine.render_full(SRC, s2))
    print(f"     export {out.shape[1]}x{out.shape[0]}, peak memory {pk.peak / 2**30:.2f} GB")
    f2 = eng.render(SRC, s2, "fine", 1600)
    small = engine.resize_long_edge(out, 1600)
    check(abs(float(small.mean()) - f2.mean() / 255) < 0.02, f"export matches preview ({small.mean():.3f} vs {f2.mean()/255:.3f})")
    print("RAW TESTS", "FAILED: " + "; ".join(fails) if fails else "PASSED")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
