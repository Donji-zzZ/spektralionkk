"""Main editor window (Lightroom-style Develop layout)."""

from __future__ import annotations

import os

from PySide6 import QtCore, QtGui, QtWidgets

from .. import APP_NAME, APP_VERSION, engine as engine_mod, i18n, profiles
from ..i18n import tr, trf
from .. import live as live_mod
from .. import looks as looks_mod
from ..engine import SUPPORTED_EXTENSIONS, is_raw
from ..library import Library, expand_paths
from ..render_service import RenderService
from ..settings import (
    BORDER_FIELDS,
    FIELD_LABELS,
    GEOMETRY_FIELDS,
    NO_PRINT,
    SYNC_GROUPS,
    DevelopSettings,
    crop_ratio,
    effective_crop,
    geometry_key,
)
from . import theme
from .export_dialog import ExportDialog, Exporter
from .filmstrip import Filmstrip
from .canvas import Canvas
from .panels import DevelopPanel, GroupsDialog, LeftPanel

RELOAD_FIELDS = {"film", "paper", "auto_exposure", "grain", "halation", "couplers", "diffusion", "glare",
                 "border", "border_text", "date_stamp", "vignette", "wb_mode", "lut_name", "film_format",
                 "edge_holes", "shoot_data"}
TIER_RANK = {"live": 0, "draft": 0, "fine": 1}
LIVE_MAX_EDGE = 2560
# histogram drag: field -> (min, max, change for a drag across the whole histogram)
HIST_DRAG = {"exposure_ev": (-5.0, 5.0, 4.0), "blacks": (-100, 100, 200), "shadows": (-100, 100, 200),
             "highlights": (-100, 100, 200), "whites": (-100, 100, 200)}


def _fmt(field, value):
    if isinstance(value, bool):
        return "on" if value else "off"
    if field in ("film", "paper"):
        st = profiles.stock_by_key(value)
        return st.name if st else ("Direct scan" if value == NO_PRINT else str(value))
    if isinstance(value, float):
        return f"{value:+.2f}" if field in ("exposure_ev", "print_brightness") else f"{value:g}"
    return str(value).replace("_", " ")


