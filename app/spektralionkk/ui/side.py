"""Side-panel widgets: Navigator, Histogram (+ camera info), Looks browser, History."""

from __future__ import annotations

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from .. import looks as looks_mod
from ..i18n import tr, trf
from . import theme
from .canvas import to_qimage


class Navigator(QtWidgets.QWidget):
    """Thumbnail of the photo with the visible area outlined; click or drag to move there."""

    navigate = QtCore.Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self._pm = None
        self._view = None

    def set_image(self, img: np.ndarray | None):
        self._pm = QtGui.QPixmap.fromImage(to_qimage(img)) if img is not None else None
        self.update()

    def set_view(self, rect):
        self._view = rect
        self.update()

    def _target(self):
        if self._pm is None:
            return QtCore.QRectF()
        r = QtCore.QRectF(self.rect()).adjusted(6, 6, -6, -6)
        s = min(r.width() / self._pm.width(), r.height() / self._pm.height())
        w, h = self._pm.width() * s, self._pm.height() * s
        return QtCore.QRectF(r.center().x() - w / 2, r.center().y() - h / 2, w, h)

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        p.fillRect(self.rect(), QtGui.QColor("#141415"))
        if self._pm is None:
            p.setPen(QtGui.QColor(theme.TEXT_FAINT))
            p.drawText(self.rect(), QtCore.Qt.AlignCenter, tr("Navigator"))
            return
        t = self._target()
        p.drawPixmap(t, self._pm, QtCore.QRectF(self._pm.rect()))
        if self._view:
            x, y, w, h = self._view
            R = QtCore.QRectF(t.left() + x * t.width(), t.top() + y * t.height(), w * t.width(), h * t.height())
            R = R.intersected(t)
            p.fillRect(t, QtGui.QColor(0, 0, 0, 90))
            p.drawPixmap(R, self._pm, QtCore.QRectF(
                (R.left() - t.left()) / t.width() * self._pm.width(), (R.top() - t.top()) / t.height() * self._pm.height(),
                R.width() / t.width() * self._pm.width(), R.height() / t.height() * self._pm.height()))
            pen = QtGui.QPen(QtGui.QColor(theme.ACCENT), 2)
            p.setPen(pen)
            p.drawRect(R)

    def _emit(self, pos):
        t = self._target()
        if t.isEmpty():
            return
        u = (pos.x() - t.left()) / t.width()
        v = (pos.y() - t.top()) / t.height()
        self.navigate.emit(min(max(u, 0), 1), min(max(v, 0), 1))

    def mousePressEvent(self, e):
        self._emit(e.position())

    def mouseMoveEvent(self, e):
        if e.buttons() & QtCore.Qt.LeftButton:
            self._emit(e.position())


HIST_ZONES = ((0.00, 0.10, "blacks", "Blacks"), (0.10, 0.32, "shadows", "Shadows"),
              (0.32, 0.68, "exposure_ev", "Exposure"), (0.68, 0.90, "highlights", "Highlights"),
              (0.90, 1.00, "whites", "Whites"))


