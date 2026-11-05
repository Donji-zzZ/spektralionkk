"""Reusable controls: collapsible sections, slider rows (linear / mired / hue), toggles, grouped combos."""

from __future__ import annotations

import math

from PySide6 import QtCore, QtGui, QtWidgets

from ..i18n import tr, trf
from . import theme


class Separator(QtWidgets.QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Separator")


class Section(QtWidgets.QWidget):
    """Collapsible titled panel with a header bar (Lightroom style) and an optional reset button."""

    resetRequested = QtCore.Signal()

    def __init__(self, title: str, *, collapsed=False, resettable=True, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        head = QtWidgets.QWidget()
        head.setObjectName("SectionHead")
        head.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        hl = QtWidgets.QHBoxLayout(head)
        hl.setContentsMargins(10, 0, 8, 0)
        hl.setSpacing(4)
        self._title = tr(title).replace("&", "&&")
        self._btn = QtWidgets.QPushButton()
        self._btn.setObjectName("SectionHeader")
        self._btn.setFlat(True)
        self._btn.setCursor(QtCore.Qt.PointingHandCursor)
        self._btn.clicked.connect(self.toggle)
        hl.addWidget(self._btn, 1)
        self.extra = QtWidgets.QHBoxLayout()
        self.extra.setSpacing(2)
        hl.addLayout(self.extra)
        if resettable:
            r = QtWidgets.QToolButton()
            r.setObjectName("Mini")
            r.setText("↺")
            r.setToolTip(trf("Reset {title}", title=tr(title)))
            r.clicked.connect(self.resetRequested)
            hl.addWidget(r)
        lay.addWidget(head)
        self.body = QtWidgets.QWidget()
        self.form = QtWidgets.QVBoxLayout(self.body)
        self.form.setContentsMargins(12, 8, 12, 10)
        self.form.setSpacing(5)
        lay.addWidget(self.body)
        self._collapsed = False
        self.set_collapsed(collapsed)

    def add_switch(self, tooltip: str = "") -> QtWidgets.QCheckBox:
        """An on/off switch in the header (e.g. Film Edge), visible even when the section is collapsed."""
        sw = QtWidgets.QCheckBox()
        sw.setObjectName("HeadSwitch")
        sw.setToolTip(tooltip)
        sw.setCursor(QtCore.Qt.PointingHandCursor)
        self.extra.addWidget(sw)
        return sw

    def toggle(self):
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, c: bool):
        self._collapsed = c
        self.body.setVisible(not c)
        self._btn.setText(("▸  " if c else "▾  ") + self._title)

    def is_collapsed(self):
        return self._collapsed

    def add(self, w):
        self.form.addWidget(w)
        return w

    def add_subhead(self, text):
        lab = QtWidgets.QLabel(text)
        lab.setObjectName("SubHead")
        self.form.addWidget(lab)
        return lab


HUE_GRADIENT = ("qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff3b3b, stop:0.17 #ffd23b, stop:0.33 #5bd94b, "
                "stop:0.5 #3bd9d9, stop:0.67 #3b6bff, stop:0.83 #c43bff, stop:1 #ff3b3b)")


class SliderRow(QtWidgets.QWidget):
    """Label | slider | value. Double-click the label to reset. Optional non-linear mapping."""

    valueChanged = QtCore.Signal(float)  # live while dragging
    committed = QtCore.Signal(float)  # on release / edit finished

    def __init__(self, label: str, lo: float, hi: float, *, step: float = 0.01, decimals: int = 2,
                 default: float = 0.0, sublabel: str = "", signed: bool | None = None, scale: float = 1.0,
                 tooltip: str = "", gradient=None, mapping: str = "linear", suffix: str = "", parent=None):
        super().__init__(parent)
        self._lo, self._hi, self._step = lo, hi, step
        self._default = default
        self._scale = scale
        self._signed = (lo < 0) if signed is None else signed
        self._decimals = decimals
        self._mapping = mapping  # 'linear' | 'mired' (Kelvin, even in perceived warmth)
        self._suffix = suffix
        self._block = False
        self._value = default
        grid = QtWidgets.QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(0)
        self.label = QtWidgets.QLabel(tr(label))
        self.label.setToolTip((tr(tooltip) + "\n" if tooltip else "") + tr("Double-click to reset"))
        self.label.mouseDoubleClickEvent = lambda e: self.reset()
        grid.addWidget(self.label, 0, 0)
        if sublabel:
            sub = QtWidgets.QLabel(tr(sublabel))
            sub.setObjectName("Faint")
            grid.addWidget(sub, 1, 0)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setPageStep(50)
        self.slider.setMinimumWidth(90)
        if gradient:
            bg = gradient if isinstance(gradient, str) else (
                f"qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {gradient[0]}, stop:0.5 #55555a, stop:1 {gradient[1]})")
            self.slider.setStyleSheet(
                f"QSlider::groove:horizontal {{ height: 3px; border-radius: 1px; background: {bg}; }}")
        grid.addWidget(self.slider, 0, 1, 2 if sublabel else 1, 1)
        self.box = QtWidgets.QLineEdit()
        self.box.setObjectName("Value")
        self.box.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.box.setFixedWidth(54)
        self.box.setFont(theme.tabular(self.box.font()))
        grid.addWidget(self.box, 0, 2, 2 if sublabel else 1, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnMinimumWidth(0, 86)
        self.slider.valueChanged.connect(self._from_slider)
        self.slider.sliderReleased.connect(lambda: self.committed.emit(self._value))
        self.box.editingFinished.connect(self._from_box)
        self.set_value(default)

    # mapping between value and slider position 0..1000
    def _to_pos(self, v):
        v = min(max(v, self._lo), self._hi)
        if self._mapping == "mired":
            m_lo, m_hi = 1e6 / self._lo, 1e6 / self._hi
            t = (m_lo - 1e6 / v) / (m_lo - m_hi)
        else:
            t = (v - self._lo) / (self._hi - self._lo)
        return int(round(t * 1000))

    def _from_pos(self, pos):
        t = pos / 1000.0
        if self._mapping == "mired":
            m_lo, m_hi = 1e6 / self._lo, 1e6 / self._hi
            v = 1e6 / (m_lo - t * (m_lo - m_hi))
        else:
            v = self._lo + t * (self._hi - self._lo)
        return round(round(v / self._step) * self._step, 6)

    def _show(self, v):
        shown = v * self._scale
        if self._signed:
            txt = f"{shown:+.{self._decimals}f}"
            if abs(shown) < 0.5 * 10 ** -self._decimals:
                txt = f"{0:.{self._decimals}f}"
        else:
            txt = f"{shown:.{self._decimals}f}"
        self.box.setText(txt + self._suffix)

    def _from_slider(self, pos):
        if self._block:
            return
        v = self._from_pos(pos)
        if v == self._value:
            return
        self._value = v
        self._show(v)
        self.valueChanged.emit(v)
        if not self.slider.isSliderDown():
            self.committed.emit(v)

    def _from_box(self):
        if self._block:
            return
        try:
            v = float(self.box.text().replace(self._suffix, "").replace(",", ".").replace("+", "")) / self._scale
        except ValueError:
            self._show(self._value)
            return
        v = min(max(v, self._lo), self._hi)
        if abs(v - self._value) < 1e-12:
            self._show(v)
            return
        self.set_value(v)
        self.valueChanged.emit(v)
        self.committed.emit(v)

    def value(self) -> float:
        return self._value

    def set_value(self, v: float):
        self._block = True
        self._value = float(v)
        self.slider.setValue(self._to_pos(float(v)))
        self._show(float(v))
        self._block = False

    def reset(self):
        self.set_value(self._default)
        self.valueChanged.emit(self._default)
        self.committed.emit(self._default)

    def set_enabled(self, on: bool):
        for w in (self.slider, self.box, self.label):
            w.setEnabled(on)

    def setEnabled(self, on: bool):  # noqa: N802
        self.set_enabled(on)


class ToggleRow(QtWidgets.QWidget):
    toggled = QtCore.Signal(bool)

    def __init__(self, label: str, sublabel: str = "", tooltip: str = "", parent=None):
        super().__init__(parent)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        col = QtWidgets.QVBoxLayout()
        col.setSpacing(0)
        self.label = QtWidgets.QLabel(tr(label))
        self.label.setToolTip(tr(tooltip))
        col.addWidget(self.label)
        if sublabel:
            s = QtWidgets.QLabel(tr(sublabel))
            s.setObjectName("Faint")
            s.setWordWrap(True)
            col.addWidget(s)
        lay.addLayout(col, 1)
        self.box = QtWidgets.QCheckBox()
        self.box.toggled.connect(self.toggled)
        lay.addWidget(self.box)

    def set_value(self, v: bool):
        self.box.blockSignals(True)
        self.box.setChecked(bool(v))
        self.box.blockSignals(False)

    def value(self) -> bool:
        return self.box.isChecked()


class TextRow(QtWidgets.QWidget):
    """Label + one-line text field; emits when editing finishes (Enter / focus out)."""

    changed = QtCore.Signal(str)

    def __init__(self, label: str, placeholder: str = "", tooltip: str = "", max_len: int = 40, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.label = QtWidgets.QLabel(tr(label))
        self.label.setToolTip(tr(tooltip))
        self.label.setMinimumWidth(86)
        lay.addWidget(self.label)
        self.edit = QtWidgets.QLineEdit()
        self.edit.setPlaceholderText(tr(placeholder))
        self.edit.setToolTip(tr(tooltip))
        self.edit.setMaxLength(max_len)
        self.edit.setClearButtonEnabled(True)
        self._last = ""
        self.edit.editingFinished.connect(self._finished)
        lay.addWidget(self.edit, 1)

    def _finished(self):
        t = self.edit.text().strip()
        if t != self._last:
            self._last = t
            self.changed.emit(t)

    def set_value(self, v):
        self._last = str(v or "")
        self.edit.blockSignals(True)
        self.edit.setText(self._last)
        self.edit.blockSignals(False)

    def value(self) -> str:
        return self.edit.text().strip()

    def setEnabled(self, on: bool):  # noqa: N802
        self.edit.setEnabled(on)
        self.label.setEnabled(on)


class ComboRow(QtWidgets.QWidget):
    """Label + combo box. items: list of values, or list of (group title, [(value, label), ...])."""

    changed = QtCore.Signal(object)

    def __init__(self, label: str, items, labels=None, tooltip: str = "", parent=None):
        super().__init__(parent)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.label = QtWidgets.QLabel(tr(label))
        self.label.setToolTip(tr(tooltip))
        self.label.setMinimumWidth(86)
        lay.addWidget(self.label)
        self.combo = QtWidgets.QComboBox()
        self.combo.setMaxVisibleItems(30)
        # don't let long stock names widen the whole panel
        self.combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo.setMinimumContentsLength(8)
        self.combo.view().setMinimumWidth(260)
        model = QtGui.QStandardItemModel(self.combo)
        if items and isinstance(items[0], tuple) and isinstance(items[0][1], list):
            for title, entries in items:
                head = QtGui.QStandardItem(tr(title).upper())
                head.setFlags(QtCore.Qt.NoItemFlags)
                f = head.font()
                f.setBold(True)
                f.setPointSizeF(7.5)
                head.setFont(f)
                head.setForeground(QtGui.QBrush(QtGui.QColor(theme.TEXT_DIM)))
                model.appendRow(head)
                for value, text in entries:
                    it = QtGui.QStandardItem("   " + tr(text))
                    it.setData(value, QtCore.Qt.UserRole)
                    model.appendRow(it)
        else:
            for i, it in enumerate(items):
                si = QtGui.QStandardItem(tr(labels[i]) if labels else tr(str(it).replace("_", " ").capitalize()))
                si.setData(it, QtCore.Qt.UserRole)
                model.appendRow(si)
        self.combo.setModel(model)
        self.combo.currentIndexChanged.connect(self._changed)
        lay.addWidget(self.combo, 1)

    def _changed(self, i):
        v = self.combo.itemData(i, QtCore.Qt.UserRole)
        if v is not None:
            self.changed.emit(v)

    def set_value(self, v):
        for i in range(self.combo.count()):
            if self.combo.itemData(i, QtCore.Qt.UserRole) == v:
                self.combo.blockSignals(True)
                self.combo.setCurrentIndex(i)
                self.combo.blockSignals(False)
                return

    def value(self):
        return self.combo.currentData(QtCore.Qt.UserRole)

    def setEnabled(self, on: bool):  # noqa: N802
        self.combo.setEnabled(on)
        self.label.setEnabled(on)
