"""Entry point for the frozen spektralionkk app (PyInstaller; Windows .exe and macOS .app)."""
import multiprocessing
import os
import sys

if getattr(sys, "frozen", False):
    sys.dont_write_bytecode = True  # never write into the app folder (a signed macOS bundle must stay unchanged)


def _setup_env():
    from spektralionkk.platform_util import data_root

    root = data_root()  # %LOCALAPPDATA%\spektralionkk  |  ~/Library/Application Support/spektralionkk
    try:  # bring the library of the app's old name (sprktralionkk) along, before anything creates the new folder
        from spektralionkk.migrate import migrate_old_data

        migrate_old_data(os.path.dirname(root))
    except Exception:
        pass
    cache = os.path.join(root, "numba_cache")
    os.makedirs(cache, exist_ok=True)
    os.environ.setdefault("NUMBA_CACHE_DIR", cache)
    os.environ.setdefault("QT_API", "pyside6")
    started_from_finder = sys.platform == "darwin" and getattr(sys, "frozen", False) and not _is_terminal()
    if sys.stdout is None or sys.stderr is None or started_from_finder:  # windowed app: keep a log
        log = open(os.path.join(root, "spektralionkk.log"), "a", buffering=1, encoding="utf-8")
        sys.stdout = log if started_from_finder else (sys.stdout or log)
        sys.stderr = log if started_from_finder else (sys.stderr or log)
        try:  # a crash inside native code still leaves a trace in the log
            import faulthandler

            faulthandler.enable(log)
        except Exception:
            pass
    return root


def _is_terminal() -> bool:
    try:
        return sys.stderr is not None and sys.stderr.isatty()
    except Exception:
        return False


def _selftest(root: str, quiet: bool) -> int:
    """Compile kernels, render a test image through the real engine and export it.

    Usage: spektralionkk.exe --selftest            (Windows)
           spektralionkk.app/Contents/MacOS/spektralionkk --selftest   (macOS)
    The report is selftest.txt in the app's data folder.
    """
    import platform
    import tempfile
    import time
    import traceback

    lines = [f"CPU: {platform.processor() or platform.machine()}", f"System: {platform.platform()}",
             f"Cores: {os.cpu_count()}"]
    ok = True
    try:
        import numpy as np
        from PIL import Image

        t = time.perf_counter()
        from spektralionkk import numba_guard

        guarded = numba_guard.install()
        from spektrafilm.utils.numba_warmup import warmup
        warmup()
        lines.append(f"kernels ready ({time.perf_counter() - t:.1f}s), threading: {numba_guard.threading_layer()}"
                     + (" (renders take turns)" if guarded else ""))

        from spektralionkk import engine, i18n
        from spektralionkk.settings import DevelopSettings

        i18n.init()
        lines.append(f"interface language: {i18n.LANGS[i18n.LANG]} ({i18n.LANG})")

        tmp = tempfile.mkdtemp(prefix="sprk_selftest_")
        src = os.path.join(tmp, "chart.jpg")
        y, x = np.mgrid[0:600, 0:900]
        img = np.stack([x / 900, y / 600, 0.5 + 0.5 * np.sin(x / 40.0)], -1)
        Image.fromarray((img * 255).astype(np.uint8)).save(src, quality=95)
        eng = engine.Engine()
        s = DevelopSettings()
        t = time.perf_counter(); eng.render(src, s, "draft"); lines.append(f"preview render OK ({time.perf_counter() - t:.1f}s)")
        s.yellow = 15
        t = time.perf_counter(); eng.render(src, s, "draft"); lines.append(f"print-side edit OK ({time.perf_counter() - t:.2f}s)")
        s.saturation, s.vignette, s.clarity = 30, -30, 20
        t = time.perf_counter(); eng.render(src, s, "draft"); lines.append(f"finishing edit OK ({time.perf_counter() - t:.2f}s)")
        bw = DevelopSettings(film="kodak_tri_x_400", paper="ilford_multigrade_iv_rc", bw_grade=3.0)
        img = eng.render(src, bw, "draft")
        chroma = float(np.abs(img.astype(int) - img.mean(axis=2, keepdims=True)).mean())
        assert chroma < 1.5, f"B&W print not neutral ({chroma:.2f})"
        lines.append("black & white profiles OK (Tri-X on Multigrade)")
        from spektralionkk.looks import LOOKS, look_values
        for name, (_, _, values) in LOOKS.items():
            ls = DevelopSettings()
            for k, v in look_values(values).items():
                setattr(ls, k, v)
            eng.render(src, ls, "thumb")
        lines.append(f"all {len(LOOKS)} looks render OK")
        from spektralionkk import live, presets
        t = time.perf_counter()
        live.warmup()
        lp = live.LivePreview(eng)
        lp.render(src, s, 900)
        s2 = s.copy()
        s2.exposure_ev = 1.0
        t2 = time.perf_counter()
        lp.render(src, s2, 900, dragging=True)
        lines.append(f"real-time preview OK (tables {t2 - t:.1f}s, slider frame {(time.perf_counter() - t2) * 1000:.0f} ms)")
        # the app renders on several threads at once (refined render, live preview): that must be safe with every
        # numba threading layer (workqueue on most Macs is not thread-safe on its own; engine.numba_guard handles it)
        import threading

        errors = []

        def refine():
            try:
                eng.render(src, s2, "fine", 1200)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        th = threading.Thread(target=refine)
        th.start()
        for ev in (0.5, -0.5, 0.25):
            s3 = s.copy()
            s3.exposure_ev = ev
            lp.render(src, s3, 900, dragging=True)
        th.join()
        assert not errors, errors
        lines.append("concurrent live preview + refined render OK")
        xmp = os.path.join(tmp, "test.xmp")
        with open(xmp, "w", encoding="utf-8") as fh:
            fh.write('<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-'
                     'syntax-ns#"><rdf:Description xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/" '
                     'crs:Contrast2012="+20" crs:Saturation="-10"/></rdf:RDF></x:xmpmeta>')
        pr = presets.import_file(xmp)
        assert pr.values.get("contrast") == 20, pr.values
        dg = DevelopSettings(film="digital", border="135", date_stamp=True, date_text="'26 11 05")
        dg.contrast = 20
        eng.render(src, dg, "draft")
        lines.append("preset import, Digital profile, film frame and date stamp OK")
        t = time.perf_counter()
        out = engine.render_full(src, s, output_color_space="sRGB")
        engine.save_image(os.path.join(tmp, "out.jpg"), out, color_space="sRGB", fmt="jpeg")
        lines.append(f"full render + JPEG export OK ({time.perf_counter() - t:.1f}s)")
    except Exception:
        ok = False
        lines.append("FAILED:\n" + traceback.format_exc())
    lines.append("RESULT: " + ("PASS" if ok else "FAIL"))
    text = "\n".join(lines)
    with open(os.path.join(root, "selftest.txt"), "w", encoding="utf-8") as fh:
        fh.write(text)
    if not quiet:
        print(text)
        if sys.platform.startswith("win"):
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(None, text, "spektralionkk self-test", 0x40 if ok else 0x10)
            except Exception:
                pass
    return 0 if ok else 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    import warnings

    warnings.filterwarnings("ignore", message=".*Matplotlib.*")  # plotting is not bundled
    warnings.filterwarnings("ignore", category=RuntimeWarning)  # NaN guards inside colour maths
    root = _setup_env()
    if "--selftest" in sys.argv or "--selftest-quiet" in sys.argv:
        sys.exit(_selftest(root, quiet="--selftest-quiet" in sys.argv))
    from spektralionkk.app import main

    sys.exit(main())
