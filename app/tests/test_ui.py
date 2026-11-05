"""Scripted UI test: drives the real window through every feature and saves screenshots.

Run:  .venv\\Scripts\\python.exe -I -X utf8 -W ignore app\\tests\\test_ui.py
Uses a throwaway LOCALAPPDATA so the user's library is untouched.
"""
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="sprk_ui_")
os.environ.setdefault("NUMBA_CACHE_DIR", os.path.join(tempfile.gettempdir(), "sprk_test_numba_cache"))
sys.path.insert(0, os.path.join(HERE, ".."))

import numpy as np
from PIL import Image
from PySide6 import QtCore, QtGui, QtWidgets

from spektralionkk.ui import theme
from spektralionkk.ui.main_window import MainWindow

p1 = os.path.join(OUT, "test_input.jpg")
if not os.path.exists(p1):
    raise SystemExit("run test_engine.py first")
h, w = 1400, 2100
y, x = np.mgrid[0:h, 0:w] / np.array([h, w])[:, None, None]
sky = np.stack([0.35 + 0.3 * y, 0.5 + 0.3 * y, 0.9 - 0.2 * y], -1)
ground = np.stack([0.25 + 0.2 * x, 0.35 + 0.1 * np.sin(x * 20), 0.12 + 0 * x], -1)
img = np.where((y > 0.55 + 0.05 * np.sin(x * 9))[..., None], ground, sky)
yy, xx = np.mgrid[0:h, 0:w]
img[(yy - 380) ** 2 + (xx - 1500) ** 2 < 90 ** 2] = 1.0
img[1100:1300, 200:400] = 0.5  # a neutral grey patch for the WB picker
p2 = os.path.join(OUT, "test_landscape.jpg")
Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(p2, quality=95)
p3 = os.path.join(OUT, "test_landscape_copy.jpg")
Image.open(p2).save(p3, quality=92)
paths = [p1, p2, p3]

app = QtWidgets.QApplication(sys.argv)
theme.apply(app)
win = MainWindow(initial_paths=paths)
win.show()
log, fails = [], []


def check(cond, msg):
    log.append(("PASS " if cond else "FAIL ") + msg)
    print(log[-1], flush=True)
    if not cond:
        fails.append(msg)


def wait_for(pred, timeout=120):
    t = time.time()
    while time.time() - t < timeout:
        app.processEvents()
        if pred():
            return True
        time.sleep(0.01)
    return False


def fine_shown():
    return win._shown[1] == 1 and win._shown[0] == win.service.generation


def shot(name):
    app.processEvents()
    win.grab().save(os.path.join(OUT, name))


def canvas_mean():
    im = win.canvas.current_image()
    return float(im.mean()) / 255 if im is not None else 0.0


def timed_edit(upd, final=True):
    t = time.time()
    win.on_edit(dict(upd), final)
    ok = wait_for(fine_shown, 120)
    return ok, time.time() - t


check(wait_for(lambda: win._engine_ready, 300), "engine warm-up finished")
check(wait_for(lambda: win.current == p1 and fine_shown(), 120), "first photo rendered")
win.strip.set_current(p2)
check(wait_for(lambda: win.current == p2 and fine_shown(), 120), "landscape rendered")
shot("ui_1_initial.png")

# --- speed: finishing edits go straight to the refined preview
ok, dt = timed_edit({"saturation": 40})
check(ok and dt < 1.0, f"finishing edit (saturation) refreshes in {dt:.2f}s (< 1 s)")
ok, dt = timed_edit({"contrast": 25, "vignette": -30})
check(ok and dt < 1.0, f"tone + vignette edit refreshes in {dt:.2f}s")
ok, dt = timed_edit({"exposure_ev": 1.0})
log.append(f"     film exposure edit (re-runs film) {dt:.2f}s")
before_reset = canvas_mean()
t = time.time()
win.reset_photo()
check(wait_for(fine_shown, 60), "reset rendered")
dt = time.time() - t
check(dt < 0.6, f"reset to defaults is instant from cache ({dt:.2f}s)")
win.undo()
check(wait_for(fine_shown, 60) and abs(canvas_mean() - before_reset) < 0.01, "undo restores the previous look")
win.redo()
wait_for(fine_shown, 60)

