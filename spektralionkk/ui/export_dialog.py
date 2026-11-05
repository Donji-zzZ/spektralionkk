"""Export dialog and background batch exporter."""

from __future__ import annotations

import os
import threading
import time
import traceback

from PySide6 import QtCore, QtWidgets

from .. import engine
from ..i18n import tr, translate_tree, trf

COLOR_SPACES = ["sRGB", "Display P3", "Adobe RGB (1998)", "ProPhoto RGB", "ITU-R BT.2020"]
FORMATS = [("JPEG", "jpeg", ".jpg"), ("TIFF 16-bit", "tiff16", ".tif"), ("TIFF 8-bit", "tiff8", ".tif"),
           ("PNG 8-bit", "png", ".png")]
SIZES = [("Full resolution", None), ("Long edge 6000 px", 6000), ("Long edge 4096 px", 4096),
         ("Long edge 3000 px", 3000), ("Long edge 2048 px", 2048), ("Long edge 1080 px", 1080)]


class ExportDialog(QtWidgets.QDialog):
    def __init__(self, n_current: int, n_selected: int, n_all: int, prefs: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export")
        self.setMinimumWidth(460)
        form = QtWidgets.QFormLayout(self)
        form.setLabelAlignment(QtCore.Qt.AlignRight)
        form.setVerticalSpacing(10)

        self.scope = QtWidgets.QComboBox()
        self.scope.addItem(tr("Current photo"), "current")
        if n_selected > 1:
            self.scope.addItem(trf("Selected photos ({n})", n=n_selected), "selected")
        self.scope.addItem(trf("All photos in library ({n})", n=n_all), "all")
        if n_selected > 1:
            self.scope.setCurrentIndex(1)
        form.addRow("Export", self.scope)

        self.fmt = QtWidgets.QComboBox()
        for label, key, _ in FORMATS:
            self.fmt.addItem(label, key)
        self.fmt.setCurrentIndex(max(0, self.fmt.findData(prefs.get("format", "jpeg"))))
        form.addRow("Format", self.fmt)

        self.quality = QtWidgets.QSpinBox()
        self.quality.setRange(50, 100)
        self.quality.setValue(int(prefs.get("quality", 95)))
        form.addRow("JPEG quality", self.quality)
        self.fmt.currentIndexChanged.connect(lambda: self.quality.setEnabled(self.fmt.currentData() == "jpeg"))
        self.quality.setEnabled(self.fmt.currentData() == "jpeg")

        self.cs = QtWidgets.QComboBox()
        self.cs.addItems(COLOR_SPACES)
        self.cs.setCurrentText(prefs.get("color_space", "sRGB"))
        form.addRow("Colour space", self.cs)

        self.size = QtWidgets.QComboBox()
        for label, v in SIZES:
            self.size.addItem(label, v)
        self.size.setCurrentIndex(max(0, self.size.findData(prefs.get("long_edge"))))
        form.addRow("Size", self.size)

        row = QtWidgets.QHBoxLayout()
        self.folder = QtWidgets.QLineEdit(prefs.get("folder", ""))
        self.folder.setPlaceholderText("Same folder as each photo")
        b = QtWidgets.QPushButton("Browse…")
        b.clicked.connect(self._browse)
        row.addWidget(self.folder, 1)
        row.addWidget(b)
        w = QtWidgets.QWidget()
        w.setLayout(row)
        form.addRow("Folder", w)

        self.suffix = QtWidgets.QLineEdit(prefs.get("suffix", "_sprk"))
        form.addRow("File name suffix", self.suffix)

        self.frame = QtWidgets.QCheckBox("Include the film frame and date stamp")
        self.frame.setToolTip("Uses each photo's Film Edge settings (border, edge print, date stamp).\n"
                              "Untick to export just the picture.")
        self.frame.setChecked(bool(prefs.get("frame", True)))
        form.addRow("Frame", self.frame)

        note = QtWidgets.QLabel("Full-quality renders run on the CPU: roughly 20–60 s for a 24–45 MP RAW. Progress "
                                "shows next to Export… at the top left, and you can keep editing meanwhile.")
        note.setObjectName("Faint")
        note.setWordWrap(True)
        form.addRow(note)

        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.button(QtWidgets.QDialogButtonBox.Ok).setText("Export")
        bb.button(QtWidgets.QDialogButtonBox.Ok).setObjectName("Primary")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)
        translate_tree(self)

    def _browse(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, tr("Export folder"),
                                                       self.folder.text() or os.path.expanduser("~"))
        if d:
            self.folder.setText(d)

    def options(self) -> dict:
        return {"scope": self.scope.currentData(), "format": self.fmt.currentData(),
                "quality": self.quality.value(), "color_space": self.cs.currentText(),
                "long_edge": self.size.currentData(), "folder": self.folder.text().strip(),
                "suffix": self.suffix.text(), "frame": self.frame.isChecked()}


def output_path(src: str, opts: dict) -> str:
    ext = {"jpeg": ".jpg", "tiff16": ".tif", "tiff8": ".tif", "png": ".png"}[opts["format"]]
    folder = opts["folder"] or os.path.dirname(src)
    base = os.path.splitext(os.path.basename(src))[0] + (opts["suffix"] or "")
    path = os.path.join(folder, base + ext)
    n = 2
    while os.path.exists(path):
        path = os.path.join(folder, f"{base}-{n}{ext}")
        n += 1
    return path


class Exporter(QtCore.QObject):
    progress = QtCore.Signal(int, int, str)  # done, total, current file
    finished = QtCore.Signal(list, list)  # written paths, errors

    def __init__(self, jobs, opts, parent=None):
        """jobs: list of (path, DevelopSettings)"""
        super().__init__(parent)
        self.jobs, self.opts = jobs, opts
        self._cancel = False

    @property
    def cancelled(self) -> bool:
        return self._cancel

    def cancel(self):
        self._cancel = True

    def start(self):
        threading.Thread(target=self._run, name="export", daemon=True).start()

    def _run(self):
        written, errors = [], []
        o = self.opts
        n = len(self.jobs)
        for i, (path, s) in enumerate(self.jobs):
            if self._cancel:
                break
            name = os.path.basename(path)
            self.progress.emit(i * 100, n * 100, name)
            try:
                if o["folder"]:
                    os.makedirs(o["folder"], exist_ok=True)
                t0 = time.perf_counter()
                rgb = engine.render_full(
                    path, s, output_color_space=o["color_space"], long_edge=o["long_edge"],
                    progress=lambda f, i=i, name=name: self.progress.emit(i * 100 + int(f * 95), n * 100, name),
                    cancel=lambda: self._cancel, include_frame=bool(o.get("frame", True)))
                out = output_path(path, o)
                fmt = o["format"]
                engine.save_image(out, rgb, color_space=o["color_space"],
                                  fmt="jpeg" if fmt == "jpeg" else fmt,
                                  quality=o["quality"], bit_depth=8 if fmt == "tiff8" else 16)
                written.append(out)
                print(f"exported {out} in {time.perf_counter() - t0:.1f}s")
            except engine.RenderCancelled:
                break
            except MemoryError:
                errors.append(trf("{name}: not enough memory — try a smaller export size", name=name))
            except Exception as exc:
                traceback.print_exc()
                errors.append(f"{name}: {type(exc).__name__}: {exc}")
        self.progress.emit(n * 100, n * 100, "")
        self.finished.emit(written, errors)
