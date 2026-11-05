"""UI test for v1.3: real-time slider preview, histogram drag, preset / LUT import, ratings and flags,
filmstrip batch actions, frame & date-stamp toggles.

Run:  .venv\\Scripts\\python.exe -I -X utf8 -W ignore app\\tests\\test_ui_live.py
Uses a throwaway LOCALAPPDATA so the user's library is untouched.
"""
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="sprk_uilive_")
os.environ.setdefault("NUMBA_CACHE_DIR", os.path.join(tempfile.gettempdir(), "sprk_test_numba_cache"))
sys.path.insert(0, os.path.join(HERE, ".."))

import numpy as np
from PySide6 import QtCore, QtWidgets

from spektralionkk import presets
from spektralionkk.ui import theme
from spektralionkk.ui.filmstrip import FLAG_ROLE, RATING_ROLE
from spektralionkk.ui.main_window import MainWindow

sys.path.insert(0, HERE)
from test_features import XMP  # noqa: E402

p1 = os.path.join(OUT, "test_input.jpg")
p2 = os.path.join(OUT, "test_landscape.jpg")
p3 = os.path.join(OUT, "test_landscape_copy.jpg")
for p in (p1, p2, p3):
    if not os.path.exists(p):
        raise SystemExit("run test_engine.py and test_ui.py first")
paths = [p1, p2, p3]

app = QtWidgets.QApplication(sys.argv)
theme.apply(app)
win = MainWindow(initial_paths=paths)
win.resize(1500, 950)
win.show()
fails = []
events = []  # (time, gen, kind)
win.service.rendered.connect(lambda gen, path, kind, img, secs, info: events.append((time.perf_counter(), gen, kind, secs)))
requests = []  # who asked for heavy renders (diagnostics)
_orig_request = win.service.request


def _logged_request(path, s, kind, **kw):
    import traceback as _tb

    requests.append((time.perf_counter(), kind, kw.get("new_gen", True),
                     " < ".join(f"{f.name}:{f.lineno}" for f in _tb.extract_stack()[-5:-1])))
    return _orig_request(path, s, kind, **kw)


win.service.request = _logged_request


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


def wait_for(pred, timeout=120):
    t = time.time()
    while time.time() - t < timeout:
        app.processEvents()
        if pred():
            return True
        time.sleep(0.005)
    return False


def fine_shown():
    return win._shown[1] == 1 and win._shown[0] == win.service.generation


def pump(seconds):
    t = time.time()
    while time.time() - t < seconds:
        app.processEvents()
        time.sleep(0.003)


def shot(name):
    app.processEvents()
    win.grab().save(os.path.join(OUT, name))


# no modal boxes in an unattended test
QtWidgets.QMessageBox.information = staticmethod(lambda *a, **k: QtWidgets.QMessageBox.Ok)
QtWidgets.QMessageBox.warning = staticmethod(lambda *a, **k: QtWidgets.QMessageBox.Ok)
QtWidgets.QMessageBox.question = staticmethod(lambda *a, **k: QtWidgets.QMessageBox.Yes)

check(wait_for(lambda: win._engine_ready, 300), "engine warm-up finished")
win.strip.set_current(p2)
check(wait_for(lambda: win.current == p2 and fine_shown(), 180), "photo rendered")
live_first = [e for e in events if e[2] == "live"]
check(bool(live_first), "opening a photo shows a real-time frame before the refined one")

# ---------------------------------------------------------------- slider drag (exposure)
gaps = []
last = [time.perf_counter()]


def tick():
    now = time.perf_counter()
    gaps.append(now - last[0])
    last[0] = now


timer = QtCore.QTimer()
timer.timeout.connect(tick)
timer.start(5)
hist_len = len(win.histories[win.current]["entries"])
events.clear()
requests.clear()
drag_gen0 = win.service.generation + 1  # renders of states from before the drag don't count
t0 = time.perf_counter()
values = [round(0.1 * i, 2) for i in range(1, 31)]  # 0.1 .. 3.0 EV, one step every 25 ms
for v in values:
    win.right.b.binds["exposure_ev"].set_value(v)
    win.on_edit({"exposure_ev": v}, False)
    pump(0.025)
pump(0.3)
drag_events = list(events)
lives = [e for e in drag_events if e[2] == "live"]
fines = [e for e in drag_events if e[2] in ("fine", "draft") and e[1] >= drag_gen0]
check(len(lives) >= 12, f"live frames while dragging: {len(lives)} for {len(values)} slider moves")
check(not fines, f"no heavy render while the slider is held ({len(fines)})")
if fines:
    for e in fines:
        print(f"     heavy render at +{(e[0] - t0) * 1000:.0f} ms gen {e[1]} kind {e[2]} took {e[3] * 1000:.0f} ms")
    for r in requests:
        print(f"     request at +{(r[0] - t0) * 1000:.0f} ms {r[1]} new_gen={r[2]} from {r[3]}")