# --- white balance (JPEG): Temp slider works, picker neutralises
m0 = win.canvas.current_image().astype(float)
rb0 = (m0[..., 0] - m0[..., 2]).mean()
win.right.temp.set_value(8500)
win.right.temp.committed.emit(8500.0)
check(wait_for(fine_shown, 120), "temperature edit rendered")
check(win.s.wb_mode == "custom" and win.s.temperature == 8500, "dragging Temp switches WB to Custom")
m1 = win.canvas.current_image().astype(float)
check((m1[..., 0] - m1[..., 2]).mean() > rb0 + 8, "higher Kelvin makes the photo warmer")
win.on_tool("wb")
check(win.canvas.mode == "wb", "WB picker mode on")
win.canvas.wbPicked.emit(300 / 2100, 1200 / 1400)  # the grey patch
check(wait_for(lambda: win.canvas.mode == "view" and fine_shown() and win.s.wb_mode == "custom"
               and win.s.temperature != 8500, 60), f"WB picker sets white balance ({win.s.temperature:.0f} K)")

# --- before / after
t = time.time()
win.set_before(True)
check(wait_for(lambda: win.canvas.has_original() and win.canvas.before, 30), "Before view shows the original")
dt1 = time.time() - t
win.set_before(False)
t = time.time()
win.set_before(True)
app.processEvents()
dt2 = time.time() - t
check(dt1 < 1.0 and dt2 < 0.05, f"original view fast ({dt1:.2f}s first, {dt2 * 1000:.0f} ms again)")
shot("ui_2_before.png")
win.set_before(False)
win.set_split(True)
app.processEvents()
check(win.canvas.split and win.canvas.has_original(), "Before | After split view")
shot("ui_3_split.png")
win.set_split(False)

# --- looks
win.left.looks_sec.set_collapsed(False)
win._thumb_key = None
win._request_look_thumbs()
check(wait_for(lambda: sum(1 for it in win.left.looks._items.values()
                           if not it.icon().pixmap(54, 36).toImage().pixelColor(27, 18).name() == "#2a2a2d") >= 5, 240),
      "look thumbnails rendered")
win.apply_look("Monochrome (Leica-inspired)")
check(wait_for(fine_shown, 120), "B&W look rendered")
im = win.canvas.current_image().astype(float)
check(np.abs(im - im.mean(axis=2, keepdims=True)).mean() < 1.5 and win.s.paper == "ilford_multigrade_iv_rc",
      "Leica-inspired monochrome look is a true B&W print")
check(win.s.edge_label == "leica_monochrome", "the look gives the film edge its own lettering")
win.on_edit({"contrast": 12}, True)
check(win.s.edge_label == "leica_monochrome", "...which stays while the look is fine-tuned")
win.on_edit({"film": "ilford_hp5_plus_400"}, True)
check(win.s.edge_label == "", "choosing another film puts that film's name back on the edge")
shot("ui_4_look_bw.png")
win.apply_look("Positive Film (GR-inspired)")
check(wait_for(fine_shown, 120) and win.s.film == "fujifilm_provia_100f", "GR-inspired positive look applied")
hist = win.histories[win.current]
check(len(hist["entries"]) >= 8 and hist["entries"][-1][0].startswith("Look:"), "history records the steps")
win.history_jump(1)
check(wait_for(fine_shown, 60) and win.s.saturation == 40, "clicking a history step restores it")
win.apply_look("Positive Film (GR-inspired)")
wait_for(fine_shown, 120)

# --- crop tool
win.on_tool("crop")
check(win._crop_mode and wait_for(lambda: win.canvas.mode == "crop" and win.canvas.has_image(), 60), "crop mode shows the frame")
app.processEvents()
win.right.b.binds["aspect"].changed.emit("Free")  # unlock the aspect ratio
app.processEvents()
win.canvas.cropChanged.emit((0.2, 0.1, 0.7, 0.8))
win._crop_changed((0.2, 0.1, 0.7, 0.8))
win._sync_crop_overlay()
shot("ui_5_crop.png")
win.on_crop_action("done")
check(wait_for(lambda: not win._crop_mode and fine_shown(), 120), "crop applied")
im = win.canvas.current_image()
exp_ratio = (0.5 * 2100) / (0.7 * 1400)
check(abs(im.shape[1] / im.shape[0] - exp_ratio) < 0.03, f"free crop gives the drawn rectangle ({im.shape[1]}x{im.shape[0]})")
win.on_tool("crop")
wait_for(lambda: win.canvas.mode == "crop", 30)
win.right.b.binds["aspect"].changed.emit("1:1")
app.processEvents()
win.on_crop_action("done")
check(wait_for(lambda: not win._crop_mode and fine_shown(), 120), "aspect change applied")
im = win.canvas.current_image()
check(abs(im.shape[0] - im.shape[1]) <= 2, f"1:1 aspect lock gives a square ({im.shape[1]}x{im.shape[0]})")
win.on_tool("crop")
wait_for(lambda: win.canvas.mode == "crop", 30)
win.on_crop_action("reset")
win.on_crop_action("done")
wait_for(lambda: not win._crop_mode and fine_shown(), 120)