class Histogram(QtWidgets.QWidget):
    """RGB histogram with clipping indicators (click the triangles) and Lightroom-style drag-to-adjust:
    drag left/right over a zone to change Blacks, Shadows, Exposure, Highlights or Whites."""

    clippingToggled = QtCore.Signal(bool)
    dragStarted = QtCore.Signal(str)
    dragged = QtCore.Signal(str, float)  # field, horizontal drag as a fraction of the width
    dragFinished = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(96)
        self.setMouseTracking(True)
        self._paths = []
        self._lo = self._hi = 0.0
        self._on = False
        self._zone = None
        self._drag = None
        self.value_text = ""

    def _zone_at(self, x):
        f = x / max(self.width(), 1)
        for z in HIST_ZONES:
            if z[0] <= f < z[1] or (f >= 1.0 and z[1] == 1.0):
                return z
        return None

    def mouseMoveEvent(self, e):
        x = e.position().x()
        if self._drag:
            self.dragged.emit(self._drag[0], (x - self._drag[1]) / max(self.width(), 1))
            return
        z = self._zone_at(x) if e.position().y() >= 16 else None
        if z != self._zone:
            self._zone = z
            self.setCursor(QtCore.Qt.SizeHorCursor if z else QtCore.Qt.PointingHandCursor)
            self.setToolTip(trf("Drag left/right to adjust {zone}", zone=tr(z[3])) if z else tr("Click to show clipping"))
            self.update()

    def leaveEvent(self, e):
        if not self._drag:
            self._zone = None
            self.update()

    def mouseReleaseEvent(self, e):
        if self._drag:
            field = self._drag[0]
            self._drag = None
            self.value_text = ""
            self.dragFinished.emit(field)
            self.update()

    def set_value_text(self, text):
        self.value_text = text
        self.update()

    def set_image(self, img: np.ndarray | None, inset=None):
        self._paths = []
        if img is not None:
            if inset:
                l, t, w, h = inset
                img = img[t:t + h, l:l + w]
            step = max(1, int(np.sqrt(img.shape[0] * img.shape[1] / 120000)))
            sub = img[::step, ::step].reshape(-1, 3)
            self._hi = float((sub >= 254).any(axis=1).mean() * 100)
            self._lo = float((sub <= 2).all(axis=1).mean() * 100)
            w, h = self.width() - 12, self.height() - 16
            for c, col in enumerate(("#ff5a4a", "#4ad27a", "#4a8cff")):
                hist, _ = np.histogram(sub[:, c], bins=64, range=(0, 256))
                hist = np.sqrt(hist.astype(np.float64))
                hist /= max(hist.max(), 1e-9)
                path = QtGui.QPainterPath(QtCore.QPointF(6, 8 + h))
                for i, v in enumerate(hist):
                    path.lineTo(6 + w * i / 63.0, 8 + h - v * h)
                path.lineTo(6 + w, 8 + h)
                path.closeSubpath()
                self._paths.append((path, QtGui.QColor(col)))
        self.update()

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.fillRect(self.rect(), QtGui.QColor("#141415"))
        if self._zone:  # highlight the zone under the cursor / being dragged
            z = self._zone
            p.fillRect(QtCore.QRectF(z[0] * self.width(), 0, (z[1] - z[0]) * self.width(), self.height()),
                       QtGui.QColor(255, 255, 255, 18))
        p.setCompositionMode(QtGui.QPainter.CompositionMode_Screen)
        for path, col in self._paths:
            col.setAlpha(160)
            p.setBrush(col)
            p.setPen(QtCore.Qt.NoPen)
            p.drawPath(path)
        p.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)
        for x, pct, col in ((6, self._lo, "#4a8cff"), (self.width() - 18, self._hi, "#ff4a3a")):
            on = pct > 0.05
            c = QtGui.QColor(col if on else theme.TEXT_FAINT)
            if self._on and on:
                c = QtGui.QColor("white")
            p.setBrush(c)
            p.setPen(QtCore.Qt.NoPen)
            tri = QtGui.QPolygonF([QtCore.QPointF(x, 4), QtCore.QPointF(x + 12, 4), QtCore.QPointF(x + 6, 12)])
            p.drawPolygon(tri)
        label = self.value_text or (tr(self._zone[3]) if self._zone else "")
        if label:
            f = p.font()
            f.setPointSizeF(8)
            f.setBold(True)
            p.setFont(f)
            p.setPen(QtGui.QColor(theme.TEXT))
            p.drawText(QtCore.QRectF(0, self.height() - 18, self.width() - 8, 16),
                       QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, label)

    def mousePressEvent(self, e):
        pos = e.position()
        on_triangle = pos.y() < 16 and (pos.x() < 24 or pos.x() > self.width() - 24)
        if on_triangle:
            self._on = not self._on
            self.clippingToggled.emit(self._on)
            self.update()
            return
        z = self._zone_at(pos.x())
        if z and e.button() == QtCore.Qt.LeftButton:
            self._zone = z
            self._drag = (z[2], pos.x())
            self.dragStarted.emit(z[2])

    def set_clipping_on(self, on):
        self._on = on
        self.update()

    def clip_percent(self):
        return self._lo, self._hi


