"""Creative LUTs (.cube): import, store and apply.

Imported LUTs are copied to %LOCALAPPDATA%\\sprktralionkk\\luts so presets that use them keep working.
They are applied to the finished, display-encoded (sRGB) image — the space most "film look" .cube
files are made for. (LUTs made for camera log footage expect log input and will look wrong.)
"""

from __future__ import annotations

import os
import re
import shutil
import threading

import numpy as np


def lut_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "sprktralionkk", "luts")
    os.makedirs(d, exist_ok=True)
    return d


_cache: dict[str, tuple] = {}
_lock = threading.Lock()


def parse_cube(path: str):
    """Returns (kind, table, domain_min, domain_max, title). kind '3d': table [r, g, b, 3]; '1d': [n, 3]."""
    size3 = size1 = None
    dmin, dmax = np.zeros(3, np.float32), np.ones(3, np.float32)
    title = os.path.splitext(os.path.basename(path))[0]
    rows = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            up = line.upper()
            if up.startswith("TITLE"):
                m = re.search(r'"(.*)"', line)
                if m and m.group(1).strip():
                    title = m.group(1).strip()
            elif up.startswith("LUT_3D_SIZE"):
                size3 = int(line.split()[1])
            elif up.startswith("LUT_1D_SIZE"):
                size1 = int(line.split()[1])
            elif up.startswith("DOMAIN_MIN"):
                dmin = np.array([float(v) for v in line.split()[1:4]], np.float32)
            elif up.startswith("DOMAIN_MAX"):
                dmax = np.array([float(v) for v in line.split()[1:4]], np.float32)
            elif up.startswith("LUT_3D_INPUT_RANGE") or up.startswith("LUT_1D_INPUT_RANGE"):
                lo, hi = (float(v) for v in line.split()[1:3])
                dmin, dmax = np.full(3, lo, np.float32), np.full(3, hi, np.float32)
            elif re.match(r"^[-+0-9.eE]", line):
                vals = line.split()
                if len(vals) >= 3:
                    rows.append([float(v) for v in vals[:3]])
    data = np.asarray(rows, np.float32)
    if size3:
        if len(data) != size3 ** 3:
            raise ValueError(f"{os.path.basename(path)}: expected {size3 ** 3} rows, found {len(data)}")
        # file order: red changes fastest, then green, then blue
        table = np.ascontiguousarray(data.reshape(size3, size3, size3, 3).transpose(2, 1, 0, 3))
        return "3d", table, dmin, dmax, title
    if size1:
        if len(data) != size1:
            raise ValueError(f"{os.path.basename(path)}: expected {size1} rows, found {len(data)}")
        return "1d", data, dmin, dmax, title
    raise ValueError(f"{os.path.basename(path)} is not a .cube LUT (no LUT_3D_SIZE / LUT_1D_SIZE)")


def import_cube(path: str) -> str:
    """Validate and copy a .cube into the LUT store; returns the name to reference it by."""
    kind, table, dmin, dmax, title = parse_cube(path)
    name = os.path.splitext(os.path.basename(path))[0]
    dst = os.path.join(lut_dir(), name + ".cube")
    if os.path.abspath(dst) != os.path.abspath(path):
        shutil.copyfile(path, dst)
    with _lock:
        _cache.pop(name, None)
    return name


def available() -> list[str]:
    try:
        return sorted(os.path.splitext(n)[0] for n in os.listdir(lut_dir()) if n.lower().endswith(".cube"))
    except OSError:
        return []


def load(name: str):
    with _lock:
        if name in _cache:
            return _cache[name]
    path = os.path.join(lut_dir(), name + ".cube")
    lut = parse_cube(path) if os.path.exists(path) else None
    with _lock:
        _cache[name] = lut
    return lut


def apply(rgb: np.ndarray, name: str, amount: float) -> np.ndarray:
    """rgb: float32 HxWx3 (or Nx3) display-encoded in [0, 1]."""
    lut = load(name) if name else None
    if lut is None or amount <= 0:
        return rgb
    kind, table, dmin, dmax, _ = lut
    shape = rgb.shape
    x = ((rgb.reshape(-1, 3) - dmin) / np.maximum(dmax - dmin, 1e-6)).astype(np.float32)
    x = np.clip(x, 0.0, 1.0)
    if kind == "1d":
        n = table.shape[0]
        grid = np.linspace(0, 1, n, dtype=np.float32)
        out = np.stack([np.interp(x[:, c], grid, table[:, c]) for c in range(3)], axis=1)
    else:
        n = table.shape[0]
        f = x * (n - 1)
        i0 = np.minimum(f.astype(np.int32), n - 2)
        d = f - i0
        r0, g0, b0 = i0[:, 0], i0[:, 1], i0[:, 2]
        dr, dg, db = d[:, 0:1], d[:, 1:2], d[:, 2:3]
        c000 = table[r0, g0, b0]; c100 = table[r0 + 1, g0, b0]
        c010 = table[r0, g0 + 1, b0]; c110 = table[r0 + 1, g0 + 1, b0]
        c001 = table[r0, g0, b0 + 1]; c101 = table[r0 + 1, g0, b0 + 1]
        c011 = table[r0, g0 + 1, b0 + 1]; c111 = table[r0 + 1, g0 + 1, b0 + 1]
        c00 = c000 + (c100 - c000) * dr; c10 = c010 + (c110 - c010) * dr
        c01 = c001 + (c101 - c001) * dr; c11 = c011 + (c111 - c011) * dr
        c0 = c00 + (c10 - c00) * dg; c1 = c01 + (c11 - c01) * dg
        out = c0 + (c1 - c0) * db
    a = min(max(amount / 100.0, 0.0), 1.0)
    out = rgb.reshape(-1, 3) * (1 - a) + out * a
    return np.clip(out, 0.0, 1.0).reshape(shape).astype(np.float32)
