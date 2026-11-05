"""Film x paper colour check.

For every film stock and each paper it can be printed on, render a neutral grey ramp plus the 24
ColorChecker colours through the app's own pipeline (spatial / random effects off) and report:
  * the grey balance (CIELAB chroma C* of the printed greys; a neutral print has C* near 0),
  * whether spektrafilm's neutral-print-filter database has an entry for the pair,
  * the error of the app's fast settings (enlarger / scanner LUTs, fast stats) against the exact
    computation, as mean / max CIEDE2000 over all patches (default paper of each film).

Run: .venv\\Scripts\\python.exe -I -X utf8 -W ignore app\\tests\\check_neutrality.py
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="sprk_neutral_")
sys.path.insert(0, os.path.join(HERE, ".."))

import colour
import numpy as np

from spektralionkk import engine, live, profiles
from spektralionkk.settings import NO_PRINT, DevelopSettings

CHECKER_SRGB = [(115, 82, 68), (194, 150, 130), (98, 122, 157), (87, 108, 67), (133, 128, 177), (103, 189, 170),
                (214, 126, 44), (80, 91, 166), (193, 90, 99), (94, 60, 108), (157, 188, 64), (224, 163, 46),
                (56, 61, 150), (70, 148, 73), (175, 54, 60), (231, 199, 31), (187, 86, 149), (8, 133, 161),
                (243, 243, 242), (200, 200, 200), (160, 160, 160), (122, 122, 121), (85, 85, 85), (52, 52, 52)]
GREY_EV = [-3, -2, -1, 0, 1, 2]  # stops around 18 % grey
PATCH = 4


def chart():
    srgb = np.array(CHECKER_SRGB, np.float64) / 255.0
    lin = colour.RGB_to_RGB(srgb, colour.RGB_COLOURSPACES["sRGB"], colour.RGB_COLOURSPACES["ProPhoto RGB"],
                            apply_cctf_decoding=True, chromatic_adaptation_transform="Bradford")
    greys = np.array([[0.18 * 2.0 ** k] * 3 for k in GREY_EV])
    vals = np.concatenate([greys, np.maximum(lin, 0)], 0)
    img = np.repeat(np.repeat(vals[None, :, :], PATCH, 0), PATCH, 1)  # (PATCH, n*PATCH, 3)
    return np.ascontiguousarray(img, np.float64), len(GREY_EV)


def lab_of(out):
    n = out.shape[1] // PATCH
    rgb = np.array([out[:, i * PATCH:(i + 1) * PATCH].reshape(-1, 3).mean(0) for i in range(n)])
    xyz = colour.RGB_to_XYZ(rgb, colour.RGB_COLOURSPACES["sRGB"], apply_cctf_decoding=True)
    return colour.XYZ_to_Lab(xyz, colour.CCS_ILLUMINANTS["CIE 1931 2 Degree Standard Observer"]["D65"])


def render(s, img, exact=False):
    from spektrafilm import Simulator, digest_params

    p = live._bake_params(s, keep_exposure=True)  # spatial + random effects off, like the live tables
    if exact:
        p.settings.use_enlarger_lut = False
        p.settings.use_scanner_lut = False
        p.settings.use_fast_stats = False
    dp = digest_params(p)
    ev = engine.meter(np.full((64, 64, 3), 0.18), s)
    out = Simulator(dp)._pipeline.process(img * 2.0 ** ev)
    return np.clip(np.asarray(out, np.float64), 0, 1), dp


def main():
    from spektrafilm.runtime.params_builder import _get_neutral_print_filters

    db = _get_neutral_print_filters()
    img, ng = chart()
    only = set(sys.argv[1:])  # optional: film keys to check
    films = [f for f in profiles.film_stocks() if f.key != profiles.DIGITAL and (not only or f.key in only)]
    papers = profiles.print_papers()
    colour_papers = [p for p in papers if not p.bw]
    rows, refs = [], []
    for f in films:
        if f.kind == "positive":
            pairs = [NO_PRINT]
        elif f.bw:
            pairs = [profiles.BW_PAPER]
        else:
            pairs = [p.key for p in colour_papers]
        default_paper = engine.effective_paper(DevelopSettings(film=f.key, paper=NO_PRINT)) \
            if f.kind != "positive" else NO_PRINT
        for pk in pairs:
            s = DevelopSettings(film=f.key, paper=pk)
            out, dp = render(s, img)
            lab = lab_of(out)
            grey = lab[:ng]
            c = np.hypot(grey[:, 1], grey[:, 2])
            in_db = None
            if pk not in (NO_PRINT, profiles.BW_PAPER):  # aliases use their base stock's entry
                in_db = db.get(pk, {}).get(dp.enlarger.illuminant, {}).get(profiles.base_stock(f.key)) is not None
            row = {"film": f.key, "paper": pk, "default_paper": pk == default_paper, "in_db": in_db,
                   "C_mid": float(c[GREY_EV.index(0)]), "C_max": float(c.max()),
                   "ab_mid": [round(float(grey[GREY_EV.index(0), 1]), 2), round(float(grey[GREY_EV.index(0), 2]), 2)],
                   "L": [round(float(x), 1) for x in grey[:, 0]]}
            if pk == default_paper:
                ex, _ = render(s, img, exact=True)
                de = colour.delta_E(lab, lab_of(ex), method="CIE 2000")
                row["dE_fast_vs_exact_mean"] = float(de.mean())
                row["dE_fast_vs_exact_max"] = float(de.max())
                refs.append(row)
            rows.append(row)
            flag = "" if in_db in (None, True) else "  <-- no neutral filters in database"
            print(f"{f.key:32s} {pk:30s} C*mid {row['C_mid']:5.2f}  C*max {row['C_max']:5.2f}"
                  + (f"  dE fast/exact {row['dE_fast_vs_exact_mean']:.2f}/{row['dE_fast_vs_exact_max']:.2f}"
                     if "dE_fast_vs_exact_mean" in row else "") + flag, flush=True)
    path = os.path.join(HERE, "out", "neutrality.json" if not only else "neutrality_subset.json")
    with open(path, "w") as fh:
        json.dump(rows, fh, indent=1)
    missing = sorted({(r["film"], r["paper"]) for r in rows if r["in_db"] is False})
    print("\nmissing neutral-filter entries:", len(missing))
    for m in missing:
        print("   ", m)
    worst = sorted(rows, key=lambda r: -r["C_mid"])[:10]
    print("\nleast neutral mid-grey (C*):")
    for r in worst:
        print(f"    {r['film']:32s} {r['paper']:30s} {r['C_mid']:.2f}  a*b* {r['ab_mid']}  in_db={r['in_db']}")
    print("\nfast settings vs exact (default papers): mean dE00 %.2f, worst %.2f" % (
        np.mean([r["dE_fast_vs_exact_mean"] for r in refs]), max(r["dE_fast_vs_exact_max"] for r in refs)))


if __name__ == "__main__":
    main()
