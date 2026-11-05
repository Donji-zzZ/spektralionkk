"""Film / paper profile catalogue.

* spektrafilm's 20 colour films and 8 colour papers (Andrea Volpato, CC BY-SA 4.0)
* SpektraLab's black-and-white films, Ilford Multigrade IV RC paper and the CineStill 800T alias
  (from github.com/JamesQiu2005/SpektraLab engine/resources_product, GPL-3.0; built from the
  manufacturers' published datasheets — see data/NOTICE-SpektraLab-profiles.md)
"""

from __future__ import annotations

import dataclasses
import json
import os
import threading
from dataclasses import dataclass
from functools import lru_cache

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
EXTRA_DIR = os.path.join(DATA_DIR, "profiles")
NO_PRINT = "none"  # direct scan of the film (slides)
BW_PAPER = "ilford_multigrade_iv_rc"
DIGITAL = "digital"  # no film simulation: neutral filmic rendering (base for Lightroom presets / LUTs)


@dataclass(frozen=True)
class Stock:
    key: str
    name: str
    kind: str  # 'negative' | 'positive'
    use: str  # 'still' | 'cine'
    bw: bool = False
    target_print: str | None = None
    source: str = "spektrafilm"


_lock = threading.Lock()
_cache: dict[str, object] = {}


def _extra_keys() -> list[str]:
    try:
        return sorted(os.path.splitext(n)[0] for n in os.listdir(EXTRA_DIR) if n.endswith(".json"))
    except OSError:
        return []


def _load_extra(key: str):
    from spektrafilm import load_profile
    from spektrafilm.profiles import io as pio

    with open(os.path.join(EXTRA_DIR, key + ".json"), encoding="utf-8") as fh:
        d = json.load(fh)
    if "derived_from" in d:  # alias: base profile with a few info keys overridden
        base = load_profile(d["derived_from"])
        prof = dataclasses.replace(base, info=dataclasses.replace(base.info))
        for k, v in d.get("info", {}).items():
            if hasattr(prof.info, k):
                setattr(prof.info, k, v)
        prof.info.stock = key
        return prof
    known_meta = {f.name for f in dataclasses.fields(pio.ProfileMetadata)}
    known_info = {f.name for f in dataclasses.fields(pio.ProfileInfo)}
    d["metadata"] = {k: v for k, v in d.get("metadata", {}).items() if k in known_meta}
    d["info"] = {k: v for k, v in d.get("info", {}).items() if k in known_info}
    return pio.profile_from_dict(d)


def base_stock(key: str) -> str:
    """The stock whose spectral data a profile uses: an alias such as CineStill 800T (Vision3 500T without
    the rem-jet layer) returns its base, everything else returns itself."""
    if key not in _extra_keys():
        return key
    try:
        with open(os.path.join(EXTRA_DIR, key + ".json"), encoding="utf-8") as fh:
            return json.load(fh).get("derived_from") or key
    except (OSError, ValueError):
        return key


def load(key: str):
    """Load (and cache) a profile by stock key, from spektrafilm or the bundled extras."""
    with _lock:
        if key in _cache:
            return _cache[key]
    if key in _extra_keys():
        prof = _load_extra(key)
    else:
        from spektrafilm import load_profile

        prof = load_profile(key)
    with _lock:
        _cache[key] = prof
    return prof


def _stock(key: str, source: str) -> Stock:
    info = load(key).info
    return Stock(key, info.name or key, info.type, info.use or "still",
                 getattr(info, "channel_model", "color") == "bw", getattr(info, "target_print", None), source)


@lru_cache(maxsize=1)
def film_stocks() -> tuple[Stock, ...]:
    from spektrafilm.model.stocks import FilmStocks

    out = [Stock(DIGITAL, "Digital (no film)", "digital", "still", False, None, "app")]
    out += [_stock(e.value, "spektrafilm") for e in FilmStocks]
    for k in _extra_keys():
        if k != BW_PAPER:
            out.append(_stock(k, "SpektraLab"))
    return tuple(out)


@lru_cache(maxsize=1)
def print_papers() -> tuple[Stock, ...]:
    from spektrafilm.model.stocks import PrintPapers

    out = [_stock(e.value, "spektrafilm") for e in PrintPapers]
    if BW_PAPER in _extra_keys():
        out.append(_stock(BW_PAPER, "SpektraLab"))
    return tuple(out)


def stock_by_key(key: str) -> Stock | None:
    for s in film_stocks() + print_papers():
        if s.key == key:
            return s
    return None


# --- Multigrade contrast grades -------------------------------------------------

@lru_cache(maxsize=1)
def _grades():
    with open(os.path.join(DATA_DIR, "paper_grades.json"), encoding="utf-8") as fh:
        g = json.load(fh)["grades"]
    order = ["00", "0", "1", "2", "3", "4", "5"]
    pos = [-1.0, 0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    return [(p, g[k]["m_filter_neutral"], g[k]["y_filter_neutral"], g[k]["print_exposure"]) for p, k in zip(pos, order)]


def multigrade_pack(grade: float) -> tuple[float, float, float]:
    """(m_filter_neutral, y_filter_neutral, print_exposure) for a grade in [-1 (=00), 5]; half grades interpolated."""
    rows = _grades()
    grade = min(max(float(grade), rows[0][0]), rows[-1][0])
    for (p0, m0, y0, e0), (p1, m1, y1, e1) in zip(rows, rows[1:]):
        if p0 <= grade <= p1:
            t = (grade - p0) / (p1 - p0)
            return (m0 + t * (m1 - m0), y0 + t * (y1 - y0), e0 + t * (e1 - e0))
    return rows[-1][1:]


def grade_label(grade: float) -> str:
    return "00" if grade <= -0.75 else (f"{grade:.1f}".rstrip("0").rstrip(".") if grade >= 0 else f"{grade:.1f}")
