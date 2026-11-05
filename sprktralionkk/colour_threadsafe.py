"""Make colour-science's global mode switches per-thread.

colour-science keeps three process-wide settings (domain-range scale, safe-division mode,
safe-power switch) and many of its functions flip them temporarily with context managers, e.g.
RGB_to_RGB / sRGB transfer functions switch the domain-range scale. spektrafilm's scan step calls
those functions, so when two threads render at the same time one thread can observe the other's
temporary setting in the middle of a CAM16 calculation and produce garbage (measured: errors of
up to 0.86 on a 0..1 scale with three concurrent print renders).

This patch keeps every existing call site working unchanged:
  * get_* / set_* functions read / write a threading.local value (their code objects are swapped,
    so references imported elsewhere are covered too);
  * the module globals that colour reads directly (``_DOMAIN_RANGE_SCALE == "1"``,
    ``if not _SPOW_ENABLED``, ``validate_method(_SDIV_MODE, ...)``) become small proxies that
    compare / format / delegate using the current thread's value.
New threads start from colour's defaults ("reference", "Ignore Zero Conversion", True).
"""

from __future__ import annotations

import threading

_done = False


class _ThreadValue:
    __slots__ = ("_tls", "_attr", "_default")

    def __init__(self, tls, attr, default):
        self._tls, self._attr, self._default = tls, attr, default

    def value(self):
        return getattr(self._tls, self._attr, self._default)

    def __eq__(self, other):
        return self.value() == (other.value() if isinstance(other, _ThreadValue) else other)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self.value())

    def __bool__(self):
        return bool(self.value())

    def __str__(self):
        return str(self.value())

    def __repr__(self):
        return repr(self.value())

    def __getattr__(self, name):  # e.g. .lower() inside validate_method
        return getattr(self.value(), name)


def install():
    global _done
    if _done:
        return
    import colour  # noqa: F401  (make sure the modules are initialised)
    import colour.algebra.common as alg
    import colour.utilities.array as arr

    tls = threading.local()

    # --- domain-range scale (colour.utilities.array)
    arr._sprk_tls = tls
    arr._DOMAIN_RANGE_SCALE = _ThreadValue(tls, "scale", "reference")

    def _get_scale():
        return getattr(_sprk_tls, "scale", "reference")  # noqa: F821  (resolved in arr's globals)

    def _set_scale(scale="reference"):
        _sprk_tls.scale = validate_method(  # noqa: F821
            str(scale), ("ignore", "reference", "1", "100"), '"{0}" scale is invalid, it must be one of {1}!')

    arr.get_domain_range_scale.__code__ = _get_scale.__code__
    arr.set_domain_range_scale.__code__ = _set_scale.__code__

    # --- safe division mode and safe power switch (colour.algebra.common)
    alg._sprk_tls = tls
    alg._SDIV_MODE = _ThreadValue(tls, "sdiv", "Ignore Zero Conversion")
    alg._SPOW_ENABLED = _ThreadValue(tls, "spow", True)

    def _get_sdiv():
        return getattr(_sprk_tls, "sdiv", "Ignore Zero Conversion")  # noqa: F821

    def _set_sdiv(mode):
        _sprk_tls.sdiv = str(mode)  # noqa: F821

    def _is_spow():
        return getattr(_sprk_tls, "spow", True)  # noqa: F821

    def _set_spow(enable):
        _sprk_tls.spow = bool(enable)  # noqa: F821

    alg.get_sdiv_mode.__code__ = _get_sdiv.__code__
    alg.set_sdiv_mode.__code__ = _set_sdiv.__code__
    alg.is_spow_enabled.__code__ = _is_spow.__code__
    alg.set_spow_enable.__code__ = _set_spow.__code__
    _done = True
