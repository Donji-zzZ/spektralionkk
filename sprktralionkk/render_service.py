"""Background rendering.

* live worker: real-time previews from baked lookup tables (see live.py) — every slider move.
* main worker: refined previews (draft / fine) with grain, halation and the other spatial effects,
  crop-tool frames, 1:1 detail tiles, then — only when idle — Look thumbnails. Latest request wins;
  stale work is cancelled between stages, and nothing heavy starts while a slider is being dragged.
* aux worker: cheap jobs that must never wait behind a film render (Original view, WB eyedropper).
* prefetch worker: decodes neighbouring photos.
"""

from __future__ import annotations

import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

from PySide6 import QtCore

from .engine import Engine, RenderCancelled, configure_thread
from .settings import DevelopSettings


class RenderService(QtCore.QObject):
    rendered = QtCore.Signal(int, str, str, object, float, object)  # gen, path, kind, uint8 img, secs, info
    originalReady = QtCore.Signal(str, object, object)  # path, uint8 img, request key
    wbSampled = QtCore.Signal(str, float, float)
    thumbReady = QtCore.Signal(str, str, object)  # path, look name, uint8 img
    stripThumbReady = QtCore.Signal(str, object)  # path, uint8 img (processed filmstrip thumbnail)
    failed = QtCore.Signal(int, str, str)
    busy = QtCore.Signal(str)
    engineReady = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        from .live import LivePreview

        self.engine = Engine()
        self.live = LivePreview(self.engine)
        self._cv = threading.Condition()
        self._pending = None
        self._detail = None
        self._thumbs: list = []
        self._thumb_epoch = 0
        self._strip: dict = {}  # path -> settings: filmstrip thumbnails to refresh when idle
        self._gen = 0
        self._stop = False
        self._ready = threading.Event()
        self._lcv = threading.Condition()
        self._live_job = None
        self._live_until = 0.0  # no idle-time work (Look thumbnails) before this time: the user is editing
        self._aux = ThreadPoolExecutor(max_workers=1, initializer=configure_thread)
        self._prefetch = ThreadPoolExecutor(max_workers=1, initializer=configure_thread)
        self._thread = threading.Thread(target=self._run, name="render", daemon=True)
        self._thread.start()
        self._lthread = threading.Thread(target=self._run_live, name="live", daemon=True)
        self._lthread.start()

    # -- requests
    def request_live(self, path: str, s: DevelopSettings, size: int, *, dragging: bool = False,
                     uncropped: bool = False) -> int:
        """Real-time preview (~10-150 ms). Starts a new generation, so any refine in flight is dropped."""
        with self._cv:
            self._gen += 1
            self._detail = None
            if self._pending is not None and self._pending[0] != self._gen:
                self._pending = None
            gen = self._gen
            self._live_until = time.monotonic() + (1.5 if dragging else 0.6)
        with self._lcv:
            self._live_job = (gen, path, s.copy(), int(size), bool(dragging), bool(uncropped))
            self._lcv.notify()
        return gen

    def request(self, path: str, s: DevelopSettings, kind: str, *, new_gen: bool = True, long_edge: int = 1400) -> int:
        """kind: 'draft' | 'fine' | 'crop_draft' | 'crop_fine'"""
        with self._cv:
            if new_gen:
                self._gen += 1
                self._detail = None
            self._pending = (self._gen, path, s.copy(), kind, long_edge)
            self._cv.notify()
            return self._gen

    def request_detail(self, path: str, s: DevelopSettings, rect) -> None:
        with self._cv:
            self._detail = (self._gen, path, s.copy(), "detail", rect)
            self._cv.notify()

    def request_thumbs(self, path: str, jobs: list) -> None:
        """jobs: [(look name, DevelopSettings)] rendered at thumbnail size when the worker is idle."""
        with self._cv:
            self._thumb_epoch += 1
            self._thumbs = [(path, name, s.copy()) for name, s in jobs]
            self._cv.notify()

    def cancel_thumbs(self):
        with self._cv:
            self._thumb_epoch += 1
            self._thumbs = []

    def request_strip_thumbs(self, jobs: list) -> None:
        """jobs: [(path, DevelopSettings)] — processed filmstrip thumbnails, rendered when idle."""
        with self._cv:
            for path, s in jobs:
                self._strip.pop(path, None)
                self._strip[path] = s.copy()
            self._cv.notify()

    def request_original(self, path: str, s: DevelopSettings, long_edge: int, key) -> None:
        s = s.copy()

        def job():
            try:
                img = self.engine.original_display(path, s, long_edge)
                self.originalReady.emit(path, img, key)
            except Exception as exc:
                traceback.print_exc()
                self.failed.emit(-1, path, f"Original view: {exc}")

        self._aux.submit(job)

    def request_wb_sample(self, path: str, s: DevelopSettings, u: float, v: float) -> None:
        s = s.copy()

        def job():
            try:
                T, tint = self.engine.sample_wb(path, s, u, v)
                self.wbSampled.emit(path, T, tint)
            except Exception as exc:
                traceback.print_exc()
                self.failed.emit(-1, path, f"White balance picker: {exc}")

        self._aux.submit(job)

    def prefetch(self, path: str, s: DevelopSettings):
        self._prefetch.submit(self.engine.prefetch, path, s.copy())

    @property
    def generation(self) -> int:
        return self._gen

    def stop(self):
        with self._cv:
            self._stop = True
            self._cv.notify()
        with self._lcv:
            self._lcv.notify()
        self._ready.set()

    def _stale(self, gen):
        return (self._pending is not None and self._pending[0] != gen) or self._gen != gen

    def _editing(self):
        return time.monotonic() < self._live_until

    # -- workers
    def _run(self):
        configure_thread()
        self.busy.emit("Preparing film engine…")
        try:
            from spektrafilm.utils.numba_warmup import warmup

            warmup()
        except Exception:
            traceback.print_exc()
        try:
            from .live import warmup as live_warmup

            live_warmup()  # compile (or load from cache) the real-time kernel
            from . import fastprint, grainfast

            fastprint.warmup()  # ... and the full-resolution print table and grain kernels
            grainfast.warmup()
        except Exception:
            traceback.print_exc()
        self._ready.set()
        self.busy.emit("")
        self.engineReady.emit()
        while True:
            with self._cv:
                while not self._stop and self._pending is None and self._detail is None:
                    idle_work = bool(self._thumbs or self._strip)
                    if idle_work and not self._editing():
                        break
                    # Look and filmstrip thumbnails wait until the user stops editing
                    self._cv.wait(max(0.05, self._live_until - time.monotonic()) if idle_work else None)
                if self._stop:
                    return
                if self._pending is not None:
                    job, self._pending = self._pending, None
                elif self._detail is not None:
                    job, self._detail = self._detail, None
                elif self._thumbs:
                    job = ("thumb", self._thumb_epoch) + self._thumbs.pop(0)
                else:
                    path = next(iter(self._strip))
                    job = ("strip", path, self._strip.pop(path))
            if job[0] == "thumb":
                self._run_thumb(*job[1:])
                continue
            if job[0] == "strip":
                self._run_strip(*job[1:])
                continue
            gen, path, s, kind, arg = job
            cancel = lambda: self._stale(gen)  # noqa: E731
            if cancel():
                continue
            self.busy.emit({"draft": "Developing…", "fine": "Refining…", "crop_draft": "Developing…",
                            "crop_fine": "Refining…", "detail": "Rendering full-resolution detail…"}.get(kind, "…"))
            t0 = time.perf_counter()
            try:
                info = {}
                if kind == "detail":
                    res = self.engine.detail(path, s, arg, cancel)
                    if res is None:
                        raise RenderCancelled
                    img, box, full = res
                    info = {"box": box, "full": full, "rect": arg}
                elif kind.startswith("crop_"):
                    img = self.engine.render_uncropped(path, s, kind[5:], arg, cancel)
                    info = dict(self.engine.last_info)
                else:
                    img = self.engine.render(path, s, kind, arg, cancel)
                    info = dict(self.engine.last_info)
                if not cancel():
                    self.rendered.emit(gen, path, kind, img, time.perf_counter() - t0, info)
            except RenderCancelled:
                pass
            except MemoryError:
                self.failed.emit(gen, path, "Not enough memory for this operation.")
            except Exception as exc:
                traceback.print_exc()
                self.failed.emit(gen, path, f"{type(exc).__name__}: {exc}")
            with self._cv:
                idle = self._pending is None and self._detail is None
            if idle:
                self.busy.emit("")

    def _run_thumb(self, epoch, path, name, s):
        try:
            img = self.engine.render(path, s, "thumb", cancel=self._editing)
            self.thumbReady.emit(path, name, img)
        except RenderCancelled:  # the user started editing: try again when they stop
            with self._cv:
                if epoch == self._thumb_epoch:
                    self._thumbs.insert(0, (path, name, s))
        except Exception:
            traceback.print_exc()

    def _run_strip(self, path, s):
        try:
            img = self.engine.strip_thumb(path, s, cancel=self._editing)
            self.stripThumbReady.emit(path, img)
        except RenderCancelled:
            with self._cv:
                if path not in self._strip:
                    self._strip = {path: s, **self._strip}
        except Exception:
            traceback.print_exc()

    def _run_live(self):
        configure_thread()
        self._ready.wait()
        while True:
            with self._lcv:
                while self._live_job is None and not self._stop:
                    self._lcv.wait()
                if self._stop:
                    return
                job, self._live_job = self._live_job, None
            gen, path, s, size, dragging, uncropped = job
            if gen != self._gen:
                continue
            t0 = time.perf_counter()
            try:
                img = self.live.render(path, s, size, dragging=dragging, uncropped=uncropped,
                                       cancel=lambda: self._gen != gen)
                if gen == self._gen:
                    self.rendered.emit(gen, path, "crop_live" if uncropped else "live", img,
                                       time.perf_counter() - t0, dict(self.live.last_info))
            except RenderCancelled:
                pass
            except Exception:  # anything the tables can't do: fall back to the regular preview
                traceback.print_exc()
                with self._cv:
                    if gen == self._gen:
                        self._pending = (gen, path, s, "crop_draft" if uncropped else "draft", size)
                        self._cv.notify()
