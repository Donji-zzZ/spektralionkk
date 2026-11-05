"""Image canvas.

* Zoom is tracked relative to the FULL-RESOLUTION photo (100% = one photo pixel per physical screen
  pixel), so draft/refined swaps and photo switches never change the apparent size.
* Modes: 'view' (pan/zoom), 'crop' (interactive crop rectangle on the uncropped frame), 'wb' (white
  balance picker).
* Before/After split with a draggable divider, clipping warning overlay, full-resolution detail tiles.
"""

from __future__ import annotations

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from ..i18n import tr, trf
from . import theme


def to_qimage(img: np.ndarray) -> QtGui.QImage:
    data = img if img.dtype == np.uint8 else (np.clip(img, 0, 1) * 255.0 + 0.5).astype(np.uint8)
    data = np.ascontiguousarray(data)
    h, w = data.shape[:2]
    return QtGui.QImage(data.data, w, h, 3 * w, QtGui.QImage.Format_RGB888).copy()


class StatusPill(QtWidgets.QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"background: rgba(16,16,17,215); color: {theme.TEXT}; border-radius: 10px; padding: 3px 10px;")
        self.hide()

    def show_text(self, text: str):
        if not text:
            self.hide()
            return
        self.setText(text)
        self.adjustSize()
        self.show()
        self.raise_()


HANDLES = ("tl", "t", "tr", "r", "br", "b", "bl", "l")


