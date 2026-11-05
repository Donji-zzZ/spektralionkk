"""Keep numba safe when the app renders on several threads at once.

The live preview, the refined preview, filmstrip thumbnails and exports run on their own threads. numba's omp
and tbb threading layers let them launch parallel kernels at the same time; its workqueue layer - the one
pip-installed numba uses on macOS - aborts the whole process when that happens. On that layer every call into
compiled numba code takes one shared lock, so kernels take turns (each one still uses every core) while the
rest of the work (decoding, numpy, colour maths, drawing) still overlaps.
"""

from __future__ import annotations

import threading

_LOCK = threading.RLock()
_layer = ""
_installed = False


def threading_layer() -> str:
    """The threading layer numba uses in this process, chosen now if no parallel kernel has run yet."""
    global _layer
    if _layer:
        return _layer
    import numba

    try:
        _layer = numba.threading_layer()
    except ValueError:  # numba picks its layer at the first parallel launch: make it pick now
        try:
            from numba.np.ufunc import parallel

            parallel._launch_threads()
            _layer = numba.threading_layer()
        except Exception:  # noqa: BLE001
            _layer = "unknown"
    return _layer


def is_threadsafe() -> bool:
    return threading_layer() in ("omp", "tbb")


def active() -> bool:
    """True when numba calls are being serialised (the layer is not thread-safe)."""
    return _installed


def install() -> bool:
    """Serialise calls into numba-compiled code when the threading layer is not thread-safe.

    Call once at start-up, before any rendering thread starts. Returns True when the guard is on.
    """
    global _installed
    if _installed or is_threadsafe():
        return _installed
    from numba import _dispatcher
    from numba.core.dispatcher import Dispatcher

    base_call = _dispatcher.Dispatcher.__call__  # the compiled dispatcher's own call

    def __call__(self, *args, **kwargs):
        with _LOCK:
            return base_call(self, *args, **kwargs)

    Dispatcher.__call__ = __call__  # every @njit function (CPUDispatcher) inherits it
    _installed = True
    return True
