"""Point tone-curve editor (master RGB and per-channel), Lightroom style.

Click to add a point, drag to move it, double-click or right-click a point to remove it.
"""

from __future__ import annotations

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from ..finish import curve_lut
from . import theme

CHANNELS = (("curve_master", "RGB", "#e6e4e1"), ("curve_r", "R", "#ff5a4a"), ("curve_g", "G", "#4ad27a"),
            ("curve_b", "B", "#4a8cff"))


class CurveCanvas(QtWidgets.QWidget):
    changed = QtCore.Signal(str, tuple, bool)  # field, points, final

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(220)
        self.setMouseTracking(True)
        self.curves = {f: ((0.0, 0.0), (1.0, 1.0)) for f, _, _ in CHANNELS}
        self.field = "curve_master"
        self._drag = None
        self._hover = None
        self._hist = None

    def set_curves(self, d: dict):
        self.curves.update({k: tuple(tuple(p) for p in v) for k, v in d.items()})
        self.update()

    def set_histogram(self, img):
        if img is None:
            self._hist = None
        else:
            sub = img[::4, ::4].reshape(-1, 3).mean(axis=1)
            h, _ = np.histogram(sub, bins=64, range=(0, 256))
            h = np.sqrt(h.astype(float))
            self._hist = h / max(h.max(), 1e-9)
        self.update()

    def _rect(self):
        return QtCore.QRectF(self.rect()).adjusted(8, 8, -8, -8)

    def _to_px(self, x, y):
        r = self._rect()
        return QtCore.QPointF(r.left() + x * r.width(), r.bottom() - y * r.height())

    def _from_px(self, p):
        r = self._rect()
        return (min(max((p.x() - r.left()) / r.width(), 0.0), 1.0),
                min(max((r.bottom() - p.y()) / r.height(), 0.0), 1.0))

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = self._rect()
        p.fillRect(self.rect(), QtGui.QColor("#141415"))
        if self._hist is not None:
            path = QtGui.QPainterPath(QtCore.QPointF(r.left(), r.bottom()))
            for i, v in enumerate(self._hist):
                path.lineTo(r.left() + r.width() * i / 63.0, r.bottom() - v * r.height() * 0.9)
            path.lineTo(r.right(), r.bottom())
            path.closeSubpath()
            p.fillPath(path, QtGui.QColor(255, 255, 255, 22))
        pen = QtGui.QPen(QtGui.QColor(theme.LINE), 1)
        p.setPen(pen)
        for k in range(1, 4):
            x = r.left() + r.width() * k / 4
            y = r.top() + r.height() * k / 4
            p.drawLine(QtCore.QPointF(x, r.top()), QtCore.QPointF(x, r.bottom()))
            p.drawLine(QtCore.QPointF(r.left(), y), QtCore.QPointF(r.right(), y))
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 40), 1, QtCore.Qt.DashLine))
        p.drawLine(r.bottomLeft(), r.topRight())
        for field, _, col in CHANNELS:  # other channels faintly
            if field == self.field or self.curves[field] == ((0.0, 0.0), (1.0, 1.0)):
                continue
            self._draw_curve(p, self.curves[field], QtGui.QColor(col), 0.35)
        col = dict((f, c) for f, _, c in CHANNELS)[self.field]
        self._draw_curve(p, self.curves[self.field], QtGui.QColor(col), 1.0)
        for i, (x, y) in enumerate(self.curves[self.field]):
            c = self._to_px(x, y)
            p.setPen(QtGui.QPen(QtGui.QColor(col), 1.5))
            p.setBrush(QtGui.QColor(theme.ACCENT) if i == self._hover else QtGui.QColor("#141415"))
            p.drawEllipse(c, 4.5, 4.5)

    def _draw_curve(self, p, pts, col, alpha):
        lut = curve_lut(pts, 256)
        col.setAlphaF(alpha)
        p.setPen(QtGui.QPen(col, 1.6))
        path = QtGui.QPainterPath(self._to_px(0, float(lut[0])))
        for i in range(1, 256):
            path.lineTo(self._to_px(i / 255.0, float(lut[i])))
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawPath(path)

    def _hit(self, pos):
        for i, (x, y) in enumerate(self.curves[self.field]):
            c = self._to_px(x, y)
            if abs(c.x() - pos.x()) < 8 and abs(c.y() - pos.y()) < 8:
                return i
        return None

    def mousePressEvent(self, e):
        pos = e.position()
        i = self._hit(pos)
        pts = list(self.curves[self.field])
        if e.button() == QtCore.Qt.RightButton:
            if i is not None and 0 < i < len(pts) - 1:
                pts.pop(i)
                self._commit(pts, True)
            return
        if i is None:  # add a point on the curve under the cursor
            x, y = self._from_px(pos)
            if 0.01 < x < 0.99:
                lut = curve_lut(pts, 1024)
                y = float(np.interp(x, np.linspace(0, 1, 1024), lut)) if abs(
                    self._to_px(x, float(np.interp(x, np.linspace(0, 1, 1024), lut))).y() - pos.y()) < 12 else y
                pts.append((x, y))
                pts.sort()
                i = pts.index((x, y))
                self._commit(pts, False)
        self._drag = i

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self._drag is None:
            h = self._hit(pos)
            if h != self._hover:
                self._hover = h
                self.update()
            return
        pts = list(self.curves[self.field])
        i = self._drag
        x, y = self._from_px(pos)
        if i == 0:
            x = 0.0 if pts[0][0] == 0.0 else min(x, pts[1][0] - 0.01)
        elif i == len(pts) - 1:
            x = 1.0 if pts[-1][0] == 1.0 else max(x, pts[-2][0] + 0.01)
        else:
            x = min(max(x, pts[i - 1][0] + 0.01), pts[i + 1][0] - 0.01)
        pts[i] = (round(x, 4), round(y, 4))
        self._commit(pts, False)

    def mouseReleaseEvent(self, e):
        if self._drag is not None:
            self._drag = None
            self._commit(list(self.curves[self.field]), True)

    def mouseDoubleClickEvent(self, e):
        i = self._hit(e.position())
        pts = list(self.curves[self.field])
        if i is not None and 0 < i < len(pts) - 1:
            pts.pop(i)
            self._drag = None
            self._commit(pts, True)

    def _commit(self, pts, final):
        self.curves[self.field] = tuple(pts)
        self.update()
        self.changed.emit(self.field, tuple(pts), final)