class ExportStatus(QtWidgets.QWidget):
    """Export progress inside the top bar (no window): a slim bar, the photo being exported and a stop button.
    When the export ends it shows the result for a while, with a button to open the folder."""

    stopRequested = QtCore.Signal()
    showRequested = QtCore.Signal()
    detailsRequested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ExportStatus")
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 0, 0)
        lay.setSpacing(6)
        self.bar = QtWidgets.QProgressBar()
        self.bar.setObjectName("ExportBar")
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 1000)
        self.bar.setFixedSize(110, 5)
        self.label = QtWidgets.QLabel("")
        self.label.setObjectName("ExportLabel")
        self.stop = QtWidgets.QToolButton()
        self.stop.setText("✕")
        self.stop.setToolTip("Stop exporting")
        self.stop.clicked.connect(self.stopRequested)
        self.show_btn = QtWidgets.QToolButton()
        self.show_btn.setText("Show")
        self.show_btn.setToolTip("Show the exported file in Explorer")
        self.show_btn.clicked.connect(self.showRequested)
        self.details_btn = QtWidgets.QToolButton()
        self.details_btn.setText("Details")
        self.details_btn.clicked.connect(self.detailsRequested)
        for w in (self.bar, self.label, self.stop, self.show_btn, self.details_btn):
            lay.addWidget(w, 0, QtCore.Qt.AlignVCenter)
        self._hide_timer = QtCore.QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)
        self.hide()

    def start(self, n: int):
        self._hide_timer.stop()
        self.bar.setValue(0)
        self.bar.show()
        self.stop.show()
        self.show_btn.hide()
        self.details_btn.hide()
        self.label.setText(tr("Exporting…"))
        self.show()

    def update_progress(self, done: int, total: int, name: str):
        self.bar.setValue(int(1000 * done / max(1, total)))
        if name:
            n = total // 100
            i = min(n, done // 100 + 1)
            self.label.setText(trf("Exporting {name}", name=name) + (trf("  ·  {i} of {n}", i=i, n=n) if n > 1 else ""))
            self.label.setToolTip(name)

    def finish(self, written: int, failed: int, stopped: bool):
        self.bar.hide()
        self.stop.hide()
        if failed:
            self.label.setText(trf("⚠ Exported {written}, {failed} failed", written=written, failed=failed))
        elif stopped:
            self.label.setText(trf("Export stopped · {written} saved", written=written))
        else:
            self.label.setText(tr("✓ Exported 1 photo") if written == 1 else trf("✓ Exported {n} photos", n=written))
        self.show_btn.setVisible(written > 0)
        self.details_btn.setVisible(failed > 0)
        self._hide_timer.start(15000 if not failed else 60000)


class TopBar(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(4)

        def tb(text, tip, checkable=False):
            b = QtWidgets.QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setCheckable(checkable)
            lay.addWidget(b)
            return b

        self.left_toggle = tb("◧", "Show / hide the left panel (F7)", True)
        self.left_toggle.setChecked(True)
        self.open_btn = tb("Open…", "Open photos (Ctrl+O)")
        self.folder_btn = tb("Folder…", "Open a folder (Ctrl+Shift+O)")
        self.export_btn = tb("Export…", "Export (Ctrl+E)")
        self.export_status = ExportStatus()
        lay.addWidget(self.export_status)
        lay.addSpacing(14)
        self.info = QtWidgets.QLabel("")
        self.info.setObjectName("FileInfo")
        lay.addWidget(self.info, 1)
        self.right_toggle = tb("◨", "Show / hide the Develop panel (F8)", True)
        self.right_toggle.setChecked(True)


class ToolBar(QtWidgets.QWidget):
    """Under the image: before/after, clipping, zoom read-out (Lightroom's toolbar)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ToolBar")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(8, 3, 8, 3)
        lay.setSpacing(4)

        def tb(text, tip):
            b = QtWidgets.QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setCheckable(True)
            lay.addWidget(b)
            return b

        self.before = tb("◐ Before", "Show the original photo (\\)")
        self.split = tb("◫ Before | After", "Split view with a draggable divider (Y)")
        self.clipping = tb("▲ Clipping", "Show clipped highlights (red) and shadows (blue) (J)")
        lay.addStretch(1)
        self.zoom = QtWidgets.QLabel("")
        self.zoom.setObjectName("Dim")
        lay.addWidget(self.zoom)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, initial_paths=None):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(theme.app_icon())
        self.resize(1660, 1000)
        sb = self.statusBar()
        _show = sb.showMessage
        sb.showMessage = lambda text, timeout=0: _show(tr(text), timeout)  # status messages in the UI language
        self.lib = Library()
        engine_mod.PREFS["always_grain"] = bool(self.lib.prefs.get("always_grain", False))
        engine_mod.PREFS["show_frame"] = bool(self.lib.prefs.get("show_frame", True))
        self.service = RenderService(self)
        self.current: str | None = None
        self.s = DevelopSettings()
        self.clipboard: dict | None = None
        self.histories: dict[str, dict] = {}
        self._shown = (-1, -1)
        self._engine_ready = False
        self._exporter = None
        self._info: dict = {}
        self._fine_size = 0
        self._crop_mode = False
        self._crop_saved = None
        self._before = False
        self._split = False
        self._thumb_key = None
        self._orig_key = None
        self._dragging = False  # a slider / histogram drag is in progress
        self._uncommitted = False  # values changed by a drag that has not been released yet
        self._hist_drag = None
        self._live_status = False
        self._noted = None

        # ---- layout
        central = QtWidgets.QWidget()
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.top = TopBar()
        root.addWidget(self.top)
        split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        split.setHandleWidth(1)
        self.left = LeftPanel()
        self.left.setMinimumWidth(250)
        self.right = DevelopPanel()
        self.right.setMinimumWidth(320)
        mid = QtWidgets.QWidget()
        ml = QtWidgets.QVBoxLayout(mid)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)
        self.canvas = Canvas()
        ml.addWidget(self.canvas, 1)
        self.toolbar = ToolBar()
        ml.addWidget(self.toolbar)
        self.strip = Filmstrip()
        ml.addWidget(self.strip)
        split.addWidget(self.left)
        split.addWidget(mid)
        split.addWidget(self.right)
        split.setStretchFactor(1, 1)
        split.setSizes([270, 1040, 350])
        root.addWidget(split, 1)
        self.setCentralWidget(central)
        self._build_menus()

        # ---- wiring
        r, lp, c = self.right, self.left, self.canvas
        r.edited.connect(self.on_edit)
        r.toolRequested.connect(self.on_tool)
        r.cropAction.connect(self.on_crop_action)
        r.syncRequested.connect(self.sync_dialog)
        r.resetRequested.connect(self.reset_photo)
        r.importRequested.connect(self.import_presets)
        r.hist.clippingToggled.connect(self.set_clipping)
        r.hist.dragStarted.connect(self._hist_start)
        r.hist.dragged.connect(self._hist_move)
        r.hist.dragFinished.connect(self._hist_end)
        lp.zoomPreset.connect(self.zoom_preset)
        lp.navigator.navigate.connect(c.center_on_norm)
        lp.copyRequested.connect(self.copy_dialog)
        lp.pasteRequested.connect(self.paste_settings)
        lp.looks.applyLook.connect(self.apply_look)
        lp.looks.saveLook.connect(self.save_look)
        lp.looks.deleteLook.connect(self.delete_look)
        lp.looks.importLooks.connect(lambda: self.import_presets("preset"))
        lp.looks.exportLook.connect(self.export_preset)
        lp.history.jump.connect(self.history_jump)
        lp.looks_sec._btn.clicked.connect(lambda: QtCore.QTimer.singleShot(0, self._request_look_thumbs))
        c.viewChanged.connect(lp.navigator.set_view)
        c.viewChanged.connect(lambda _: lp.set_zoom_state(*c.zoom_percent()))
        c.zoomChanged.connect(self.toolbar.zoom.setText)
        c.filesDropped.connect(self.add_paths)
        c.detailWanted.connect(self._request_detail)
        c.wbPicked.connect(self._wb_picked)
        c.cropChanged.connect(self._crop_changed)
        c.cropCommit.connect(lambda: self.on_crop_action("done"))
        self.toolbar.before.clicked.connect(lambda on: self.set_before(on))
        self.toolbar.split.clicked.connect(lambda on: self.set_split(on))
        self.toolbar.clipping.clicked.connect(lambda on: self.set_clipping(on))
        self.strip.currentChanged.connect(self.open_photo)
        self.strip.filesDropped.connect(self.add_paths)
        self.strip.removeRequested.connect(self.remove_paths)
        self.strip.action.connect(self.strip_action)
        self.strip.look_groups = self._look_groups
        self.strip.can_paste = lambda: bool(self.clipboard)
        self.strip.filter = self.lib.prefs.get("strip_filter", "all")
        t = self.top
        t.open_btn.clicked.connect(self.open_files)
        t.folder_btn.clicked.connect(self.open_folder)
        t.export_btn.clicked.connect(self.export)
        t.export_status.stopRequested.connect(self._stop_export)
        t.export_status.showRequested.connect(self._show_export)
        t.export_status.detailsRequested.connect(self._export_details)
        t.left_toggle.toggled.connect(lp.setVisible)
        t.right_toggle.toggled.connect(r.setVisible)
        sv = self.service
        sv.rendered.connect(self.on_rendered)
        sv.originalReady.connect(self.on_original)
        sv.wbSampled.connect(self.on_wb_sampled)
        sv.thumbReady.connect(lambda path, name, img: path == self.current and lp.looks.set_thumb(name, img))
        sv.stripThumbReady.connect(self.strip.set_processed_thumb)
        sv.failed.connect(self.on_failed)
        sv.busy.connect(lambda text: c.set_status(tr(text)))
        sv.engineReady.connect(self._on_engine_ready)
        self._fine_timer = QtCore.QTimer(self, singleShot=True, interval=280)
        self._fine_timer.timeout.connect(self._request_fine)
        self._spatial_timer = QtCore.QTimer(self, singleShot=True, interval=200)
        self._spatial_timer.timeout.connect(self._request_spatial)
        self._crop_fine_timer = QtCore.QTimer(self, singleShot=True, interval=300)
        self._crop_fine_timer.timeout.connect(lambda: self._crop_mode and self.current and self.service.request(
            self.current, self.s, "crop_fine", new_gen=False, long_edge=self.canvas.target_long_edge()))
        self._live_busy = QtCore.QTimer(self, singleShot=True, interval=250)  # only say "Developing…" if slow
        self._live_busy.timeout.connect(self._show_live_busy)
        self._save_timer = QtCore.QTimer(self, singleShot=True, interval=800)
        self._save_timer.timeout.connect(self.lib.save)
        self._resize_timer = QtCore.QTimer(self, singleShot=True, interval=500)
        self._resize_timer.timeout.connect(self._after_resize)

        # ---- restore
        lp.looks.populate(self.lib.prefs.get("user_looks", {}))
        r.load(self.s, raw=False)
        c.set_image(None)
        if self.lib.photos:
            self.strip.set_paths(self.lib.photos)
            self._refresh_meta(self.lib.photos)
        if initial_paths:
            QtCore.QTimer.singleShot(0, lambda: self.add_paths(initial_paths))
        elif self.lib.photos:
            last = self.lib.prefs.get("last_photo")
            QtCore.QTimer.singleShot(0, lambda: self.strip.set_current(
                last if last in self.lib.photos else self.lib.photos[0]))
        geo = self.lib.prefs.get("window")
        if geo:
            self.restoreGeometry(QtCore.QByteArray.fromHex(geo.encode()))
        i18n.translate_tree(self)  # static texts, tooltips and menus in the interface language

    # ------------------------------------------------------------------ menus
    def _build_menus(self):
        mb = self.menuBar()

        def act(menu, text, slot, shortcut=None, checkable=False, checked=False):
            a = QtGui.QAction(tr(text), self)
            if shortcut:
                a.setShortcut(QtGui.QKeySequence(shortcut))
                a.setShortcutContext(QtCore.Qt.WindowShortcut)
            a.setCheckable(checkable)
            a.setChecked(checked)
            a.triggered.connect(slot)
            menu.addAction(a)
            self.addAction(a)
            return a

        f = mb.addMenu(tr("&File"))
        act(f, "Open Photos…", self.open_files, "Ctrl+O")
        act(f, "Open Folder…", self.open_folder, "Ctrl+Shift+O")
        f.addSeparator()
        act(f, "Export…", self.export, "Ctrl+E")
        f.addSeparator()
        act(f, "Import Presets && LUTs…", lambda: self.import_presets("preset"), "Ctrl+Shift+I")
        act(f, "Export Current Settings as Preset…", lambda: self.export_preset(""))
        act(f, "Open Presets && LUTs Folder", self._open_preset_folder)
        f.addSeparator()
        act(f, "Remove Selected from Library", lambda: self.remove_paths(self.strip.selected_paths()))
        f.addSeparator()
        act(f, "Exit", self.close, "Alt+F4")

        e = mb.addMenu(tr("&Edit"))
        act(e, "Undo", self.undo, "Ctrl+Z")
        act(e, "Redo", self.redo, "Ctrl+Y")
        e.addSeparator()
        act(e, "Copy Settings…", self.copy_dialog, "Ctrl+Shift+C")
        act(e, "Paste Settings", self.paste_settings, "Ctrl+Shift+V")
        act(e, "Sync Settings…", self.sync_dialog, "Ctrl+Shift+S")
        act(e, "Select All Photos", self.strip.select_all, "Ctrl+A")
        e.addSeparator()
        act(e, "Reset Photo", self.reset_photo, "Ctrl+R")
        act(e, "Save Current as Default for New Photos", self.save_default)
        act(e, "Restore Factory Defaults for New Photos", self.factory_default)

        p = mb.addMenu(tr("&Photo"))
        act(p, "Crop && Straighten", lambda: self.on_tool("crop"), "R")
        act(p, "White Balance Picker", lambda: self.on_tool("wb"), "W")
        act(p, "Save Look…", self.save_look)
        p.addSeparator()
        act(p, "Rotate Left", lambda: self.on_crop_action("rotl"), "Ctrl+[")
        act(p, "Rotate Right", lambda: self.on_crop_action("rotr"), "Ctrl+]")
        p.addSeparator()
        rm = p.addMenu(tr("Set Rating"))
        for k in range(6):
            act(rm, "No stars" if k == 0 else "★" * k, lambda _=False, k=k: self._rate(k), str(k))
        fm = p.addMenu(tr("Flag"))
        act(fm, "Pick", lambda: self._flag("pick"), "P")
        act(fm, "Reject", lambda: self._flag("reject"), "X")
        act(fm, "Unflag", lambda: self._flag(""), "U")

        v = mb.addMenu(tr("&View"))
        act(v, "Before (Original)", lambda: self.set_before(not self._before), "\\")
        act(v, "Before | After Split", lambda: self.set_split(not self._split), "Y")
        act(v, "Show Clipping", lambda: self.set_clipping(not self.canvas.clipping), "J")
        v.addSeparator()
        act(v, "Fit", lambda: self.zoom_preset("fit"), "F")
        act(v, "Fill", lambda: self.zoom_preset("fill"))
        act(v, "100%", lambda: self.zoom_preset("100"), "Z")
        act(v, "200%", lambda: self.zoom_preset("200"))
        act(v, "Zoom In", lambda: self.canvas.zoom_by(1.25), "Ctrl+=")
        act(v, "Zoom Out", lambda: self.canvas.zoom_by(0.8), "Ctrl+-")
        v.addSeparator()
        act(v, "Previous Photo", lambda: self.strip.step(-1), "Left")
        act(v, "Next Photo", lambda: self.strip.step(1), "Right")
        act(v, "Left Panel", lambda: self.top.left_toggle.toggle(), "F7")
        act(v, "Develop Panel", lambda: self.top.right_toggle.toggle(), "F8")
        v.addSeparator()
        self.frame_action = act(v, "Show Film Frame && Date Stamp in Preview", self._toggle_frame_pref, "Shift+F",
                                checkable=True, checked=engine_mod.PREFS["show_frame"])
        act(v, "Render Grain in Fitted Preview (slower)", self._toggle_grain_pref,
            checkable=True, checked=engine_mod.PREFS["always_grain"])
        v.addSeparator()
        lm = v.addMenu("语言 / Language" if i18n.LANG == "zh_CN" else "Language / 语言")
        group = QtGui.QActionGroup(self)
        for code, name in i18n.LANGS.items():
            a = act(lm, name, lambda _=False, c=code: self._set_language(c), checkable=True, checked=i18n.LANG == code)
            group.addAction(a)
        self._esc = QtGui.QShortcut(QtGui.QKeySequence("Esc"), self, activated=self._escape)
        self._enter = QtGui.QShortcut(QtGui.QKeySequence("Return"), self, activated=self._enter_key)
        self._enter2 = QtGui.QShortcut(QtGui.QKeySequence("Enter"), self, activated=self._enter_key)

        h = mb.addMenu(tr("&Help"))
        act(h, "Keyboard Shortcuts", self.show_shortcuts, "F1")
        act(h, trf("About {APP_NAME}", APP_NAME=APP_NAME), self.about)

    def _set_language(self, code: str):
        if code == i18n.LANG:
            return
        try:
            i18n.save_language(code)
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, APP_NAME, str(exc))
            return
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle(APP_NAME)
        box.setText(tr("The language changes the next time sprktralionkk starts.") +
                    ("\n\nThe language changes the next time sprktralionkk starts." if i18n.LANG != "en" else
                     "\n\n界面语言将在下次启动 sprktralionkk 时切换。"))
        restart = box.addButton(tr("Restart now") + (" / Restart now" if i18n.LANG != "en" else " / 立即重启"),
                                QtWidgets.QMessageBox.AcceptRole)
        box.addButton(tr("Later") + (" / Later" if i18n.LANG != "en" else " / 稍后"), QtWidgets.QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is restart:
            import sys

            args = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv
            self.close()
            if not self.isVisible():  # closed (library saved): start again
                QtCore.QProcess.startDetached(sys.executable, args)
                QtWidgets.QApplication.instance().quit()

    def _toggle_grain_pref(self, on):
        engine_mod.PREFS["always_grain"] = bool(on)
        self.lib.prefs["always_grain"] = bool(on)
        self.lib.save()
        self._schedule()

    def _toggle_frame_pref(self, on):
        """Preview only: exports have their own 'Include the film frame' option."""
        engine_mod.PREFS["show_frame"] = bool(on)
        self.lib.prefs["show_frame"] = bool(on)
        self.lib.save()
        self.canvas.clear_detail()
        self._orig_key = None
        self._schedule(["border"])
        if not on:
            self.statusBar().showMessage("Frame hidden in the preview — exports still follow the Export dialog", 4000)

    def _escape(self):
        if self._crop_mode:
            self.on_crop_action("cancel")
        elif self.canvas.mode == "wb":
            self._set_wb_tool(False)

    def _enter_key(self):
        if self._crop_mode:
            self.on_crop_action("done")

    # ------------------------------------------------------------------ library
    def open_files(self):
        exts = " ".join("*" + e for e in sorted(SUPPORTED_EXTENSIONS))
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, tr("Open photos"), self.lib.prefs.get("last_dir", os.path.expanduser("~")),
            trf("Photos ({exts});;All files (*)", exts=exts))
        if paths:
            self.lib.prefs["last_dir"] = os.path.dirname(paths[0])
            self.add_paths(paths)

    def open_folder(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(
            self, tr("Open a folder of photos"), self.lib.prefs.get("last_dir", os.path.expanduser("~")))
        if d:
            self.lib.prefs["last_dir"] = d
            self.add_paths([d])

    def add_paths(self, paths):
        new = self.lib.add(paths)
        given = expand_paths(paths)
        if not given:
            self.statusBar().showMessage("No supported photos found there.", 4000)
            return
        self.strip.add_paths(new)
        self._refresh_meta(new)
        self.lib.save()
        self.strip.set_current(given[0])
        self.statusBar().showMessage(trf("Added {n} photo(s)", n=len(new)) if new else "Already in the library", 3000)

    def remove_paths(self, paths):
        if not paths:
            return
        self.lib.remove(paths)
        self.strip.remove_paths(paths)
        self.lib.save()
        if self.current in paths:
            self.current = None
            if self.lib.photos:
                self.strip.set_current(self.lib.photos[0])
            else:
                self.canvas.set_image(None)
                self.top.info.setText("")
                self.left.navigator.set_image(None)

    # ------------------------------------------------------------------ photo
    def open_photo(self, path):
        if not path or path == self.current:
            return
        if self._crop_mode:
            self.on_crop_action("cancel")
        self.current = path
        self.lib.prefs["last_photo"] = path
        self.s = self.lib.settings_for(path)
        self._info = {}
        self._uncommitted = False
        self._hist_drag = None
        self._dragging = False
        self.right.load(self.s, raw=is_raw(path))
        self._update_info()
        self.canvas.reset_view()
        self.canvas.set_original(None)
        self.canvas._placeholder.hide()
        self._shown = (-1, -1)
        self._thumb_key = None
        self._orig_key = None
        self.left.looks.clear_thumbs()
        self.left.looks.set_current(self.s.look)
        self.service.cancel_thumbs()
        self.service.engine.drop_full()
        h = self.histories.setdefault(path, {"entries": [(tr("Opened"), self.s.to_dict())], "index": 0})
        self._show_history(h)
        self._schedule()
        paths = self.strip.paths()
        if path in paths:
            i = paths.index(path)
            for j in (i + 1, i - 1, i + 2):
                if 0 <= j < len(paths):
                    self.service.prefetch(paths[j], self.lib.settings_for(paths[j]))

    # ------------------------------------------------------------------ edits
    def on_edit(self, updates: dict, final: bool, label: str | None = None):
        for k, v in list(updates.items()):
            cur = getattr(self.s, k, None)
            if isinstance(cur, bool):
                updates[k] = bool(v)
            elif isinstance(cur, int) and not isinstance(cur, bool):
                updates[k] = int(round(v))
            elif isinstance(cur, tuple):  # tone curves (lists when they come from JSON)
                updates[k] = tuple((float(p[0]), float(p[1])) for p in v)
        if not self.current:
            for k, v in updates.items():
                setattr(self.s, k, v)
            return
        before = self.s.to_dict()
        for k, v in updates.items():
            setattr(self.s, k, v)
        if "look" not in updates and set(updates) & set(looks_mod.LOOK_FIELDS):
            self.s.look = ""
        self._stock_rules(updates)
        after = self.s.to_dict()
        changed = [k for k in after if before.get(k) != after.get(k)]
        # releasing a slider re-sends the value the drag already applied: still one history step
        release = final and self._uncommitted
        if not changed and not release:
            return
        if changed:
            first = not self.lib.is_edited(self.current)
            self.lib.set_settings(self.current, self.s)
            self._save_timer.start()
            if first:
                self._refresh_meta([self.current])
        self._uncommitted = not final
        if "border" in changed and self.s.border != "none" and not engine_mod.PREFS["show_frame"]:
            self.frame_action.setChecked(True)  # turning Film Edge on: show it, even if the preview hid frames
            self._toggle_frame_pref(True)
        if final and not self._crop_mode:  # crop edits are committed as one step by Done
            self._push_history(label or self._label(updates), after)
        if final and (RELOAD_FIELDS & set(changed) or len(changed) > 2):
            self.right.load(self.s, raw=is_raw(self.current), wb_shown=self._info.get("wb"))
            self.left.looks.set_current(self.s.look)
        if self._crop_mode:
            if set(changed) & {"rotation", "flip_h", "flip_v", "straighten"}:
                self._schedule_crop()
            if "aspect" in changed:
                self._apply_aspect()
            return
        self._update_info()
        self.canvas.clear_detail()
        self._schedule(changed or list(updates), final=final)

    def _label(self, updates):
        keys = [k for k in updates if k not in ("look",)]
        if not keys:
            return tr("Edit")
        if set(keys) >= {"wb_mode", "temperature"}:
            return trf("White balance: {T} K, tint {tint}", T=f"{self.s.temperature:.0f}", tint=f"{self.s.tint:+.0f}")
        if len(keys) > 3:
            return tr("Multiple settings")
        k = keys[0]
        v = _fmt(k, updates[k])
        return f"{tr(FIELD_LABELS.get(k, k))}: {tr(v) if v in ('on', 'off') else v}"

    def _stock_rules(self, updates):
        """Slides are scanned directly; negatives need a paper; B&W films print on B&W paper."""
        film = profiles.stock_by_key(self.s.film)
        if not film:
            return
        if "film" in updates and "paper" not in updates:
            paper = profiles.stock_by_key(self.s.paper)
            if film.kind == "positive":
                if self.s.paper != NO_PRINT:
                    self.s.paper = NO_PRINT
                    self.statusBar().showMessage("Slide film: scanned directly (no print)", 4000)
            elif film.bw and not (paper and paper.bw):
                self.s.paper = profiles.BW_PAPER
                self.statusBar().showMessage("B&W film: printing on Ilford Multigrade IV RC", 4000)
            elif not film.bw and (self.s.paper == NO_PRINT or (paper and paper.bw)):
                tp = film.target_print if profiles.stock_by_key(film.target_print or "") else None
                self.s.paper = tp or ("kodak_2383" if film.use == "cine" else "kodak_portra_endura")
                self.statusBar().showMessage(trf("Printing on {paper}", paper=profiles.stock_by_key(self.s.paper).name),
                                             4000)
        if "paper" in updates and self.s.paper == NO_PRINT and film.kind != "positive":
            self.s.paper = engine_mod.effective_paper(self.s)
            self.statusBar().showMessage("Direct scan is for slide films — a negative needs a paper", 4000)
        if "paper" in updates and self.s.paper != NO_PRINT and film.kind == "positive":
            self.s.paper = NO_PRINT
            self.statusBar().showMessage("Slides can't be printed on negative paper — showing the direct scan", 4000)

    def _update_info(self):
        if not self.current:
            self.top.info.setText("")
            return
        film = profiles.stock_by_key(self.s.film)
        paper = profiles.stock_by_key(self.s.paper)
        parts = [os.path.basename(self.current)]
        cs = self._info.get("crop_size")
        if cs:
            parts.append(f"{cs[0]}×{cs[1]}")
        if engine_mod.is_digital(self.s):
            parts.append(tr("Digital (no film)"))
        else:
            parts.append((film.name if film else self.s.film) + "  →  " + (paper.name if paper else tr("direct scan")))
        if self.s.look:
            parts.append(tr(self.s.look))
        if self._info.get("note"):
            parts.append(tr("embedded JPEG (RAW codec not supported)"))
        self.top.info.setText("   ·   ".join(parts))

    # ------------------------------------------------------------------ history / undo
    def _push_history(self, label, state):
        h = self.histories.setdefault(self.current, {"entries": [(tr("Opened"), state)], "index": 0})
        del h["entries"][h["index"] + 1:]
        h["entries"].append((label, state))
        h["index"] = len(h["entries"]) - 1
        if len(h["entries"]) > 200:
            h["entries"].pop(1)
            h["index"] -= 1
        self._show_history(h)

    def _show_history(self, h):
        self.left.history.set_entries([e[0] for e in h["entries"]], h["index"])

    def history_jump(self, i):
        h = self.histories.get(self.current)
        if not h or not (0 <= i < len(h["entries"])):
            return
        h["index"] = i
        self._restore(h["entries"][i][1])
        self._show_history(h)

    def undo(self):
        h = self.histories.get(self.current or "")
        if h and h["index"] > 0:
            self.history_jump(h["index"] - 1)

    def redo(self):
        h = self.histories.get(self.current or "")
        if h and h["index"] < len(h["entries"]) - 1:
            self.history_jump(h["index"] + 1)

    def _restore(self, d):
        before = self.s.to_dict()
        self.s = DevelopSettings.from_dict(d)
        self.lib.set_settings(self.current, self.s)
        self._save_timer.start()
        self.right.load(self.s, raw=is_raw(self.current), wb_shown=self._info.get("wb"))
        self.left.looks.set_current(self.s.look)
        after = self.s.to_dict()
        self._update_info()
        self.canvas.clear_detail()
        self._schedule([k for k in after if before.get(k) != after.get(k)])

    # ------------------------------------------------------------------ rendering
    def _live_edge(self) -> int:
        return max(480, min(self.canvas.target_long_edge(), LIVE_MAX_EDGE))

    def _schedule(self, changed=None, final=True):
        """Colour, tone, exposure, white balance, film, paper, finishing and frame edits show at once from
        the real-time tables; the refined render (grain, halation, sharpening…) follows when you let go."""
        if not self.current or not self._engine_ready:
            return
        if self._crop_mode:
            self._schedule_crop()
            return
        self._dragging = not final
        self._fine_timer.stop()
        if changed is not None and set(changed) <= live_mod.SPATIAL_ONLY:
            # only the refined render can show these: render it as soon as the slider pauses
            self._spatial_timer.start(30 if final else 220)
        else:
            self._spatial_timer.stop()
            self.service.request_live(self.current, self.s, self._live_edge(), dragging=not final)
            if not self._live_busy.isActive():
                self._live_busy.start()
        if self._before or self._split:
            self._request_original()

    def _show_live_busy(self):
        self._live_status = True
        self.canvas.set_status(tr("Developing…"))

    def _request_fine(self):
        if self.current and not self._crop_mode:
            self._fine_size = self.canvas.target_long_edge()
            self.service.request(self.current, self.s, "fine", new_gen=False, long_edge=self._fine_size)

    def _request_spatial(self):
        if self.current and not self._crop_mode:
            self._fine_size = self.canvas.target_long_edge()
            self.service.request(self.current, self.s, "fine", long_edge=self._fine_size)

    def _schedule_crop(self):
        self._crop_fine_timer.stop()
        self.service.request_live(self.current, self.s, self._live_edge(), uncropped=True)

    def _request_detail(self, rect):
        if (self.current and not self._crop_mode and self._shown[1] >= TIER_RANK["fine"]
                and self._shown[0] == self.service.generation):
            self.service.request_detail(self.current, self.s, rect)

    def _request_original(self):
        if not self.current:
            return
        size = max(self._fine_size, self.canvas.target_long_edge())
        key = (self.current, geometry_key(self.s), self.s.subset(BORDER_FIELDS), self.s.lens_correction,
               size)
        if key != self._orig_key:
            self._orig_key = key
            self.service.request_original(self.current, self.s, size, key)

    def on_original(self, path, img, key):
        if path == self.current and key == self._orig_key:
            self.canvas.set_original(img)
            self.canvas.set_before(self._before)
            self.canvas.set_split(self._split)

    def on_rendered(self, gen, path, kind, img, secs, info):
        if path != self.current:
            return
        if kind == "detail":
            if gen == self.service.generation and self.canvas.wants_detail():
                self.canvas.set_detail(img, info["box"], info["full"])
                self.statusBar().showMessage(trf("Full-resolution detail rendered in {secs}s", secs=f"{secs:.1f}"), 2500)
            return
        if kind.startswith("crop_"):
            if self._crop_mode:
                self.canvas.set_image(img, info)
                fs = info.get("frame_size")
                if fs:
                    self._frame = fs
                    self._sync_crop_overlay()
                if kind == "crop_live" and gen == self.service.generation:
                    self._crop_fine_timer.start()
            return
        if self._crop_mode:
            return
        rank = (gen, TIER_RANK[kind])
        if rank < self._shown:
            return
        self._shown = rank
        self._info = info or {}
        self.canvas.set_image(img, info)
        self.right.hist.set_image(img, info.get("inset"))
        if self.s.wb_mode != "custom" and info.get("wb"):
            self.right.set_wb_display(*info["wb"])
        self._update_info()
        if kind in ("live", "draft"):
            self._live_busy.stop()
            if self._live_status:
                self._live_status = False
                self.canvas.set_status("")
            if gen == self.service.generation and not self._dragging:
                self._fine_timer.start(150 if kind == "live" else 10)  # refine once the user lets go
        if info.get("note") and self._noted != path:
            self._noted = path
            self.statusBar().showMessage(info["note"], 20000)
        if kind == "fine":
            self.right.set_info(info)
            self.strip.set_processed_thumb(path, img)
            self.left.navigator.set_image(img)
            note = "" if info.get("grain_shown", True) else "  ·  grain shown at 100% and in exports"
            if not info.get("note"):
                self.statusBar().showMessage(trf("Rendered in {secs}s", secs=f"{secs:.2f}") + tr(note), 3000)
            if self.canvas.wants_detail():
                r = self.canvas.visible_rect_norm()
                if r:
                    self.service.request_detail(path, self.s, r)
            QtCore.QTimer.singleShot(50, self._request_look_thumbs)

    def on_failed(self, gen, path, msg):
        if path == self.current:
            self.canvas.set_status("")
            QtWidgets.QMessageBox.warning(self, tr("Could not render"), f"{os.path.basename(path)}\n\n{tr(msg)}")

    def _on_engine_ready(self):
        self._engine_ready = True
        self._schedule()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "_resize_timer"):
            self._resize_timer.start()

    def _after_resize(self):
        if self.current and not self._crop_mode and self.canvas.target_long_edge() > self._fine_size * 1.15:
            self._request_fine()

    # ------------------------------------------------------------------ looks
    def _look_values(self, name):
        if name in looks_mod.LOOKS:
            return looks_mod.LOOKS[name][2]
        return self.lib.prefs.get("user_looks", {}).get(name)

    def apply_look(self, name):
        values = self._look_values(name)
        if values is None or not self.current:
            return
        upd = looks_mod.look_values(values)
        if name not in looks_mod.LOOKS:  # imported presets may also carry exposure and white balance
            for k in ("exposure_ev", "wb_mode", "temperature", "tint"):
                if k in values:
                    upd[k] = values[k]
        upd["look"] = name
        self.on_edit(upd, True, label=trf("Look: {name}", name=tr(name)))
        self.left.looks.set_current(name)

    def _request_look_thumbs(self):
        if not self.current or self.left.looks_sec.is_collapsed() or not self.left.isVisible():
            return
        base = self.s.copy()
        key = (self.current, tuple(v for k, v in self.s.to_dict().items() if k not in looks_mod.LOOK_FIELDS))
        if key == self._thumb_key:
            return
        self._thumb_key = key
        jobs = []
        for name in self.left.looks.names():
            values = self._look_values(name)
            if values is None:
                continue
            s = base.copy()
            for k, v in looks_mod.look_values(values).items():
                setattr(s, k, v)
            s.border = "none"
            jobs.append((name, s))
        self.service.request_thumbs(self.current, jobs)

    def save_look(self):
        if not self.current:
            return
        name, ok = QtWidgets.QInputDialog.getText(self, tr("Save Look"), tr("Name for this look:"))
        name = (name or "").strip()
        if not ok or not name:
            return
        if name in looks_mod.LOOKS:
            name += " (mine)"
        user = dict(self.lib.prefs.get("user_looks", {}))
        user[name] = looks_mod.capture(self.s)
        self.lib.prefs["user_looks"] = user
        self.lib.save()
        self.left.looks.populate(user)
        self.s.look = name
        self.lib.set_settings(self.current, self.s)
        self.left.looks.set_current(name)
        self._thumb_key = None
        self._request_look_thumbs()
        self.statusBar().showMessage(trf("Saved look “{name}”", name=name), 3000)

    def delete_look(self, name):
        user = dict(self.lib.prefs.get("user_looks", {}))
        if name in user and QtWidgets.QMessageBox.question(self, tr("Delete Look"), trf("Delete “{name}”?", name=name)) == \
                QtWidgets.QMessageBox.Yes:
            user.pop(name)
            self.lib.prefs["user_looks"] = user
            self.lib.save()
            self.left.looks.populate(user)
            self._thumb_key = None
            self._request_look_thumbs()

    # ------------------------------------------------------------------ tools
    def on_tool(self, key):
        if key == "crop":
            if self._crop_mode:
                self.on_crop_action("done")
            else:
                self.enter_crop()
        elif key == "wb":
            self._set_wb_tool(self.canvas.mode != "wb")
        elif key == "split":
            self.set_split(not self._split)
        elif key == "original":
            self.set_before(not self._before)

    def _set_wb_tool(self, on):
        if self._crop_mode:
            return
        self.canvas.set_mode("wb" if on else "view")
        self.right.set_tool("wb", on)
        self.right.picker.setChecked(on) if self.right.picker.isCheckable() else None
        if on:
            self.statusBar().showMessage("Click on something that should be neutral grey (Esc to cancel)", 6000)

    def _wb_picked(self, u, v):
        if self.current:
            self.service.request_wb_sample(self.current, self.s, u, v)
        self._set_wb_tool(False)

    def on_wb_sampled(self, path, T, tint):
        if path == self.current:
            self.on_edit({"wb_mode": "custom", "temperature": round(T), "tint": round(tint)}, True,
                         label=trf("White balance picker: {T} K, tint {tint}", T=f"{T:.0f}", tint=f"{tint:+.0f}"))
            self.right.set_wb_display(round(T), round(tint))

    def set_before(self, on):
        self._before = bool(on)
        self.toolbar.before.setChecked(self._before)
        self.right.set_tool("original", self._before)
        if self._before:
            self._request_original()
        self.canvas.set_before(self._before)

    def set_split(self, on):
        self._split = bool(on)
        self.toolbar.split.setChecked(self._split)
        self.right.set_tool("split", self._split)
        if self._split:
            self._request_original()
        self.canvas.set_split(self._split)

    def set_clipping(self, on):
        self.canvas.set_clipping(bool(on))
        self.toolbar.clipping.setChecked(bool(on))
        self.right.hist.set_clipping_on(bool(on))

    # ------------------------------------------------------------------ histogram drag (Lightroom-style)
    def _hist_start(self, field):
        if not self.current or self._crop_mode or field not in HIST_DRAG:
            return
        self._hist_drag = (field, float(getattr(self.s, field)))

    def _hist_value(self, field, frac):
        lo, hi, span = HIST_DRAG[field]
        v = min(max(self._hist_drag[1] + frac * span, lo), hi)
        return round(v / 0.05) * 0.05 if field == "exposure_ev" else float(round(v))

    def _hist_text(self, field, v):
        return f"{tr(FIELD_LABELS.get(field, field))}  " + (f"{v:+.2f} EV" if field == "exposure_ev" else f"{v:+.0f}")

    def _hist_move(self, field, frac):
        if not self._hist_drag or self._hist_drag[0] != field:
            return
        v = self._hist_value(field, frac)
        if abs(v - getattr(self.s, field)) < 1e-9:
            return
        w = self.right.b.binds.get(field)
        if w is not None:
            w.set_value(v)
        self.right.hist.set_value_text(self._hist_text(field, v))
        self.on_edit({field: v}, False)

    def _hist_end(self, field):
        if not self._hist_drag or self._hist_drag[0] != field:
            return
        start = self._hist_drag[1]
        self._hist_drag = None
        v = getattr(self.s, field)
        if self._uncommitted or abs(v - start) > 1e-9:
            self.on_edit({field: v}, True, label=self._hist_text(field, v))

    # ------------------------------------------------------------------ presets & LUTs
    def import_presets(self, kind="preset"):
        """kind 'preset': Lightroom / Camera Raw .xmp, .lrtemplate, .cube, .sprkpreset -> My Looks.
        kind 'lut': a .cube for the Creative LUT control of the current photo."""
        from .. import luts, presets

        if kind == "lut":
            title, flt = tr("Import LUT"), tr("Cube LUTs (*.cube);;All files (*)")
        else:
            title, flt = tr("Import presets"), tr(presets.IMPORT_FILTER)
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, title, self.lib.prefs.get("preset_dir", os.path.expanduser("~")), flt)
        if not paths:
            return
        self.lib.prefs["preset_dir"] = os.path.dirname(paths[0])
        if kind == "lut":
            try:
                name = luts.import_cube(paths[0])
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, title, f"{os.path.basename(paths[0])}\n\n{tr(str(exc))}")
                return
            self.right.refresh_luts(name)
            if self.current:
                self.on_edit({"lut_name": name}, True, label=trf("LUT: {name}", name=name))
                self.right.load(self.s, raw=is_raw(self.current), wb_shown=self._info.get("wb"))
            self.statusBar().showMessage(trf("Imported LUT “{name}”", name=name), 4000)
            return
        user = dict(self.lib.prefs.get("user_looks", {}))
        added, problems, ignored = [], [], []
        for p in paths:
            try:
                pr = presets.import_file(p)
            except Exception as exc:
                problems.append(f"{os.path.basename(p)}: {tr(str(exc))}")
                continue
            name = pr.name.strip() or os.path.splitext(os.path.basename(p))[0]
            if name in looks_mod.LOOKS:
                name += " (imported)"
            values = dict(pr.values)
            values["_source"] = pr.source
            user[name] = values
            added.append(name)
            if pr.unsupported:
                ignored.append(f"{name}: " + ", ".join(pr.unsupported[:10]) + (" …" if len(pr.unsupported) > 10 else ""))
        self.lib.prefs["user_looks"] = user
        self.lib.save()
        self.left.looks.populate(user)
        self.right.refresh_luts()
        self._thumb_key = None
        if len(added) == 1 and self.current:
            self.apply_look(added[0])
        else:
            self._request_look_thumbs()
        msg = trf("Imported {n} preset(s) into My Looks.", n=len(added)) if added else tr("Nothing was imported.")
        if len(added) > 1:
            msg += tr(" Click one in the Looks list to apply it.")
        if ignored:
            msg += (tr("\n\nSettings with no equivalent here were skipped (the rest of each preset is applied):\n")
                    + "\n".join(ignored[:8]))
        if problems:
            msg += tr("\n\nCould not read:\n") + "\n".join(problems[:8])
        (QtWidgets.QMessageBox.warning if problems and not added else QtWidgets.QMessageBox.information)(
            self, tr("Import presets"), msg)

    def export_preset(self, name: str = ""):
        """Save a look (or, with no name, the current settings) as a .sprkpreset file to share."""
        from .. import presets

        if name:
            values = self._look_values(name)
            if values is None:
                return
            values = dict(values)
        else:
            if not self.current:
                return
            name = self.s.look or os.path.splitext(os.path.basename(self.current))[0]
            values = looks_mod.capture(self.s)
            values.update(exposure_ev=self.s.exposure_ev)
            if self.s.wb_mode == "custom":
                values.update(wb_mode="custom", temperature=self.s.temperature, tint=self.s.tint)
        values = {k: v for k, v in values.items() if not k.startswith("_")}
        safe = "".join(c if c.isalnum() or c in " -_()" else "_" for c in name).strip() or "preset"
        start = os.path.join(self.lib.prefs.get("preset_dir", os.path.expanduser("~")), safe + presets.EXT)
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, tr("Export preset"), start,
                                                        trf("{app} preset (*{ext})", app=APP_NAME, ext=presets.EXT))
        if not path:
            return
        try:
            presets.export_preset(path, name, values)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, tr("Export preset"), str(exc))
            return
        self.lib.prefs["preset_dir"] = os.path.dirname(path)
        self.statusBar().showMessage(trf("Saved preset “{name}” — share it, or import it with File ▸ Import",
                                         name=name), 5000)

    def _open_preset_folder(self):
        from .. import luts

        d = luts.lut_dir()
        os.makedirs(d, exist_ok=True)
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(d))

    def zoom_preset(self, key):
        c = self.canvas
        {"fit": c.fit, "fill": c.fill, "100": lambda: c.set_zoom(1.0), "200": lambda: c.set_zoom(2.0)}[key]()
        self.left.set_zoom_state(*c.zoom_percent())

    # ------------------------------------------------------------------ crop mode
    def enter_crop(self):
        if not self.current or not self._engine_ready:
            return
        self._set_wb_tool(False)
        self._crop_mode = True
        self._crop_saved = {f: getattr(self.s, f) for f in GEOMETRY_FIELDS}
        self.canvas.set_before(False)
        self.canvas.set_split(False)
        self.canvas.set_mode("crop")
        self.right.crop_sec.setVisible(True)
        self.right.set_tool("crop", True)
        self._frame = self._info.get("frame_size") or self._info.get("crop_size") or (3, 2)
        self._sync_crop_overlay()
        self._schedule_crop()

    def _ratio(self):
        fw, fh = self._frame
        return crop_ratio(self.s, fw, fh)  # the film gate while Film Edge is on, else the aspect setting

    def _sync_crop_overlay(self):
        fw, fh = self._frame
        rect = effective_crop(self.s, fw, fh)
        ratio = self._ratio()
        self.canvas.set_crop(rect, ratio)

    def _apply_aspect(self):
        fw, fh = self._frame
        s = self.s.copy()
        rect = effective_crop(s, fw, fh)
        if self.s.aspect not in ("Free",) and abs((rect[2] - rect[0]) - 1) < 1e-6 and abs((rect[3] - rect[1]) - 1) < 1e-6:
            pass
        self.s.crop_l, self.s.crop_t, self.s.crop_r, self.s.crop_b = rect
        self._sync_crop_overlay()

    def _crop_changed(self, rect):
        self.s.crop_l, self.s.crop_t, self.s.crop_r, self.s.crop_b = rect

    def on_crop_action(self, action):
        if not self.current:
            return
        if action in ("rotl", "rotr"):
            rot = (self.s.rotation + (-1 if action == "rotl" else 1)) % 4
            upd = {"rotation": rot, "crop_l": 0.0, "crop_t": 0.0, "crop_r": 1.0, "crop_b": 1.0}
            self.on_edit(upd, True, label=trf("Rotate {d}", d=tr("left" if action == "rotl" else "right")))
            return
        if action in ("fliph", "flipv"):
            f = "flip_h" if action == "fliph" else "flip_v"
            self.on_edit({f: not getattr(self.s, f)}, True)
            return
        if action == "reset":
            self.s.crop_l, self.s.crop_t, self.s.crop_r, self.s.crop_b = 0.0, 0.0, 1.0, 1.0
            self.on_edit({"aspect": "Original", "straighten": 0.0}, False)
            self.right.b.load(self.s)
            self._sync_crop_overlay()
            return
        if not self._crop_mode:
            return
        if action == "cancel":
            for k, v in self._crop_saved.items():
                setattr(self.s, k, v)
            self.right.b.load(self.s)
        self._crop_mode = False
        self.canvas.set_mode("view")
        self.right.crop_sec.setVisible(False)
        self.right.set_tool("crop", False)
        self.canvas.set_before(self._before)
        self.canvas.set_split(self._split)
        self.canvas._fit = True
        if action == "done":
            new = {f: getattr(self.s, f) for f in GEOMETRY_FIELDS}
            for k, v in self._crop_saved.items():
                setattr(self.s, k, v)
            self.on_edit(new, True, label=tr("Crop"))
            if new == self._crop_saved:
                self._schedule()
        else:
            self.lib.set_settings(self.current, self.s)
            self._shown = (-1, -1)
            self._schedule()

    # ------------------------------------------------------------------ filmstrip actions
    def _refresh_meta(self, paths):
        for p in paths:
            self.strip.set_meta(p, self.lib.rating(p), self.lib.flag(p), self.lib.is_edited(p))

    def _targets(self, paths=None):
        if paths:
            return list(paths)
        sel = self.strip.selected_paths()
        if self.current and self.current in sel:
            return sel
        return [self.current] if self.current else []

    def _rate(self, n, paths=None):
        paths = self._targets(paths)
        for p in paths:
            self.lib.set_meta(p, rating=int(n))
        self._refresh_meta(paths)
        self.lib.save()
        self.statusBar().showMessage((tr("Rating cleared") if not n else trf("Rated {n}★", n=n)) +
                                     (trf(" ({n} photos)", n=len(paths)) if len(paths) > 1 else ""), 2500)

    def _flag(self, flag, paths=None):
        paths = self._targets(paths)
        for p in paths:
            self.lib.set_meta(p, flag=flag)
        self._refresh_meta(paths)
        self.lib.save()
        self.statusBar().showMessage(tr({"pick": "Flagged as pick", "reject": "Flagged as rejected"}.get(
            flag, "Flag removed")) + (trf(" ({n} photos)", n=len(paths)) if len(paths) > 1 else ""), 2500)

    def _look_groups(self):
        groups = {c: [] for c in looks_mod.CATEGORIES}
        for name, (cat, _, _) in looks_mod.LOOKS.items():
            groups[cat].append(name)
        groups["My Looks"] = sorted(self.lib.prefs.get("user_looks", {}), key=str.lower)
        return list(groups.items())

    def _look_updates(self, name) -> dict | None:
        values = self._look_values(name)
        if values is None:
            return None
        upd = looks_mod.look_values(values)
        if name not in looks_mod.LOOKS:
            for k in ("exposure_ev", "wb_mode", "temperature", "tint"):
                if k in values:
                    upd[k] = values[k]
        upd["look"] = name
        return upd

    def _batch(self, paths, make_updates, label):
        """Apply edits to several photos: the open one through the normal edit path (history, preview),
        the others directly, with fresh filmstrip thumbnails rendered in the background."""
        others = []
        for p in paths:
            if p == self.current:
                continue
            s = self.lib.settings_for(p)
            upd = make_updates(s)
            if not upd:
                continue
            d = s.to_dict()
            d.update({k: v for k, v in upd.items() if k != "_v"})
            self.lib.set_settings(p, DevelopSettings.from_dict(d))
            others.append(p)
        if others:
            self.service.request_strip_thumbs([(p, self.lib.settings_for(p)) for p in others])
            self._refresh_meta(others)
        if self.current in paths:
            upd = make_updates(self.s.copy())
            if upd:
                self.on_edit({k: v for k, v in upd.items() if k != "_v"}, True, label=label)
                self.right.load(self.s, raw=is_raw(self.current), wb_shown=self._info.get("wb"))
                self.left.looks.set_current(self.s.look)
        self.lib.save()
        n = len(others) + (1 if self.current in paths else 0)
        if n > 1:
            self.statusBar().showMessage(trf("{label} — {n} photos", label=label, n=n), 3000)

    def strip_action(self, action, paths, arg):
        if action == "filter":
            self.strip.set_filter(arg)
            self.lib.prefs["strip_filter"] = arg
            self.lib.save()
            return
        if not paths:
            return
        if action == "rate":
            self._rate(arg, paths)
        elif action == "flag":
            self._flag(arg, paths)
        elif action == "look":
            self._batch(paths, lambda s: self._look_updates(arg), trf("Look: {name}", name=tr(arg)))
        elif action == "copy":
            src = self.s if paths[0] == self.current else self.lib.settings_for(paths[0])
            fields = [f for g, fs in SYNC_GROUPS.items() if g != "Crop & rotate" for f in fs]
            self.clipboard = {f: getattr(src, f) for f in fields}
            self.statusBar().showMessage(trf("Copied the settings of {name} (everything except crop) — right-click "
                                             "▸ Paste", name=os.path.basename(paths[0])), 4000)
        elif action == "paste":
            if self.clipboard:
                self._batch(paths, lambda s: dict(self.clipboard), tr("Paste settings"))
        elif action == "sync":
            self.sync_dialog()
        elif action == "reset":
            if len(paths) > 1 and QtWidgets.QMessageBox.question(
                    self, tr("Reset Settings"), trf("Reset all edits of {n} photos?", n=len(paths))
            ) != QtWidgets.QMessageBox.Yes:
                return
            self._batch(paths, lambda s: self.lib.default_settings().to_dict(), tr("Reset"))
        elif action in ("rotl", "rotr"):
            step = -1 if action == "rotl" else 1
            self._batch(paths, lambda s: {"rotation": (s.rotation + step) % 4, "crop_l": 0.0, "crop_t": 0.0,
                                          "crop_r": 1.0, "crop_b": 1.0},
                        trf("Rotate {d}", d=tr("left" if step < 0 else "right")))
        elif action == "export":
            self.export(paths)
        elif action == "explorer":
            QtCore.QProcess.startDetached("explorer.exe", ["/select,", os.path.normpath(paths[0])])
        elif action == "open":
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(paths[0]))
        elif action == "copy_path":
            QtWidgets.QApplication.clipboard().setText("\n".join(os.path.normpath(p) for p in paths))
            self.statusBar().showMessage("Copied", 2000)
        elif action == "remove":
            self.remove_paths(paths)

    # ------------------------------------------------------------------ copy / paste / sync
    def copy_dialog(self):
        if not self.current:
            return
        groups = list(SYNC_GROUPS)
        dlg = GroupsDialog("Copy Settings", groups, [g for g in groups if g != "Crop & rotate"], "Copy", self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            fields = [f for g in dlg.groups() for f in SYNC_GROUPS[g]]
            self.clipboard = {f: getattr(self.s, f) for f in fields}
            self.statusBar().showMessage(trf("Copied {n} group(s)", n=len(dlg.groups())), 3000)

    def paste_settings(self):
        if not self.clipboard:
            self.statusBar().showMessage("Copy settings first (Copy…)", 3000)
            return
        paths = list(dict.fromkeys(self.strip.selected_paths() + ([self.current] if self.current else [])))
        self._batch(paths, lambda s: dict(self.clipboard), tr("Paste settings"))
        self.statusBar().showMessage(trf("Pasted to {n} photo(s)", n=len(paths)), 3000)

    def sync_dialog(self):
        targets = [p for p in self.strip.selected_paths() if p != self.current]
        if not self.current or not targets:
            self.statusBar().showMessage("Ctrl/Shift-click other photos in the filmstrip first", 4000)
            return
        groups = list(SYNC_GROUPS)
        dlg = GroupsDialog(trf("Sync Settings to {n} photo(s)", n=len(targets)), groups,
                           [g for g in groups if g != "Crop & rotate"], "Synchronize", self,
                           note="Copy the checked settings from the current photo to the selected photos.")
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return
        fields = [f for g in dlg.groups() for f in SYNC_GROUPS[g]]
        self._batch(targets, lambda s: {f: getattr(self.s, f) for f in fields}, tr("Sync settings"))
        self.statusBar().showMessage(trf("Synced {g} group(s) to {n} photo(s)", g=len(dlg.groups()), n=len(targets)),
                                     4000)

    def reset_photo(self):
        if self.current:
            self.on_edit(self.lib.default_settings().to_dict(), True, label=tr("Reset"))

    def save_default(self):
        self.lib.default = self.s.to_dict()
        self.lib.save()
        self.statusBar().showMessage("Saved as the default for new photos", 3000)

    def factory_default(self):
        self.lib.default = {}
        self.lib.save()
        self.statusBar().showMessage("New photos will use factory defaults", 3000)

    # ------------------------------------------------------------------ export
    def export(self, paths=None):
        if not self.lib.photos:
            self.statusBar().showMessage("Open some photos first", 3000)
            return
        if self._exporter is not None:
            self.statusBar().showMessage("An export is already running (top left). Stop it with ✕ first.", 4000)
            return
        sel = list(paths) if paths else self.strip.selected_paths()
        dlg = ExportDialog(1 if self.current else 0, len(sel), len(self.lib.photos),
                           self.lib.prefs.get("export", {}), self)
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return
        o = dlg.options()
        self.lib.prefs["export"] = {k: v for k, v in o.items() if k != "scope"}
        self.lib.save()
        paths = {"current": [self.current] if self.current else [], "selected": sel,
                 "all": list(self.lib.photos)}[o["scope"]]
        jobs = [(p, self.lib.settings_for(p) if p != self.current else self.s.copy()) for p in paths]
        if jobs:
            self.start_export(jobs, o)

    def start_export(self, jobs, o):
        """Run an export in the background; progress shows next to Export… in the top bar."""
        status = self.top.export_status
        status.start(len(jobs))
        self._exporter = ex = Exporter(jobs, o)
        ex.progress.connect(status.update_progress)

        def done(written, errors):
            self._exporter = None
            self._export_result = (list(written), list(errors))
            status.finish(len(written), len(errors), ex.cancelled)
            self.statusBar().showMessage(
                trf("Exported {n} file(s) to {folder}", n=len(written), folder=os.path.dirname(written[0]))
                if written else trf("Exported {n} file(s)", n=0), 8000)

        ex.finished.connect(done)
        ex.start()

    def _stop_export(self):
        if self._exporter is not None:
            self._exporter.cancel()
            self.top.export_status.label.setText(tr("Stopping…"))

    def _show_export(self):
        written = getattr(self, "_export_result", ([], []))[0]
        if written:
            QtCore.QProcess.startDetached("explorer.exe", ["/select,", os.path.normpath(written[0])])

    def _export_details(self):
        errors = getattr(self, "_export_result", ([], []))[1]
        if errors:
            QtWidgets.QMessageBox.warning(self, tr("Export"), tr("These photos could not be exported:\n\n")
                                          + "\n".join(errors[:12]))

    # ------------------------------------------------------------------ help
    def show_shortcuts(self):
        QtWidgets.QMessageBox.information(self, tr("Keyboard shortcuts"), "\n".join(tr(line) for line in [
            "Ctrl+O / Ctrl+Shift+O\tOpen photos / folder",
            "Ctrl+E\t\tExport",
            "← / →\t\tPrevious / next photo",
            "R\t\tCrop & straighten (Enter = apply, Esc = cancel)",
            "W\t\tWhite balance picker",
            "\\\t\tBefore (original)",
            "Y\t\tBefore | After split",
            "J\t\tShow clipping",
            "F / Z\t\tFit / 100%   (double-click the image too)",
            "Mouse wheel\tZoom   ·   drag to pan   ·   click the Navigator to jump",
            "Ctrl+Z / Ctrl+Y\tUndo / redo   (or click a History step)",
            "Ctrl+Shift+C / V\tCopy… / paste settings",
            "Ctrl+Shift+S\tSync settings to selected photos",
            "Ctrl+R\t\tReset photo",
            "0 – 5\t\tStar rating   ·   P / X / U  pick / reject / unflag",
            "Shift+F\t\tShow / hide the film frame in the preview",
            "Ctrl+Shift+I\tImport presets & LUTs (.xmp, .lrtemplate, .cube)",
            "F7 / F8\t\tLeft / Develop panel",
            "Drag on the histogram to change Blacks / Shadows / Exposure / Highlights / Whites",
            "Right-click filmstrip photos for ratings, looks, copy / paste, rotate, export…",
            "Double-click a slider label to reset it",
        ]))

    def about(self):
        if i18n.LANG == "zh_CN":
            QtWidgets.QMessageBox.about(self, trf("About {APP_NAME}", APP_NAME=APP_NAME), (
                f"<h3>{APP_NAME} {APP_VERSION}</h3>"
                "<p>适用于 Windows 的光谱胶片与印放模拟。</p>"
                "<p>胶片引擎与彩色胶片 / 相纸数据：<b>spektrafilm</b>，作者 Andrea Volpato —— "
                "<a href='https://github.com/andreavolpato/spektrafilm'>github.com/andreavolpato/spektrafilm</a>。"
                "代码 GPL-3.0；数据 CC BY-SA 4.0。</p>"
                "<p>黑白胶片数据、Ilford Multigrade 相纸与 CineStill 800T 别名来自 <b>SpektraLab</b>"
                "（<a href='https://github.com/JamesQiu2005/SpektraLab'>github.com/JamesQiu2005/SpektraLab</a>，"
                "GPL-3.0），依据厂商公开的技术资料制作；工作流程与胶片边框也受其启发。</p>"
                "<p>“相机风格”的风格是用本软件的工具做出的近似效果，并非理光、徕卡或富士的官方配置。预设导入可读取 "
                "Lightroom / Camera Raw 的 .xmp、.lrtemplate 文件和 .cube LUT。胶片、相机、软件和品牌名称均为其所有者的"
                f"商标，仅用于说明数据、文件格式或灵感来源。{APP_NAME} 与上述项目或公司均无关联。</p>"
                "<p>界面字体：<b>Inter</b>，作者 Rasmus Andersson（SIL Open Font License 1.1）。</p>"
                f"<p>{APP_NAME} 是遵循 GNU GPL v3 的自由软件，你有权获得其源代码。</p>"))
            return
        QtWidgets.QMessageBox.about(self, f"About {APP_NAME}", (
            f"<h3>{APP_NAME} {APP_VERSION}</h3>"
            "<p>Spectral film &amp; print simulation for Windows.</p>"
            "<p>Film engine and colour film / paper profiles: <b>spektrafilm</b> by Andrea Volpato — "
            "<a href='https://github.com/andreavolpato/spektrafilm'>github.com/andreavolpato/spektrafilm</a>. "
            "Code GPL-3.0; profiles CC BY-SA 4.0.</p>"
            "<p>Black-and-white film profiles, Ilford Multigrade paper and the CineStill 800T alias are from "
            "<b>SpektraLab</b> (<a href='https://github.com/JamesQiu2005/SpektraLab'>github.com/JamesQiu2005/SpektraLab</a>, "
            "GPL-3.0), built from the manufacturers' published datasheets. The workflow is also inspired by it.</p>"
            "<p>Camera-inspired Looks are approximations made with this app's tools; they are not Ricoh, Leica or "
            "Fujifilm profiles. Preset import reads Lightroom / Camera Raw .xmp and .lrtemplate files and .cube "
            "LUTs. Film, camera, software and brand names are trademarks of their owners and only describe the "
            "data, file formats or inspiration. "
            f"{APP_NAME} is not affiliated with any of these projects or companies.</p>"
            "<p>Interface font: <b>Inter</b> by Rasmus Andersson (SIL Open Font License 1.1).</p>"
            f"<p>{APP_NAME} is free software under the GNU GPL v3. You are entitled to its source code.</p>"))

    # ------------------------------------------------------------------ lifecycle
    def showEvent(self, e):
        super().showEvent(e)
        try:
            import ctypes

            hwnd = int(self.winId())
            val = ctypes.c_int(1)
            for attr in (20, 19):
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(val), ctypes.sizeof(val)) == 0:
                    break
        except Exception:
            pass

    def closeEvent(self, e):
        self.lib.prefs["window"] = bytes(self.saveGeometry().toHex()).decode()
        if self.current:
            self.lib.set_settings(self.current, self.s)
        self.lib.save()
        self.service.stop()
        super().closeEvent(e)