class Canvas(QtWidgets.QGraphicsView):
    zoomChanged = QtCore.Signal(str)
    viewChanged = QtCore.Signal(object)  # normalized visible rect of the pixmap (x, y, w, h) or None if fitted
    filesDropped = QtCore.Signal(list)
    detailWanted = QtCore.Signal(tuple)
    wbPicked = QtCore.Signal(float, float)  # normalized position in the photo
    cropChanged = QtCore.Signal(tuple)  # (l, t, r, b) normalized in the frame
    cropCommit = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QtWidgets.QGraphicsScene(self))
        self._orig = QtWidgets.QGraphicsPixmapItem()
        self._orig.setTransformationMode(QtCore.Qt.SmoothTransformation)
        self._orig.setVisible(False)
        self.scene().addItem(self._orig)
        self._clip = QtWidgets.QGraphicsRectItem()
        self._clip.setPen(QtGui.QPen(QtCore.Qt.NoPen))
        self._clip.setFlag(QtWidgets.QGraphicsItem.ItemClipsChildrenToShape, True)
        self.scene().addItem(self._clip)
        self._item = QtWidgets.QGraphicsPixmapItem(self._clip)
        self._item.setTransformationMode(QtCore.Qt.SmoothTransformation)
        # full-resolution detail: the quick view from the real-time tables underneath, the developed tile
        # (grain, halation, clarity) above it, so panning never takes the grain away from developed areas
        self._quick = QtWidgets.QGraphicsPixmapItem(self._clip)
        self._quick.setTransformationMode(QtCore.Qt.SmoothTransformation)
        self._quick.setZValue(0.9)
        self._detail = QtWidgets.QGraphicsPixmapItem(self._clip)
        self._detail.setTransformationMode(QtCore.Qt.SmoothTransformation)
        self._detail.setZValue(1)
        self._clipmask = QtWidgets.QGraphicsPixmapItem(self._clip)
        self._clipmask.setZValue(2)
        self.setBackgroundBrush(QtGui.QColor(theme.CANVAS))
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setRenderHints(QtGui.QPainter.SmoothPixmapTransform | QtGui.QPainter.Antialiasing)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.AnchorViewCenter)
        self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.FullViewportUpdate)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self._fit = True
        self._zoom = 1.0
        self._full = None
        self._inset = (0, 0, 1, 1)
        self._img = None  # current processed uint8 image (for clipping)
        self.mode = "view"
        self.split = False
        self.before = False
        self._divider = 0.5
        self._drag = None
        self._crop = (0.0, 0.0, 1.0, 1.0)
        self._crop_ratio = None  # aspect lock in pixel units (w/h) or None
        self.clipping = False
        self.status = StatusPill(self.viewport())
        self._placeholder = QtWidgets.QLabel(self.viewport())
        self._placeholder.setAlignment(QtCore.Qt.AlignCenter)
        self._placeholder.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 11pt;")
        self._placeholder.setText("Open photos or a folder to start\n\nCtrl+O  ·  Ctrl+Shift+O  ·  or drop files here\n\n"
                                  "RAW (NEF, CR2/CR3, ARW, RAF, DNG, …) · JPEG · TIFF · PNG · EXR")
        self._detail_timer = QtCore.QTimer(self, singleShot=True, interval=180)
        self._detail_timer.timeout.connect(self._maybe_detail)
        self.horizontalScrollBar().valueChanged.connect(lambda: self._view_changed())
        self.verticalScrollBar().valueChanged.connect(lambda: self._view_changed())

    # ------------------------------------------------------------------ geometry helpers
    def dpr(self) -> float:
        return self.devicePixelRatioF() or 1.0

    def target_long_edge(self) -> int:
        vp = self.viewport().rect()
        return int(max(vp.width(), vp.height()) * self.dpr())

    def _pm_size(self):
        pm = self._item.pixmap()
        return pm.width(), pm.height()

    def _view_scale(self) -> float:
        l, t, w, h = self._inset
        full_w = (self._full or (w, h))[0]
        return self._zoom * (full_w / max(w, 1)) / self.dpr()

    def _photo_center_norm(self):
        if not self.has_image():
            return None
        c = self.mapToScene(self.viewport().rect().center())
        l, t, w, h = self._inset
        return ((c.x() - l) / max(w, 1), (c.y() - t) / max(h, 1))

    def has_image(self):
        return not self._item.pixmap().isNull()

    # ------------------------------------------------------------------ content
    def reset_view(self):
        self._fit = True
        self._item.setPixmap(QtGui.QPixmap())
        self._img = None
        self.clear_detail()
        self._clipmask.setPixmap(QtGui.QPixmap())

    def set_image(self, img: np.ndarray | None, info: dict | None = None):
        if img is None:
            self.reset_view()
            self.set_original(None)
            self._placeholder.show()
            self.zoomChanged.emit("")
            self.viewChanged.emit(None)
            return
        self._placeholder.hide()
        center = self._photo_center_norm()
        info = info or {}
        h_img, w_img = img.shape[:2]
        if self.mode == "crop":
            self._inset = (0, 0, w_img, h_img)
            if info.get("frame_size"):
                self._full = tuple(info["frame_size"])
        else:
            self._inset = tuple(info.get("inset", (0, 0, w_img, h_img)))
            if info.get("crop_size"):
                self._full = tuple(info["crop_size"])
        self._img = img
        pm = QtGui.QPixmap.fromImage(to_qimage(img))
        self._item.setPixmap(pm)
        self._clip.setRect(self._clip_rect())
        self._fit_orig()
        # scene == photo: when zoomed in, panning stops at the photo's edges (smaller photos are centred)
        self.scene().setSceneRect(QtCore.QRectF(pm.rect()))
        if self._fit:
            self.fit()
        else:
            self._apply_zoom(center)
        self._update_clipmask()
        self.viewport().update()

    def current_image(self):
        return self._img

    # ------------------------------------------------------------------ before / after
    def set_original(self, img: np.ndarray | None):
        if img is None:
            self._orig.setPixmap(QtGui.QPixmap())
            return
        self._orig.setPixmap(QtGui.QPixmap.fromImage(to_qimage(img)))
        self._fit_orig()

    def _fit_orig(self):
        pm = self._orig.pixmap()
        w, h = self._pm_size()
        if not pm.isNull() and pm.width():
            self._orig.setTransform(QtGui.QTransform.fromScale(w / pm.width(), h / max(pm.height(), 1)))

    def set_split(self, on: bool):
        self.split = on
        self._orig.setVisible(on or self.before)
        self._clip.setRect(self._clip_rect())
        self.viewport().update()

    def set_before(self, on: bool):
        """Show the original photo in full (Lightroom's '\\' before view)."""
        self.before = on
        self._orig.setVisible(on or self.split)
        self._clip.setRect(self._clip_rect())
        self.viewport().update()

    def has_original(self):
        return not self._orig.pixmap().isNull()

    def _clip_rect(self):
        w, h = self._pm_size()
        if self.before and self.mode == "view" and self.has_original():
            return QtCore.QRectF(w + 20, 0, 0, 0)  # hide the processed image entirely
        if self.split and self.mode == "view":
            x = self._divider * w
            return QtCore.QRectF(x, -10, w - x + 10, h + 20)
        return QtCore.QRectF(-10, -10, w + 20, h + 20)

    # ------------------------------------------------------------------ clipping warning
    def set_clipping(self, on: bool):
        self.clipping = on
        self._update_clipmask()

    def _update_clipmask(self):
        if not self.clipping or self._img is None or self.mode != "view":
            self._clipmask.setPixmap(QtGui.QPixmap())
            return
        img = self._img
        hi = (img >= 254).any(axis=2)
        lo = (img <= 2).all(axis=2)
        rgba = np.zeros(img.shape[:2] + (4,), np.uint8)
        rgba[hi] = (255, 40, 40, 255)
        rgba[lo] = (40, 120, 255, 255)
        h, w = img.shape[:2]
        qi = QtGui.QImage(np.ascontiguousarray(rgba).data, w, h, 4 * w, QtGui.QImage.Format_RGBA8888).copy()
        self._clipmask.setPixmap(QtGui.QPixmap.fromImage(qi))

    # ------------------------------------------------------------------ detail tiles
    def clear_detail(self):
        for item in (self._detail, self._quick):
            item.setPixmap(QtGui.QPixmap())
            item.setVisible(False)

    def set_detail(self, tile: np.ndarray, box, full, developed: bool = True):
        """tile covers box = (x0, y0, x1, y1) in full-resolution pixels of the photo; below 100 % it has fewer
        pixels than the box (rendered at the screen's resolution). developed=False: the quick view, shown under
        the last developed tile until the developed version of this view arrives."""
        l, t, w, h = self._inset
        s = w / full[0]  # pixmap pixels per photo pixel
        x0, y0, x1, y1 = box
        item = self._detail if developed else self._quick
        item.setPixmap(QtGui.QPixmap.fromImage(to_qimage(tile)))
        item.setTransform(QtGui.QTransform.fromScale(s * (x1 - x0) / max(1, tile.shape[1]),
                                                     s * (y1 - y0) / max(1, tile.shape[0])))
        item.setPos(l + x0 * s, t + y0 * s)
        item.setVisible(True)
        if developed:  # it covers the whole view: the quick view underneath is no longer needed
            self._quick.setPixmap(QtGui.QPixmap())
            self._quick.setVisible(False)

    def wants_detail(self) -> bool:
        return (self.has_image() and not self._fit and self.mode == "view"
                and self._view_scale() * self.dpr() > 1.15)

    def detail_zoom(self) -> float:
        """Screen (device) pixels per photo pixel: detail tiles are rendered at min(this, 1) of full size."""
        return float(self._zoom)

    def visible_rect_norm(self):
        r = self.mapToScene(self.viewport().rect()).boundingRect()
        l, t, w, h = self._inset
        x0, y0 = max(0.0, (r.left() - l) / w), max(0.0, (r.top() - t) / h)
        x1, y1 = min(1.0, (r.right() - l) / w), min(1.0, (r.bottom() - t) / h)
        if x1 <= x0 or y1 <= y0:
            return None
        return (x0, y0, x1 - x0, y1 - y0)

    def _view_changed(self):
        if self.wants_detail():
            self._detail_timer.start()
        if not self.has_image():
            return
        if self._fit:
            self.viewChanged.emit(None)
            return
        r = self.mapToScene(self.viewport().rect()).boundingRect()
        w, h = self._pm_size()
        self.viewChanged.emit((r.left() / w, r.top() / h, r.width() / w, r.height() / h))

    def _maybe_detail(self):
        if self.wants_detail():
            r = self.visible_rect_norm()
            if r:
                self.detailWanted.emit(r)

    # ------------------------------------------------------------------ zoom
    def fit(self):
        self._fit = True
        if not self.has_image():
            return
        w, h = self._pm_size()
        vp = self.viewport().rect().adjusted(20, 20, -20, -20)
        s = min(vp.width() / max(w, 1), vp.height() / max(h, 1))
        self.setTransform(QtGui.QTransform.fromScale(s, s))
        il, it, iw, ih = self._inset
        full_w = (self._full or (iw, ih))[0]
        self._zoom = s * self.dpr() * iw / full_w
        self.centerOn(QtCore.QPointF(w / 2, h / 2))
        self.clear_detail()
        self._emit_zoom()
        self._view_changed()

    def fill(self):
        if not self.has_image():
            return
        w, h = self._pm_size()
        vp = self.viewport().rect()
        s = max(vp.width() / max(w, 1), vp.height() / max(h, 1))
        il, it, iw, ih = self._inset
        full_w = (self._full or (iw, ih))[0]
        self.set_zoom(s * self.dpr() * iw / full_w)

    def set_zoom(self, z: float, center=None):
        if not self.has_image() or self.mode == "crop":
            return
        if center is None:
            center = self._photo_center_norm()
        self._fit = False
        self._zoom = min(max(z, 0.02), 8.0)
        self._apply_zoom(center)

    def _apply_zoom(self, center_norm=None):
        s = self._view_scale()
        self.setTransform(QtGui.QTransform.fromScale(s, s))
        if center_norm is not None:
            l, t, w, h = self._inset
            self.centerOn(QtCore.QPointF(l + center_norm[0] * w, t + center_norm[1] * h))
        self._emit_zoom()
        self._view_changed()

    def zoom_by(self, factor: float):
        if not self.has_image() or self.mode == "crop":
            return
        self._fit = False
        self._zoom = min(max(self._zoom * factor, 0.02), 8.0)
        self.setTransform(QtGui.QTransform.fromScale(self._view_scale(), self._view_scale()))
        self._emit_zoom()
        self._view_changed()

    def zoom_actual(self, at: QtCore.QPointF | None = None):
        if not self.has_image() or self.mode == "crop":
            return
        center = self._photo_center_norm()
        if at is not None:
            sp = self.mapToScene(at.toPoint())
            l, t, w, h = self._inset
            center = ((sp.x() - l) / w, (sp.y() - t) / h)
        self.set_zoom(1.0, center)

    def center_on_norm(self, u: float, v: float):
        """Navigator: centre the view on (u, v) of the pixmap."""
        if not self.has_image():
            return
        if self._fit:
            self.set_zoom(1.0)
        w, h = self._pm_size()
        self.centerOn(QtCore.QPointF(u * w, v * h))
        self._view_changed()

    def _emit_zoom(self):
        if not self.has_image():
            self.zoomChanged.emit("")
            return
        pct = self._zoom * 100
        self.zoomChanged.emit(trf("Fit · {pct}%", pct=f"{pct:.0f}") if self._fit else f"{pct:.0f}%")

    def zoom_percent(self):
        return self._zoom * 100, self._fit

    # ------------------------------------------------------------------ modes
    def set_mode(self, mode: str):
        self.mode = mode
        self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag if mode == "view" else QtWidgets.QGraphicsView.NoDrag)
        self.viewport().setCursor(QtCore.Qt.CrossCursor if mode == "wb" else QtCore.Qt.ArrowCursor)
        if mode == "view":
            self.viewport().unsetCursor()
        self._clip.setRect(self._clip_rect())
        self._update_clipmask()
        if mode == "crop":
            self.clear_detail()
            self._fit = True
        self.viewport().update()

    def set_crop(self, rect, ratio):
        self._crop = tuple(rect)
        self._crop_ratio = ratio
        self.viewport().update()

    def crop_rect(self):
        return self._crop

    # ------------------------------------------------------------------ painting overlays
    def drawForeground(self, painter: QtGui.QPainter, rect):
        if not self.has_image():
            return
        w, h = self._pm_size()
        s = self._view_scale() if not self._fit else self.transform().m11()
        if self.mode == "crop":
            l, t, r, b = self._crop
            R = QtCore.QRectF(l * w, t * h, (r - l) * w, (b - t) * h)
            shade = QtGui.QColor(0, 0, 0, 150)
            full = QtCore.QRectF(0, 0, w, h)
            path = QtGui.QPainterPath()
            path.addRect(full)
            inner = QtGui.QPainterPath()
            inner.addRect(R)
            painter.fillPath(path.subtracted(inner), shade)
            pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 230))
            pen.setCosmetic(True)
            pen.setWidthF(1.2)
            painter.setPen(pen)
            painter.drawRect(R)
            pen.setColor(QtGui.QColor(255, 255, 255, 110))
            pen.setWidthF(0.8)
            painter.setPen(pen)
            for k in (1, 2):
                x = R.left() + R.width() * k / 3
                y = R.top() + R.height() * k / 3
                painter.drawLine(QtCore.QPointF(x, R.top()), QtCore.QPointF(x, R.bottom()))
                painter.drawLine(QtCore.QPointF(R.left(), y), QtCore.QPointF(R.right(), y))
            hs = 7 / max(s, 1e-6)
            painter.setBrush(QtGui.QColor(255, 255, 255))
            painter.setPen(QtCore.Qt.NoPen)
            for name, pt in self._handle_points(R).items():
                painter.drawRect(QtCore.QRectF(pt.x() - hs / 2, pt.y() - hs / 2, hs, hs))
        elif self.before and self.mode == "view":
            painter.save()
            painter.resetTransform()
            f = painter.font()
            f.setPointSizeF(8.5)
            f.setBold(True)
            painter.setFont(f)
            rr = QtCore.QRectF(12, 10, 70, 20)
            painter.setBrush(QtGui.QColor(16, 16, 17, 200))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRoundedRect(rr, 9, 9)
            painter.setPen(QtGui.QColor(theme.TEXT))
            painter.drawText(rr, QtCore.Qt.AlignCenter, tr("BEFORE"))
            painter.restore()
        elif self.split and self.mode == "view":
            x = self._divider * w
            pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 220))
            pen.setCosmetic(True)
            pen.setWidthF(1.5)
            painter.setPen(pen)
            painter.drawLine(QtCore.QPointF(x, 0), QtCore.QPointF(x, h))
            painter.save()
            painter.resetTransform()
            vx = self.mapFromScene(QtCore.QPointF(x, 0)).x()
            painter.setBrush(QtGui.QColor(16, 16, 17, 200))
            painter.setPen(QtCore.Qt.NoPen)
            f = painter.font()
            f.setPointSizeF(8.5)
            f.setBold(True)
            painter.setFont(f)
            for text, dx in (("BEFORE", -64), ("AFTER", 8)):
                rr = QtCore.QRectF(vx + dx, 10, 56, 20)
                painter.setBrush(QtGui.QColor(16, 16, 17, 200))
                painter.drawRoundedRect(rr, 9, 9)
                painter.setPen(QtGui.QColor(theme.TEXT))
                painter.drawText(rr, QtCore.Qt.AlignCenter, tr(text))
                painter.setPen(QtCore.Qt.NoPen)
            cy = self.viewport().height() / 2
            painter.setBrush(QtGui.QColor(255, 255, 255, 230))
            painter.drawEllipse(QtCore.QPointF(vx, cy), 9, 9)
            painter.setPen(QtGui.QColor(30, 30, 30))
            painter.drawText(QtCore.QRectF(vx - 9, cy - 9, 18, 18), QtCore.Qt.AlignCenter, "⇔")
            painter.restore()

    def _handle_points(self, R: QtCore.QRectF):
        cx, cy = R.center().x(), R.center().y()
        return {"tl": R.topLeft(), "t": QtCore.QPointF(cx, R.top()), "tr": R.topRight(),
                "r": QtCore.QPointF(R.right(), cy), "br": R.bottomRight(), "b": QtCore.QPointF(cx, R.bottom()),
                "bl": R.bottomLeft(), "l": QtCore.QPointF(R.left(), cy)}

    # ------------------------------------------------------------------ mouse
    def _scene_norm(self, pos):
        sp = self.mapToScene(pos)
        w, h = self._pm_size()
        return sp.x() / max(w, 1), sp.y() / max(h, 1), sp

    def mousePressEvent(self, e: QtGui.QMouseEvent):
        if not self.has_image():
            return super().mousePressEvent(e)
        pos = e.position().toPoint()
        if self.mode == "wb" and e.button() == QtCore.Qt.LeftButton:
            sp = self.mapToScene(pos)
            l, t, w, h = self._inset
            u, v = (sp.x() - l) / w, (sp.y() - t) / h
            if 0 <= u <= 1 and 0 <= v <= 1:
                self.wbPicked.emit(u, v)
            return
        if self.mode == "crop" and e.button() == QtCore.Qt.LeftButton:
            u, v, sp = self._scene_norm(pos)
            w, h = self._pm_size()
            l, t, r, b = self._crop
            R = QtCore.QRectF(l * w, t * h, (r - l) * w, (b - t) * h)
            tol = 10 / max(self.transform().m11(), 1e-6)
            hit = None
            for name, pt in self._handle_points(R).items():
                if abs(pt.x() - sp.x()) <= tol and abs(pt.y() - sp.y()) <= tol:
                    hit = name
                    break
            if hit is None and R.contains(sp):
                hit = "move"
            if hit is None:  # start a new rectangle from this corner
                self._crop = (u, v, u + 1e-3, v + 1e-3)
                hit = "br"
            self._drag = (hit, (u, v), self._crop)
            return
        if self.split and not self.before and self.mode == "view" and e.button() == QtCore.Qt.LeftButton:
            w, _ = self._pm_size()
            vx = self.mapFromScene(QtCore.QPointF(self._divider * w, 0)).x()
            if abs(pos.x() - vx) <= 10:
                self._drag = ("divider",)
                return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QtGui.QMouseEvent):
        pos = e.position().toPoint()
        if self._drag and self._drag[0] == "divider":
            u, _, _ = self._scene_norm(pos)
            self._divider = min(max(u, 0.0), 1.0)
            self._clip.setRect(self._clip_rect())
            self.viewport().update()
            return
        if self._drag and self.mode == "crop":
            u, v, _ = self._scene_norm(pos)
            self._crop = self._drag_crop(self._drag, min(max(u, 0), 1), min(max(v, 0), 1))
            self.viewport().update()
            return
        if self.mode == "crop" and self.has_image():
            _, _, sp = self._scene_norm(pos)
            w, h = self._pm_size()
            l, t, r, b = self._crop
            R = QtCore.QRectF(l * w, t * h, (r - l) * w, (b - t) * h)
            tol = 10 / max(self.transform().m11(), 1e-6)
            cur = QtCore.Qt.CrossCursor
            for name, pt in self._handle_points(R).items():
                if abs(pt.x() - sp.x()) <= tol and abs(pt.y() - sp.y()) <= tol:
                    cur = {"tl": QtCore.Qt.SizeFDiagCursor, "br": QtCore.Qt.SizeFDiagCursor,
                           "tr": QtCore.Qt.SizeBDiagCursor, "bl": QtCore.Qt.SizeBDiagCursor,
                           "t": QtCore.Qt.SizeVerCursor, "b": QtCore.Qt.SizeVerCursor,
                           "l": QtCore.Qt.SizeHorCursor, "r": QtCore.Qt.SizeHorCursor}[name]
                    break
            else:
                if R.contains(sp):
                    cur = QtCore.Qt.SizeAllCursor
            self.viewport().setCursor(cur)
        elif self.split and self.mode == "view" and self.has_image():
            w, _ = self._pm_size()
            vx = self.mapFromScene(QtCore.QPointF(self._divider * w, 0)).x()
            if abs(pos.x() - vx) <= 10:
                self.viewport().setCursor(QtCore.Qt.SplitHCursor)
            elif self.dragMode() == QtWidgets.QGraphicsView.ScrollHandDrag:
                self.viewport().unsetCursor()
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._drag:
            kind = self._drag[0]
            self._drag = None
            if kind != "divider" and self.mode == "crop":
                l, t, r, b = self._crop
                if r - l < 0.02 or b - t < 0.02:  # a click without dragging: keep the previous rectangle
                    self._crop = self._last_crop if hasattr(self, "_last_crop") else (0, 0, 1, 1)
                self._last_crop = self._crop
                self.cropChanged.emit(self._crop)
                self.viewport().update()
            return
        super().mouseReleaseEvent(e)

    def _drag_crop(self, drag, u, v):
        kind, (u0, v0), (l, t, r, b) = drag
        w, h = self._pm_size()
        if kind == "move":
            du, dv = u - u0, v - v0
            du = min(max(du, -l), 1 - r)
            dv = min(max(dv, -t), 1 - b)
            return (l + du, t + dv, r + du, b + dv)
        nl, nt, nr, nb = l, t, r, b
        if "l" in kind:
            nl = min(u, r - 0.02)
        if "r" in kind:
            nr = max(u, l + 0.02)
        if "t" in kind:
            nt = min(v, b - 0.02)
        if "b" in kind:
            nb = max(v, t + 0.02)
        ratio = self._crop_ratio
        if ratio:
            # keep the locked aspect: width drives height for corners / side handles, height for t/b
            pw, ph = (nr - nl) * w, (nb - nt) * h
            if kind in ("t", "b"):
                pw = ph * ratio
                cx = (nl + nr) / 2
                nl, nr = cx - pw / w / 2, cx + pw / w / 2
            else:
                ph = pw / ratio
                if "t" in kind:
                    nt = nb - ph / h
                elif "b" in kind or kind in ("l", "r"):
                    if kind in ("l", "r"):
                        cy = (nt + nb) / 2
                        nt, nb = cy - ph / h / 2, cy + ph / h / 2
                    else:
                        nb = nt + ph / h
            # stay inside the frame (shrink, keeping the ratio)
            if nl < 0 or nr > 1 or nt < 0 or nb > 1:
                return (l, t, r, b)
        return (max(nl, 0.0), max(nt, 0.0), min(nr, 1.0), min(nb, 1.0))

    def mouseDoubleClickEvent(self, e):
        if self.mode == "crop":
            self.cropCommit.emit()
            return
        if self.mode != "view":
            return
        if self._fit:
            self.zoom_actual(e.position())
        else:
            self.fit()

    def wheelEvent(self, e: QtGui.QWheelEvent):
        if self.mode == "crop":
            return
        d = e.angleDelta().y()
        if d:
            self.zoom_by(1.2 if d > 0 else 1 / 1.2)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._fit:
            self.fit()
        self._layout_overlays()

    def _layout_overlays(self):
        vp = self.viewport().rect()
        self.status.move(14, vp.bottom() - self.status.height() - 12)
        self._placeholder.setGeometry(vp)

    def set_status(self, text: str):
        self.status.show_text(text)
        self._layout_overlays()

    # -- drag & drop
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.filesDropped.emit(paths)