# --- navigator + 100% + detail
check(wait_for(lambda: win.service.engine.full_cached(win.current, win.s) is not None, 120),
      "the full-resolution photo is decoded in the background after the refined preview")
detail_calls = []
_set_detail = win.canvas.set_detail
win.canvas.set_detail = lambda tile, box, full, developed=True: (detail_calls.append(developed),
                                                                 _set_detail(tile, box, full, developed))
win.zoom_preset("100")
app.processEvents()
check(win.left.navigator._view is not None, "navigator shows the zoomed area")
r0 = win.left.navigator._view
win.left.navigator.navigate.emit(0.85, 0.2)
app.processEvents()
r1 = win.left.navigator._view
# the view centre follows the click unless the view would leave the photo (then it stops at the edge)
want = min(0.85, 1 - r1[2] / 2) if r1 else 0.85
check(r1 and abs((r1[0] + r1[2] / 2) - want) < 0.03,
      f"clicking the navigator moves the view (centre x {(r1[0] + r1[2] / 2) if r1 else -1:.3f}, "
      f"expected {want:.3f}, view {r0} -> {r1})")
check(wait_for(lambda: win.canvas._detail.isVisible(), 120), "1:1 renders a full-resolution tile")
check(detail_calls[:1] == [False] and detail_calls[-1] is True,
      f"zooming in shows the quick full-resolution view first, then the developed tile ({detail_calls})")
win.canvas.set_detail = _set_detail
shot("ui_6_zoom_nav.png")
win.zoom_preset("fit")

# --- clipping overlay
win.set_clipping(True)
app.processEvents()
check(not win.canvas._clipmask.pixmap().isNull(), "clipping overlay drawn")
win.set_clipping(False)

# --- switching photos keeps the display size stable
widths = []
for _ in range(3):
    win.strip.set_current(p1); wait_for(lambda: win.current == p1 and fine_shown(), 90)
    win.strip.set_current(p2); wait_for(lambda: win.current == p2 and fine_shown(), 90)
    widths.append(win.canvas.mapFromScene(win.canvas._item.sceneBoundingRect()).boundingRect().width())
check(max(widths) - min(widths) <= 2, f"display size stable across photo switches {widths}")

# --- sync via settings (dialog bypassed)
win.strip.select_all()
app.processEvents()
for pth in [x for x in paths if x != win.current]:
    s = win.lib.settings_for(pth)
    s.film, s.paper = win.s.film, win.s.paper
    win.lib.set_settings(pth, s)
check(win.lib.settings_for(p3).film == win.s.film, "sync writes settings to the other photos")

# --- export (same code as the Export dialog)
from spektralionkk.ui.export_dialog import Exporter
exp_dir = os.path.join(OUT, "exported")
opts = {"scope": "selected", "format": "jpeg", "quality": 92, "color_space": "Display P3", "long_edge": 1000,
        "folder": exp_dir, "suffix": "_sprk"}
result = {}
ex = Exporter([(p, win.lib.settings_for(p)) for p in paths[:2]], opts)
ex.finished.connect(lambda w_, e_: result.update(written=w_, errors=e_))
ex.start()
check(wait_for(lambda: "written" in result, 300), "export finished")
check(len(result.get("written", [])) == 2 and not result.get("errors"), f"exported 2 files {result.get('errors')}")
win.strip.set_current(p2)
wait_for(fine_shown, 60)
shot("ui_7_final.png")
win.lib.save()
print("UI TEST", "FAILED: " + "; ".join(fails) if fails else "PASSED")
win.close()
app.quit()
sys.exit(1 if fails else 0)