class LooksPanel(QtWidgets.QWidget):
    """Grouped list of Looks with thumbnails of the current photo; click to apply."""

    applyLook = QtCore.Signal(str)
    saveLook = QtCore.Signal()
    deleteLook = QtCore.Signal(str)
    importLooks = QtCore.Signal()
    exportLook = QtCore.Signal(str)  # look name ("" = the current settings)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 6)
        lay.setSpacing(4)
        self.list = QtWidgets.QListWidget()
        self.list.setObjectName("Looks")
        self.list.setIconSize(QtCore.QSize(54, 36))
        self.list.setUniformItemSizes(False)
        self.list.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.list.itemClicked.connect(self._clicked)
        self.list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.list)
        self._items: dict[str, QtWidgets.QListWidgetItem] = {}
        self._blank = self._blank_icon()
        self.user_looks: dict[str, dict] = {}

    def _blank_icon(self):
        pm = QtGui.QPixmap(54, 36)
        pm.fill(QtGui.QColor("#2a2a2d"))
        return QtGui.QIcon(pm)

    def populate(self, user_looks: dict):
        self.user_looks = dict(user_looks)
        self.list.clear()
        self._items.clear()
        groups = {c: [] for c in looks_mod.CATEGORIES}
        for name, (cat, desc, _) in looks_mod.LOOKS.items():
            groups[cat].append((name, desc))
        for name in sorted(self.user_looks, key=str.lower):
            src = (self.user_looks[name] or {}).get("_source")
            desc = trf("Imported {src}", src=tr(src)) if src else tr("Your saved look")
            groups["My Looks"].append((name, desc + tr(" — right-click to export or delete")))
        for cat in looks_mod.CATEGORIES:
            head = QtWidgets.QListWidgetItem(tr(cat).upper())
            head.setFlags(QtCore.Qt.NoItemFlags)
            f = head.font()
            f.setBold(True)
            f.setPointSizeF(7.5)
            head.setFont(f)
            head.setForeground(QtGui.QColor(theme.TEXT_DIM))
            self.list.addItem(head)
            if not groups[cat]:
                empty = QtWidgets.QListWidgetItem(tr("   Save your own, or right-click ▸ Import"))
                empty.setFlags(QtCore.Qt.NoItemFlags)
                empty.setForeground(QtGui.QColor(theme.TEXT_FAINT))
                self.list.addItem(empty)
            for name, desc in groups[cat]:
                it = QtWidgets.QListWidgetItem(self._blank, tr(name))  # shown translated; the look's key is the data
                it.setData(QtCore.Qt.UserRole, name)
                it.setToolTip(tr(desc))
                it.setSizeHint(QtCore.QSize(10, 42))
                self.list.addItem(it)
                self._items[name] = it

    def names(self):
        return list(self._items)

    def set_thumb(self, name, img):
        it = self._items.get(name)
        if it is not None:
            pm = QtGui.QPixmap.fromImage(to_qimage(img)).scaled(54, 36, QtCore.Qt.KeepAspectRatioByExpanding,
                                                                QtCore.Qt.SmoothTransformation)
            icon = QtGui.QIcon()
            for mode in (QtGui.QIcon.Normal, QtGui.QIcon.Selected, QtGui.QIcon.Active):
                icon.addPixmap(pm, mode)
            it.setIcon(icon)

    def clear_thumbs(self):
        for it in self._items.values():
            it.setIcon(self._blank)

    def set_current(self, name):
        self.list.blockSignals(True)
        self.list.clearSelection()
        it = self._items.get(name)
        if it is not None:
            it.setSelected(True)
        self.list.blockSignals(False)

    def _clicked(self, it):
        name = it.data(QtCore.Qt.UserRole)
        if name:
            self.applyLook.emit(name)

    def _menu(self, pos):
        self.build_menu(pos).exec(self.list.viewport().mapToGlobal(pos))

    def build_menu(self, pos) -> QtWidgets.QMenu:
        it = self.list.itemAt(pos)
        name = it.data(QtCore.Qt.UserRole) if it else None
        m = QtWidgets.QMenu(self)
        m.addAction(tr("Save current settings as a Look…")).triggered.connect(self.saveLook)
        m.addAction(tr("Import presets (.xmp, .lrtemplate, .cube)…")).triggered.connect(self.importLooks)
        m.addSeparator()
        if name:
            m.addAction(trf("Export “{name}” as a preset file…", name=tr(name))).triggered.connect(
                lambda: self.exportLook.emit(name))
        m.addAction(tr("Export current settings as a preset file…")).triggered.connect(lambda: self.exportLook.emit(""))
        if name in self.user_looks:
            m.addSeparator()
            m.addAction(trf("Delete “{name}”", name=name)).triggered.connect(lambda: self.deleteLook.emit(name))
        return m


class HistoryPanel(QtWidgets.QWidget):
    """Edit history of the current photo (newest first); click a step to go back to it."""

    jump = QtCore.Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 6)
        self.list = QtWidgets.QListWidget()
        self.list.setObjectName("History")
        self.list.itemClicked.connect(lambda it: self.jump.emit(int(it.data(QtCore.Qt.UserRole))))
        lay.addWidget(self.list)

    def set_entries(self, labels: list[str], current: int):
        self.list.blockSignals(True)
        self.list.clear()
        for i in range(len(labels) - 1, -1, -1):
            it = QtWidgets.QListWidgetItem(labels[i])
            it.setData(QtCore.Qt.UserRole, i)
            if i > current:
                it.setForeground(QtGui.QColor(theme.TEXT_FAINT))
            self.list.addItem(it)
            if i == current:
                it.setSelected(True)
        self.list.blockSignals(False)
