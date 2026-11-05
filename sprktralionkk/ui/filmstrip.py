"""Bottom filmstrip of thumbnails (multi-select for sync and batch export)."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from .. import engine
from ..i18n import tr, trf
from .canvas import to_qimage

THUMB = 132
PATH_ROLE = QtCore.Qt.UserRole
PROCESSED_ROLE = QtCore.Qt.UserRole + 1
RATING_ROLE = QtCore.Qt.UserRole + 2
FLAG_ROLE = QtCore.Qt.UserRole + 3
EDITED_ROLE = QtCore.Qt.UserRole + 4

FILTERS = [("all", "All photos"), ("picks", "Picks only"), ("unrejected", "Hide rejects"),
           ("1", "Rated ★ or more"), ("3", "Rated ★★★ or more"), ("5", "Rated ★★★★★")]


class _ThumbSignals(QtCore.QObject):
    ready = QtCore.Signal(str, QtGui.QImage)


class _Overlay(QtWidgets.QStyledItemDelegate):
    """Thumbnail plus Lightroom-style badges: stars, pick / reject flag, edited dot."""

    def paint(self, p, opt, idx):
        super().paint(p, opt, idx)
        r = QtCore.QRectF(opt.rect).adjusted(5, 4, -5, -4)
        rating = int(idx.data(RATING_ROLE) or 0)
        flag = idx.data(FLAG_ROLE) or ""
        p.save()
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        if flag == "reject":
            p.fillRect(opt.rect, QtGui.QColor(10, 10, 11, 150))
        f = QtGui.QFont(opt.font)
        f.setPointSizeF(7.5)
        p.setFont(f)
        fm = QtGui.QFontMetricsF(f)
        if rating:
            txt = "★" * rating
            pill = QtCore.QRectF(r.left(), r.bottom() - fm.height() - 3, fm.horizontalAdvance(txt) + 8, fm.height() + 3)
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor(0, 0, 0, 160))
            p.drawRoundedRect(pill, 3, 3)
            p.setPen(QtGui.QColor("#f2c94c"))
            p.drawText(pill, QtCore.Qt.AlignCenter, txt)
        if flag:
            badge = QtCore.QRectF(r.right() - 17, r.top(), 17, 16)
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor(0, 0, 0, 160))
            p.drawRoundedRect(badge, 3, 3)
            c = badge.center()
            P = QtCore.QPointF
            if flag == "pick":  # white flag
                p.setBrush(QtGui.QColor("#ffffff"))
                p.drawRect(QtCore.QRectF(c.x() - 4, c.y() - 5, 1.5, 10.5))
                p.drawPolygon(QtGui.QPolygonF([P(c.x() - 2.5, c.y() - 5), P(c.x() + 5, c.y() - 2.4),
                                               P(c.x() - 2.5, c.y() + 0.6)]))
            else:  # red cross
                pen = QtGui.QPen(QtGui.QColor("#ff5a4a"), 2.0)
                pen.setCapStyle(QtCore.Qt.RoundCap)
                p.setPen(pen)
                p.drawLine(c + P(-3.5, -3.5), c + P(3.5, 3.5))
                p.drawLine(c + P(-3.5, 3.5), c + P(3.5, -3.5))
        if idx.data(EDITED_ROLE):
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor("#e4573d"))
            p.drawEllipse(QtCore.QPointF(r.left() + 5, r.top() + 5), 3, 3)
        p.restore()


class Filmstrip(QtWidgets.QWidget):
    currentChanged = QtCore.Signal(str)
    selectionChanged = QtCore.Signal(list)
    filesDropped = QtCore.Signal(list)
    removeRequested = QtCore.Signal(list)
    action = QtCore.Signal(str, list, object)  # action, photos, argument (see _menu)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Filmstrip")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        self.list = QtWidgets.QListWidget()
        self.list.setObjectName("Strip")
        self.list.setViewMode(QtWidgets.QListView.IconMode)
        self.list.setFlow(QtWidgets.QListView.LeftToRight)
        self.list.setWrapping(False)
        self.list.setMovement(QtWidgets.QListView.Static)
        self.list.setIconSize(QtCore.QSize(THUMB, int(THUMB * 0.7)))
        self.list.setSpacing(2)
        self.list.setUniformItemSizes(True)
        self.list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.list.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.list.setFixedHeight(int(THUMB * 0.7) + 42)
        self.list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        self.list.currentItemChanged.connect(self._current)
        self.list.itemSelectionChanged.connect(lambda: self.selectionChanged.emit(self.selected_paths()))
        self.list.setAcceptDrops(True)
        self.list.viewport().setAcceptDrops(True)
        self.list.dragEnterEvent = self._drag_enter
        self.list.dragMoveEvent = self._drag_enter
        self.list.dropEvent = self._drop
        self.list.setItemDelegate(_Overlay(self.list))
        lay.addWidget(self.list)
        self._items: dict[str, QtWidgets.QListWidgetItem] = {}
        self._pool = ThreadPoolExecutor(max_workers=2)
        self._sig = _ThumbSignals()
        self._sig.ready.connect(self._thumb_ready)
        self._placeholder = self._make_placeholder()
        self.filter = "all"
        self.look_groups = lambda: []  # set by the window: [(category, [look names])]
        self.can_paste = lambda: False

    def _make_placeholder(self):
        pm = QtGui.QPixmap(THUMB, int(THUMB * 0.7))
        pm.fill(QtGui.QColor("#2a2a2d"))
        return QtGui.QIcon(pm)

    # -- items
    def set_paths(self, paths: list[str]):
        self.list.clear()
        self._items.clear()
        for p in paths:
            self._add(p)

    def add_paths(self, paths: list[str]):
        for p in paths:
            if p not in self._items:
                self._add(p)

    def _add(self, path):
        it = QtWidgets.QListWidgetItem(self._placeholder, "")
        it.setData(QtCore.Qt.UserRole, path)
        it.setToolTip(os.path.basename(path))
        it.setSizeHint(QtCore.QSize(THUMB + 8, int(THUMB * 0.7) + 10))
        self.list.addItem(it)
        self._items[path] = it
        self._pool.submit(self._load_thumb, path)

    def remove_paths(self, paths):
        for p in paths:
            it = self._items.pop(p, None)
            if it is not None:
                self.list.takeItem(self.list.row(it))

    def _load_thumb(self, path):
        arr = engine.thumbnail(path, THUMB * 2)
        if arr is not None:
            self._sig.ready.emit(path, to_qimage(arr.astype(np.float32) / 255.0))

    @staticmethod
    def _icon(qimg) -> QtGui.QIcon:
        # same pixmap for every mode, so Qt doesn't tint selected thumbnails
        pm = QtGui.QPixmap.fromImage(qimg)
        icon = QtGui.QIcon()
        for mode in (QtGui.QIcon.Normal, QtGui.QIcon.Selected, QtGui.QIcon.Active):
            icon.addPixmap(pm, mode)
        return icon

    def _thumb_ready(self, path, qimg):
        it = self._items.get(path)
        if it is not None and not it.data(QtCore.Qt.UserRole + 1):
            it.setIcon(self._icon(qimg))

    def set_processed_thumb(self, path, rgb: np.ndarray):
        it = self._items.get(path)
        if it is None:
            return
        qimg = to_qimage(rgb).scaled(THUMB * 2, THUMB * 2, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        it.setIcon(self._icon(qimg))
        it.setData(PROCESSED_ROLE, True)  # processed: don't overwrite with the camera thumb

    def set_meta(self, path, rating: int = 0, flag: str = "", edited: bool = False):
        it = self._items.get(path)
        if it is None:
            return
        it.setData(RATING_ROLE, int(rating))
        it.setData(FLAG_ROLE, flag or "")
        it.setData(EDITED_ROLE, bool(edited))
        tip = [os.path.basename(path)]
        if rating:
            tip.append("★" * rating)
        if flag:
            tip.append(tr("Pick" if flag == "pick" else "Rejected"))
        it.setToolTip("   ".join(tip))
        self._apply_filter_to(it)

    def set_filter(self, key):
        self.filter = key
        for it in self._items.values():
            self._apply_filter_to(it)
        cur = self.list.currentItem()
        if cur is not None and not cur.isHidden():
            self.list.scrollToItem(cur)

    def _apply_filter_to(self, it):
        k = self.filter
        rating, flag = int(it.data(RATING_ROLE) or 0), it.data(FLAG_ROLE) or ""
        show = (k == "all" or (k == "picks" and flag == "pick") or (k == "unrejected" and flag != "reject")
                or (k.isdigit() and rating >= int(k)))
        # never hide the photo being edited
        it.setHidden(not show and it is not self.list.currentItem())

    def visible_paths(self):
        return [p for p, it in self._items.items() if not it.isHidden()]

    # -- selection
    def paths(self):
        return [self.list.item(i).data(QtCore.Qt.UserRole) for i in range(self.list.count())]

    def selected_paths(self):
        return [it.data(QtCore.Qt.UserRole) for it in self.list.selectedItems()]

    def current_path(self):
        it = self.list.currentItem()
        return it.data(QtCore.Qt.UserRole) if it else None

    def set_current(self, path):
        it = self._items.get(path)
        if it is not None:
            self.list.setCurrentItem(it)
            self.list.scrollToItem(it)

    def step(self, delta: int):
        n = self.list.count()
        if not n:
            return
        row = self.list.currentRow()
        for _ in range(n):  # skip photos hidden by the filter
            row = (row + delta) % n
            if not self.list.item(row).isHidden():
                break
        self.list.setCurrentRow(row)

    def select_all(self):
        self.list.selectAll()

    def _current(self, cur, prev):
        if cur is not None:
            self.currentChanged.emit(cur.data(QtCore.Qt.UserRole))

    def _menu(self, pos):
        self.build_menu(pos).exec(self.list.viewport().mapToGlobal(pos))

    def build_menu(self, pos) -> QtWidgets.QMenu:
        it = self.list.itemAt(pos)
        if it is not None and not it.isSelected():
            self.list.setCurrentItem(it)
        sel = self.selected_paths()
        m = QtWidgets.QMenu(self)
        if sel:
            n = len(sel)
            many = trf(" ({n} photos)", n=n) if n > 1 else ""

            def add(menu, text, action, arg=None, shortcut=None, suffix=""):
                a = menu.addAction(tr(text) + suffix)
                if shortcut:
                    a.setShortcut(QtGui.QKeySequence(shortcut))
                a.triggered.connect(lambda: self.action.emit(action, sel, arg))
                return a

            cur_rating = int(self._items[sel[0]].data(RATING_ROLE) or 0)
            rm = m.addMenu(tr("Rating") + many)
            for k in range(6):
                a = add(rm, "No stars" if k == 0 else "★" * k, "rate", k, str(k))
                a.setCheckable(True)
                a.setChecked(n == 1 and k == cur_rating)
            fm = m.addMenu(tr("Flag") + many)
            add(fm, "⚑  Pick", "flag", "pick", "P")
            add(fm, "✕  Reject", "flag", "reject", "X")
            add(fm, "Unflag", "flag", "", "U")
            m.addSeparator()
            lm = m.addMenu(tr("Apply Look") + many)
            for cat, names in self.look_groups():
                if not names:
                    continue
                sub = lm.addMenu(tr(cat))
                for name in names:
                    a = sub.addAction(tr(name).replace("&", "&&"))
                    a.triggered.connect(lambda _=False, nm=name: self.action.emit("look", sel, nm))
            add(m, "Copy Settings from This Photo", "copy").setEnabled(n == 1)
            add(m, "Paste Settings", "paste", suffix=many).setEnabled(self.can_paste())
            add(m, "Sync Settings from the Open Photo…", "sync").setEnabled(n > 1)
            add(m, "Reset Settings", "reset", suffix=many)
            m.addSeparator()
            add(m, "Rotate Left", "rotl", suffix=many)
            add(m, "Rotate Right", "rotr", suffix=many)
            m.addSeparator()
            add(m, "Export", "export", suffix=many + "…")
            m.addSeparator()
            add(m, "Show in Explorer", "explorer")
            add(m, "Open in Default App", "open").setEnabled(n == 1)
            add(m, "Copy File Path", "copy_path")
            m.addSeparator()
            add(m, "Remove from Library", "remove", suffix=many)
            m.addSeparator()
        fl = m.addMenu(tr("Show"))
        for key, label in FILTERS:
            a = fl.addAction(tr(label))
            a.setCheckable(True)
            a.setChecked(key == self.filter)
            a.triggered.connect(lambda _=False, k=key: self.action.emit("filter", [], k))
        return m

    def _drag_enter(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def _drop(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.filesDropped.emit(paths)