lat = sorted(e[3] for e in lives)
med = lat[len(lat) // 2] if lat else 9
check(med < 0.08, f"live frame render time median {med * 1000:.0f} ms, max {max(lat) * 1000 if lat else 0:.0f} ms")
mx = max(gaps[3:]) if len(gaps) > 3 else 9
check(mx < 0.12, f"UI stays responsive while dragging (max event-loop gap {mx * 1000:.0f} ms)")
im_live = win.canvas.current_image().astype(float)
win.on_edit({"exposure_ev": values[-1]}, True)  # release
check(wait_for(fine_shown, 120), "refined render after release")
timer.stop()
h = win.histories[win.current]["entries"]
check(len(h) == hist_len + 1 and h[-1][0].startswith("Exposure"), f"one history step per drag ({h[-1][0]})")
im_fine = win.canvas.current_image().astype(float)
if im_live.shape == im_fine.shape:
    d = np.abs(im_live - im_fine).mean()
    check(d < 6, f"live frame ≈ refined render (mean diff {d:.2f}/255; grain etc. only in refined)")
else:
    print("     (live and refined frames have different sizes; skipped pixel comparison)")

# ---------------------------------------------------------------- histogram drag
start = win.s.exposure_ev
win.right.hist.dragStarted.emit("exposure_ev")
for f in (0.05, 0.1, 0.15, -0.125):
    win.right.hist.dragged.emit("exposure_ev", f)
    pump(0.03)
win.right.hist.dragFinished.emit("exposure_ev")
check(abs(win.s.exposure_ev - (start - 0.5)) < 1e-6, f"histogram drag changes exposure ({start:+.2f} → {win.s.exposure_ev:+.2f})")
check(abs(win.right.b.binds["exposure_ev"].value() - win.s.exposure_ev) < 1e-6, "slider follows the histogram drag")
check(win.histories[win.current]["entries"][-1][0].startswith("Exposure"), "histogram drag is one history step")
win.right.hist.dragStarted.emit("shadows")
win.right.hist.dragged.emit("shadows", 0.2)
win.right.hist.dragFinished.emit("shadows")
check(win.s.shadows == 40, f"dragging the Shadows zone sets Shadows ({win.s.shadows})")
check(wait_for(fine_shown, 120), "rendered after histogram drags")

# ---------------------------------------------------------------- spatial-only edit goes straight to the refined render
events.clear()
win.on_edit({"grain_size": 1.6}, True)
check(wait_for(fine_shown, 120), "grain size edit rendered")
check(not [e for e in events if e[2] == "live"], "grain-only edit skips the live tables (they can't show grain)")

# ---------------------------------------------------------------- preset import (.xmp) and LUT import
tmp = tempfile.mkdtemp()
xmp = os.path.join(tmp, "faded.xmp")
open(xmp, "w", encoding="utf-8").write(XMP)
QtWidgets.QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: ([xmp], ""))
win.import_presets("preset")
check("Test Faded Film" in win.lib.prefs.get("user_looks", {}), "XMP preset imported into My Looks")
check(win.s.look == "Test Faded Film" and win.s.film == "digital" and win.s.contrast == 18,
      "single imported preset is applied (digital profile, its tone settings)")
check(isinstance(win.s.curve_master, tuple) and isinstance(win.s.curve_master[0], tuple), "curves stored as tuples")
check(wait_for(fine_shown, 120), "imported preset rendered")
shot("uilive_1_preset.png")
n = 9
lines = [f"LUT_3D_SIZE {n}"] + [f"{min(1, r * 1.1):.5f} {g:.5f} {b * 0.85:.5f}"
                                 for b in np.linspace(0, 1, n) for g in np.linspace(0, 1, n) for r in np.linspace(0, 1, n)]
cube = os.path.join(tmp, "warm9.cube")
open(cube, "w").write("\n".join(lines))
QtWidgets.QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: ([cube], ""))
win.import_presets("lut")
check(win.s.lut_name == "warm9" and win.right.lut_combo.currentData() == "warm9", "LUT imported and selected")
check(wait_for(fine_shown, 120), "LUT rendered")
out_preset = os.path.join(tmp, "mine.sprkpreset")
QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (out_preset, ""))
win.export_preset("")
pr = presets.import_file(out_preset)
check(pr.values.get("lut_name") == "warm9" and pr.values.get("contrast") == 18, "current settings exported as a preset")

# ---------------------------------------------------------------- ratings, flags, filter
win._rate(4)
win._flag("pick")
it = win.strip._items[p2]
check(win.lib.rating(p2) == 4 and it.data(RATING_ROLE) == 4 and it.data(FLAG_ROLE) == "pick", "rating and flag set")
win.strip_action("flag", [p3], "reject")
win.strip_action("filter", [], "picks")
check(win.strip._items[p1].isHidden() and win.strip._items[p3].isHidden() and not it.isHidden(),
      "filter 'Picks only' hides the others")