class CurveEditor(QtWidgets.QWidget):
    changed = QtCore.Signal(str, tuple, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        row = QtWidgets.QHBoxLayout()
        grp = QtWidgets.QButtonGroup(self)
        self.canvas = CurveCanvas()
        for field, label, col in CHANNELS:
            b = QtWidgets.QPushButton(label)
            b.setObjectName("Seg")
            b.setCheckable(True)
            b.setChecked(field == "curve_master")
            b.clicked.connect(lambda _=False, f=field: self._channel(f))
            grp.addButton(b)
            row.addWidget(b)
        row.addStretch(1)
        reset = QtWidgets.QToolButton()
        reset.setObjectName("Mini")
        reset.setText("Reset")
        reset.setToolTip("Reset this channel's curve")
        reset.clicked.connect(lambda: self.canvas._commit([(0.0, 0.0), (1.0, 1.0)], True))
        row.addWidget(reset)
        lay.addLayout(row)
        lay.addWidget(self.canvas)
        hint = QtWidgets.QLabel("Click to add a point · drag to move · double-click to remove")
        hint.setObjectName("Faint")
        lay.addWidget(hint)
        self.canvas.changed.connect(self.changed)

    def _channel(self, field):
        self.canvas.field = field
        self.canvas.update()

    def set_curves(self, d):
        self.canvas.set_curves(d)