win.strip_action("filter", [], "all")
check(not any(i.isHidden() for i in win.strip._items.values()), "filter 'All photos' shows everything")

# ---------------------------------------------------------------- batch: apply a look to other photos from the filmstrip
got = {}
win.service.stripThumbReady.connect(lambda p, img: got.__setitem__(p, img))
open_before = win.s.to_dict()
win.strip_action("look", [p1, p3], "Portra 400 Portrait")
check(win.lib.settings_for(p1).look == "Portra 400 Portrait" and win.lib.settings_for(p3).film == "kodak_portra_400",
      "look applied to non-open photos")
check(wait_for(lambda: p1 in got and p3 in got, 120), "their filmstrip thumbnails re-rendered in the background")
win.strip_action("rotr", [p1], None)
check(win.lib.settings_for(p1).rotation == 1, "rotate from the filmstrip")
win.strip_action("copy", [p1], None)
win.strip_action("paste", [p3], None)
check(win.lib.settings_for(p3).look == "Portra 400 Portrait" and win.lib.settings_for(p3).rotation == 0,
      "copy / paste settings from the filmstrip (crop & rotation not copied)")
check(win.s.to_dict() == open_before, "the open photo is untouched by batch actions on others")

# ---------------------------------------------------------------- frame and date stamp
win.right.edge_switch.click()  # the Film Edge header switch
check(win.s.border == "auto" and not win.right.edge_sec.is_collapsed(), "Film Edge switch turns the film strip on")
check(wait_for(fine_shown, 120), "35 mm frame rendered")
framed = win.canvas.current_image().shape
win._toggle_frame_pref(False)
check(wait_for(fine_shown, 120), "rendered with the frame hidden")
bare = win.canvas.current_image().shape
check(framed[0] > bare[0] and framed[1] > bare[1], f"View ▸ Show Film Frame toggles the frame {framed[:2]} → {bare[:2]}")
win._toggle_frame_pref(True)
wait_for(fine_shown, 120)
win.on_edit({"date_stamp": True, "date_text": "'24 11 04"}, True)
check(wait_for(fine_shown, 120), "date stamp rendered")
win.right.sections["Film Edge"].set_collapsed(False)
shot("uilive_2_frame_date.png")

# ---------------------------------------------------------------- export: inline status in the top bar, no window
exp_dir = os.path.join(OUT, "exported_live")
os.makedirs(exp_dir, exist_ok=True)
opts = {"format": "jpeg", "quality": 90, "color_space": "sRGB", "long_edge": 1080, "folder": exp_dir,
        "suffix": "_live", "frame": True}
before_windows = {id(w) for w in QtWidgets.QApplication.topLevelWidgets() if w.isVisible()}
win.start_export([(win.current, win.s.copy())], opts)
st = win.top.export_status
check(st.isVisible() and st.bar.isVisible() and "%" not in st.label.text(), f"export status shown: '{st.label.text()}'")
popups = [w for w in QtWidgets.QApplication.topLevelWidgets() if w.isVisible() and id(w) not in before_windows]
check(not popups, f"no export window ({[type(w).__name__ for w in popups]})")
check(wait_for(lambda: win._exporter is None, 300), "export finished")
check(not st.bar.isVisible() and st.show_btn.isVisible() and "Exported 1" in st.label.text(),
      f"export result shown inline: '{st.label.text()}'")
shot("uilive_export_status.png")

# ---------------------------------------------------------------- crop through the live path
events.clear()
win.on_tool("crop")
check(wait_for(lambda: any(e[2] == "crop_live" for e in events), 60), "crop tool shows a real-time frame")
check(wait_for(lambda: any(e[2] == "crop_fine" for e in events), 60), "…then the refined crop frame")
win.on_crop_action("cancel")
check(wait_for(lambda: not win._crop_mode and fine_shown(), 120), "crop cancelled")

# ---------------------------------------------------------------- filmstrip context menu builds (all actions)
menu_titles = []


def grab_menu():
    for w in QtWidgets.QApplication.topLevelWidgets():
        if isinstance(w, QtWidgets.QMenu) and w.isVisible():
            menu_titles.extend(a.text() for a in w.actions())
            w.close()


QtCore.QTimer.singleShot(300, grab_menu)
it = win.strip._items[p2]
win.strip._menu(win.strip.list.visualItemRect(it).center())
check(any("Rating" in t for t in menu_titles) and any("Apply Look" in t for t in menu_titles)
      and any("Paste" in t for t in menu_titles), f"filmstrip menu has the new actions ({len(menu_titles)} entries)")
shot("uilive_3_strip.png")

win.lib.save()
print("UI LIVE TEST", "FAILED: " + "; ".join(fails) if fails else "PASSED")
win.close()
app.quit()
sys.exit(1 if fails else 0)
