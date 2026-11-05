"""Render engine: wraps spektrafilm with staged caching for interactive editing.

Stages (each cached, so an edit only recomputes what it affects):
  decode      RAW (camera as-shot WB, half-size for previews) or image -> linear ProPhoto RGB
  wb          scene-illuminant re-balance as a 3x3 matrix (no RAW re-decode)
  geometry    rotate / flip / straighten -> frame;  crop rectangle -> photo
  metering    auto-exposure measured once per framing (shared by preview, 1:1 tiles and export)
  film half   RGB -> CMY_FILM negative densities
  print half  negative -> simulated print / scan
  finish      Lightroom-style tone, presence, color grading, vignette (no film re-run)
  border      film edge / print border
plus a cache of finished display images, so reset / undo / switching back are instant.

Speed-ups (numerically safe): spectral LUTs for enlarger/scanner (~3e-4 mean error), parallel
chunked output gamut compression (bit-identical), spektrafilm's numba grain samplers, and grain is
only simulated when the preview's pixel scale is fine enough for grain to be visible.
"""

from __future__ import annotations

import math
import os
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

from . import finish as finishing
from . import profiles, wb
from .settings import (
    BORDER_FIELDS,
    FILM_FIELDS,
    FILM_FORMATS,
    FINISH_FIELDS,
    GEOMETRY_FIELDS,
    METER_FIELDS,
    NO_PRINT,
    PRINT_FIELDS,
    WB_FIELDS,
    DevelopSettings,
    edge_gate,
    effective_crop,
    geometry_key,
)

RAW_EXTENSIONS = {".nef", ".nrw", ".cr2", ".cr3", ".crw", ".arw", ".srf", ".sr2", ".raf", ".orf", ".rw2",
                  ".dng", ".pef", ".srw", ".3fr", ".iiq", ".erf", ".kdc", ".mrw", ".rwl", ".x3f", ".raw"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".exr", ".heic", ".heif", ".webp", ".bmp"}
SUPPORTED_EXTENSIONS = RAW_EXTENSIONS | IMAGE_EXTENSIONS

PROXY_LONG_EDGE = 3072  # in-memory working copy (RAW: half-size demosaic)
DRAFT_LONG_EDGE = 720
THUMB_LONG_EDGE = 240
FINE_MAX = 2880
DETAIL_PAD = 48
GRAIN_VISIBLE_UM = 12.0  # simulate grain when one preview pixel covers <= this much film
WORKING = "ProPhoto RGB"

_POOL = ThreadPoolExecutor(max_workers=max(2, min(8, (os.cpu_count() or 4))))
PREFS = {"always_grain": False, "show_frame": True}


def is_raw(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in RAW_EXTENSIONS


class RenderCancelled(Exception):
    pass


# ------------------------------------------------------------------ CPU / speed-ups

def configure_thread(headroom: bool = True):
    """Call from every thread that renders: leaves two cores free so the PC stays responsive."""
    try:
        import numba

        n = numba.config.NUMBA_NUM_THREADS
        numba.set_num_threads(max(2, n - 2) if headroom and n > 4 else n)
    except Exception:
        pass


_speedups_done = False


def install_speedups():
    """Run spektrafilm's per-pixel output gamut compression in bounded parallel chunks (identical result)."""
    global _speedups_done
    if _speedups_done:
        return
    from . import colour_threadsafe

    colour_threadsafe.install()  # colour-science global modes -> per thread (concurrent renders were corrupting)
    import spektrafilm.runtime.stages.scanning as scanning

    orig = scanning.compress_rgb
    chunk_px = 131072

    def compress_rgb_parallel(rgb, spec, **kw):
        if rgb.ndim != 3 or rgb.shape[0] * rgb.shape[1] <= chunk_px:
            return orig(rgb, spec, **kw)
        h, w = rgb.shape[:2]
        rows = max(1, chunk_px // w)
        out = np.empty_like(rgb)

        def one(y0):
            out[y0:y0 + rows] = orig(rgb[y0:y0 + rows], spec, **kw)

        list(_POOL.map(one, range(0, h, rows)))
        return out

    scanning.compress_rgb = compress_rgb_parallel

    # Film grain: one exact Poisson draw per pixel and layer instead of Poisson + binomial loops (grainfast.py).
    from . import grainfast

    grainfast.install()

    # The camera stage's RGB -> XYZ (with CAT16 adaptation) is linear when no transfer function is decoded:
    # apply it as one cached 3x3 matrix instead of colour-science's generic per-call path (same numbers).
    import colour
    import spektrafilm.utils.spectral_upsampling as su

    orig_tc_b = su._rgb_to_tc_b
    mats: dict = {}

    def rgb_to_tc_b(rgb, color_space="ITU-R BT.2020", apply_cctf_decoding=False, reference_illuminant="D55"):
        if apply_cctf_decoding or np.ndim(rgb) != 3:
            return orig_tc_b(rgb, color_space, apply_cctf_decoding, reference_illuminant)
        key = (color_space, reference_illuminant)
        m = mats.get(key)
        if m is None:
            illu_xy = su._illuminant_to_xy(reference_illuminant)
            m = np.asarray(colour.RGB_to_XYZ(np.eye(3), colourspace=color_space, apply_cctf_decoding=False,
                                             illuminant=illu_xy, chromatic_adaptation_transform="CAT16"),
                           np.float64)  # row i = XYZ of the i-th primary
            mats[key] = m
        xyz = np.asarray(rgb, np.float64) @ m
        b = np.sum(xyz, axis=-1)
        xy = xyz[..., 0:2] / np.fmax(b[..., None], 1e-10)
        return su._tri2quad(xy), np.nan_to_num(b)

    su._rgb_to_tc_b = rgb_to_tc_b
    _speedups_done = True


# ------------------------------------------------------------------ colour helpers

@lru_cache(maxsize=16)
def _rgb_matrix(src_cs: str, dst_cs: str) -> np.ndarray:
    import colour

    return np.asarray(colour.matrix_RGB_to_RGB(colour.RGB_COLOURSPACES[src_cs], colour.RGB_COLOURSPACES[dst_cs],
                                               chromatic_adaptation_transform="CAT02"), np.float32)


def _srgb_oetf(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4, dtype=np.float32) - 0.055)


def _srgb_eotf(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.04045, x / 12.92, np.power((x + 0.055) / 1.055, 2.4, dtype=np.float32))


def to_working(img: np.ndarray, cs: str, cctf: bool) -> np.ndarray:
    """Any decoded image -> linear ProPhoto RGB float32."""
    import colour

    if cs == "sRGB":
        lin = _srgb_eotf(img).astype(np.float32) if cctf else img.astype(np.float32)
    else:
        lin = np.asarray(colour.RGB_COLOURSPACES[cs].cctf_decoding(img), np.float32) if cctf else img
    m = _rgb_matrix(cs, WORKING)
    return np.maximum(lin.reshape(-1, 3) @ m.T, 0.0).reshape(img.shape).astype(np.float32)


def working_to_display(img: np.ndarray) -> np.ndarray:
    """Linear ProPhoto -> sRGB display, uint8."""
    m = _rgb_matrix(WORKING, "sRGB")
    lin = (img.reshape(-1, 3) @ m.T).reshape(img.shape)
    return (_srgb_oetf(lin) * 255.0 + 0.5).astype(np.uint8)


def to_u8(img: np.ndarray) -> np.ndarray:
    if img.dtype == np.uint8:
        return img
    return (np.clip(img, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


# ------------------------------------------------------------------ decoding

@dataclass
class Source:
    path: str
    image: np.ndarray  # linear ProPhoto float32, camera / file white balance
    full_size: tuple[int, int]  # (w, h) of the full-resolution photo
    as_shot: tuple[float, float]  # Kelvin, tint of the file's own white balance
    raw: bool
    auto: tuple[float, float] | None = None
    exif: dict = field(default_factory=dict)
    note: str = ""  # shown to the user (e.g. "editing the embedded preview")


UNSUPPORTED_RAW_NOTE = ("LibRaw can't decode this RAW's compression yet (for example Nikon High Efficiency or "
                        "JPEG XL DNG), so you are editing the camera's embedded full-size JPEG instead.")


def _embedded_preview(path: str, long_edge: int | None):
    """Largest embedded JPEG of a RAW file as float sRGB, upright. Needs a freshly opened file:
    after a failed unpack LibRaw refuses further calls on the same handle."""
    import io

    import rawpy
    from PIL import Image, ImageOps

    with rawpy.imread(path) as raw:
        flip = raw.sizes.flip
        th = raw.extract_thumb()
    if th.format == rawpy.ThumbFormat.JPEG:
        im = Image.open(io.BytesIO(th.data))
        if long_edge:
            im.draft("RGB", (long_edge, long_edge))  # fast DCT-domain downscale for previews
        if im.getexif().get(0x0112, 1) != 1:
            im = ImageOps.exif_transpose(im)
        else:
            im = {3: lambda i: i.transpose(Image.Transpose.ROTATE_180),
                  5: lambda i: i.transpose(Image.Transpose.ROTATE_90),
                  6: lambda i: i.transpose(Image.Transpose.ROTATE_270)}.get(flip, lambda i: i)(im)
        arr = np.asarray(im.convert("RGB"), np.float32) / 255.0
    else:
        arr = np.asarray(th.data, np.float32) / 255.0
    if arr.ndim == 2:
        arr = np.repeat(arr[..., None], 3, axis=2)
    if min(arr.shape[:2]) < 400:
        raise RuntimeError("the embedded preview is too small to edit")
    return arr


def _raw_size(path):
    import rawpy

    with rawpy.imread(path) as raw:
        s = raw.sizes
        w, h = s.width, s.height
        if s.flip in (5, 6):
            w, h = h, w
        return w, h


def decode_raw(path: str, lens_correction: bool, half_size: bool) -> np.ndarray:
    """Camera as-shot white balance, same processing as spektrafilm's raw loader, -> linear ProPhoto."""
    import colour
    import rawpy
    from spektrafilm.utils import raw_file_processor as rfp

    params, _, _ = rfp._postprocess_params("as_shot", None, None)
    with rawpy.imread(path) as raw:
        rgb = raw.postprocess(half_size=half_size, **params).astype(np.float32) / np.float32(65535.0)
    if lens_correction:
        try:
            rgb, _ = rfp._apply_lens_correction(rgb, rfp._read_exif_metadata(path))
        except Exception as exc:
            print("lens correction skipped:", exc)
    m = np.asarray(colour.matrix_RGB_to_RGB(rfp._ACES_COLOURSPACE, colour.RGB_COLOURSPACES[WORKING],
                                            chromatic_adaptation_transform="CAT02"), np.float32)
    return np.maximum(rgb.reshape(-1, 3) @ m.T, 0.0).reshape(rgb.shape).astype(np.float32)


def decode(path: str, lens_correction: bool = False, long_edge: int | None = None) -> Source:
    note = ""
    if is_raw(path):
        import rawpy

        try:
            full = _raw_size(path)
            half = bool(long_edge) and max(full) // 2 >= long_edge * 0.75
            img = decode_raw(path, lens_correction, half_size=half)
            as_shot = wb.raw_as_shot(path) or wb.NOMINAL
            raw = True
        except rawpy.LibRawError as exc:  # compression LibRaw can't unpack: use the embedded JPEG
            try:
                img = _embedded_preview(path, long_edge)
            except Exception as exc2:
                raise RuntimeError(
                    f"This RAW file can't be decoded ({type(exc).__name__}) and it has no usable embedded "
                    f"preview ({exc2}). Convert it with Adobe DNG Converter or the camera maker's software, "
                    "or export a TIFF/JPEG and open that.") from exc
            full = (img.shape[1], img.shape[0])
            img = to_working(np.ascontiguousarray(img, np.float32), "sRGB", True)
            as_shot, raw, note = wb.NOMINAL, False, UNSUPPORTED_RAW_NOTE
    else:
        img = _load_image(path)[..., :3]
        full = (img.shape[1], img.shape[0])
        if long_edge:
            img = resize_long_edge(np.ascontiguousarray(img, np.float32), long_edge)
        img = to_working(img, "sRGB", not path.lower().endswith(".exr"))
        as_shot, raw = wb.NOMINAL, False
    img = np.ascontiguousarray(img, dtype=np.float32)
    if long_edge:
        img = resize_long_edge(img, long_edge)
    return Source(path, img, full, as_shot, raw, exif=read_exif(path), note=note)


def _load_image(path: str) -> np.ndarray:
    try:
        from spektrafilm.utils.io import load_image_oiio

        img = np.asarray(load_image_oiio(path), dtype=np.float32)
    except Exception:
        from PIL import Image, ImageOps

        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            img = np.asarray(im, dtype=np.float32) / 255.0
    if img.ndim == 2:
        img = np.repeat(img[..., None], 3, axis=2)
    if img.shape[2] == 1:
        img = np.repeat(img, 3, axis=2)
    return img


_exif_cache: dict[str, dict] = {}


def read_exif(path: str) -> dict:
    if path in _exif_cache:
        return _exif_cache[path]
    info = {}
    try:
        import exiv2

        im = exiv2.ImageFactory.open(path)
        im.readMetadata()
        wanted = {"Exif.Image.Make", "Exif.Image.Model", "Exif.Photo.LensModel", "Exif.Photo.ISOSpeedRatings",
                  "Exif.Photo.PhotographicSensitivity", "Exif.Photo.FocalLength", "Exif.Photo.FNumber",
                  "Exif.Photo.ExposureTime", "Exif.Photo.DateTimeOriginal", "Exif.Image.DateTime"}
        found = {}
        # NB: exifData()[missing key] aborts the process inside exiv2, so only read keys that exist
        for datum in im.exifData():
            k = datum.key()
            if k in wanted and k not in found:
                found[k] = datum.toString()

        def get(k):
            return found.get(k)

        def rat(v):
            try:
                n, d = v.split("/")
                return float(n) / float(d)
            except Exception:
                try:
                    return float(v)
                except Exception:
                    return None

        make, model = get("Exif.Image.Make") or "", get("Exif.Image.Model") or ""
        info["camera"] = model if model.lower().startswith(make.lower().split()[0] if make else "~") else \
            f"{make} {model}".strip()
        info["lens"] = get("Exif.Photo.LensModel") or ""
        iso = get("Exif.Photo.ISOSpeedRatings") or get("Exif.Photo.PhotographicSensitivity")
        fl, fn, et = rat(get("Exif.Photo.FocalLength") or ""), rat(get("Exif.Photo.FNumber") or ""), \
            rat(get("Exif.Photo.ExposureTime") or "")
        parts = []
        if iso:
            parts.append(f"ISO {iso.split()[0]}")
        if fl:
            parts.append(f"{fl:g} mm")
        if fn:
            parts.append(f"f/{fn:g}")
        if et:
            parts.append(f"1/{round(1 / et)} s" if et < 0.5 else f"{et:g} s")
        info["shot"] = "   ".join(parts)
        info.update(exposure=et, fnumber=fn, focal=fl)
        dt = get("Exif.Photo.DateTimeOriginal") or get("Exif.Image.DateTime")
        if dt and len(dt) >= 10 and dt[:4].isdigit():  # "YYYY:MM:DD HH:MM:SS" -> date-back style "'YY MM DD"
            info["date"] = f"'{dt[2:4]} {dt[5:7]} {dt[8:10]}"
    except Exception:
        pass
    if "date" not in info:  # no EXIF date: use the file's modification date
        try:
            import datetime

            d = datetime.datetime.fromtimestamp(os.path.getmtime(path))
            info["date"] = d.strftime("'%y %m %d")
        except OSError:
            pass
    _exif_cache[path] = info
    return info


def resize_long_edge(img: np.ndarray, long_edge: int) -> np.ndarray:
    h, w = img.shape[:2]
    if max(h, w) <= long_edge:
        return img
    scale = long_edge / max(h, w)
    return resize_to(img, max(1, round(w * scale)), max(1, round(h * scale)))


def resize_to(img: np.ndarray, nw: int, nh: int) -> np.ndarray:
    from PIL import Image

    src = np.ascontiguousarray(img, dtype=np.float32)
    resample = Image.Resampling.BICUBIC if nw > img.shape[1] else Image.Resampling.BOX

    def one(c):
        return np.asarray(Image.fromarray(src[..., c], mode="F").resize((nw, nh), resample), dtype=np.float32)

    return np.stack(list(_POOL.map(one, range(3))), axis=-1)


# ------------------------------------------------------------------ geometry

def frame_geometry(img: np.ndarray, s: DevelopSettings) -> np.ndarray:
    """Rotate / flip / straighten (with automatic inner crop): the frame the crop rectangle lives in."""
    if s.rotation % 4:
        img = np.rot90(img, k=-(s.rotation % 4))
    if s.flip_h:
        img = img[:, ::-1]
    if s.flip_v:
        img = img[::-1]
    if abs(s.straighten) > 1e-3:
        img = _straighten(img, s.straighten)
    return np.ascontiguousarray(img)


def crop_frame(frame: np.ndarray, s: DevelopSettings) -> np.ndarray:
    h, w = frame.shape[:2]
    l, t, r, b = effective_crop(s, w, h)
    x0, x1 = int(round(l * w)), int(round(r * w))
    y0, y1 = int(round(t * h)), int(round(b * h))
    x1, y1 = max(x1, x0 + 8), max(y1, y0 + 8)
    return np.ascontiguousarray(frame[y0:y1, x0:x1])


def apply_geometry(img: np.ndarray, s: DevelopSettings) -> np.ndarray:
    return crop_frame(frame_geometry(img, s), s)


def _straighten(img: np.ndarray, degrees: float) -> np.ndarray:
    from scipy.ndimage import rotate

    h, w = img.shape[:2]
    rot = np.stack(list(_POOL.map(
        lambda c: rotate(img[..., c], -degrees, reshape=False, order=1, mode="nearest"), range(3))), axis=-1)
    a = math.radians(abs(degrees))
    sin_a, cos_a = math.sin(a), math.cos(a)
    long_side, short_side = (w, h) if w >= h else (h, w)
    if short_side <= 2 * sin_a * cos_a * long_side or abs(sin_a - cos_a) < 1e-10:
        x = 0.5 * short_side
        wr, hr = (x / sin_a, x / cos_a) if w >= h else (x / cos_a, x / sin_a)
    else:
        cos_2a = cos_a * cos_a - sin_a * sin_a
        wr, hr = (w * cos_a - h * sin_a) / cos_2a, (h * cos_a - w * sin_a) / cos_2a
    wr, hr = int(max(1, min(w, wr))), int(max(1, min(h, hr)))
    y0, x0 = (h - hr) // 2, (w - wr) // 2
    return rot[y0:y0 + hr, x0:x0 + wr]


# ------------------------------------------------------------------ params

def digital_render(lin: np.ndarray, color_space: str = "sRGB") -> np.ndarray:
    """'Digital (no film)': linear ProPhoto -> filmic tone map (ACES fit) -> display encoding, float32."""
    m = _rgb_matrix(WORKING, color_space)
    x = np.maximum(np.asarray(lin, np.float32).reshape(-1, 3) @ m.T, 0.0) * 0.8
    y = (x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14)
    y = np.clip(y, 0.0, 1.0).reshape(lin.shape)
    if color_space == "sRGB":
        return _srgb_oetf(y).astype(np.float32)
    import colour

    return np.clip(np.asarray(colour.RGB_COLOURSPACES[color_space].cctf_encoding(y), np.float32), 0, 1)


def is_digital(s: DevelopSettings) -> bool:
    return s.film == profiles.DIGITAL


def effective_paper(s: DevelopSettings) -> str:
    """The paper actually used: slides may be scanned directly; negatives always need a paper."""
    if is_digital(s):
        return NO_PRINT
    film = profiles.stock_by_key(s.film)
    paper = s.paper if (s.paper == NO_PRINT or profiles.stock_by_key(s.paper)) else "kodak_portra_endura"
    if paper == NO_PRINT and film and film.kind != "positive":
        paper = profiles.BW_PAPER if film.bw else (film.target_print if profiles.stock_by_key(
            film.target_print or "") else ("kodak_2383" if film.use == "cine" else "kodak_portra_endura"))
    return paper


def meter(img: np.ndarray, s: DevelopSettings) -> float:
    """Auto-exposure EV exactly as spektrafilm measures it (on a 256 px version of the frame)."""
    if not s.auto_exposure:
        return 0.0
    from spektrafilm.utils.autoexposure import measure_autoexposure_ev

    small = resize_long_edge(img, 256).astype(np.float64)
    try:
        ev = float(measure_autoexposure_ev(small, WORKING, False, method=s.metering))
    except Exception:
        ev = 0.0
    return ev if np.isfinite(ev) else 0.0


def build_params(s: DevelopSettings, *, output_color_space: str = "sRGB", draft: bool = False,
                 film_format_scale: float = 1.0, grain: bool = True):
    from spektrafilm import RuntimePhotoParams
    from spektrafilm.utils.morph_curves import PrintCurvesMorphParams

    install_speedups()
    paper = effective_paper(s)
    film_prof = profiles.load(s.film)
    p = RuntimePhotoParams(film=film_prof, print=profiles.load(paper if paper != NO_PRINT else "kodak_portra_endura"))
    film_bw = getattr(film_prof.info, "channel_model", "color") == "bw"
    p.io.scan_film = paper == NO_PRINT
    p.io.input_color_space = WORKING
    p.io.input_cctf_decoding = False
    p.io.output_color_space = output_color_space
    p.io.output_cctf_encoding = True
    p.settings.use_enlarger_lut = True
    p.settings.use_scanner_lut = True
    p.settings.use_fast_stats = True
    p.settings.preview_mode = draft
    if film_bw:  # data-sheet B&W profiles carry no spectral-adaptation window
        p.settings.apply_hanatos2025_adaptation_window = False
        p.settings.apply_hanatos2025_adaptation_surface = False

    cam = p.camera
    cam.auto_exposure = False  # metered by meter() so every render of a frame uses the same EV
    cam.exposure_compensation_ev = float(s.exposure_ev)
    cam.film_format_mm = float(FILM_FORMATS.get(s.film_format, 36.0)) * film_format_scale
    cam.diffusion_filter.active = bool(s.diffusion)
    cam.diffusion_filter.filter_family = s.diffusion_family
    cam.diffusion_filter.strength = float(s.diffusion_strength)

    fr = p.film_render
    fr.density_curve_gamma = float(s.negative_contrast)
    if not draft:
        fr.grain.active = bool(s.grain) and s.grain_size > 0 and grain
        fr.grain.particle_area_um2 = float(s.grain_size)
    fr.halation.active = bool(s.halation)
    fr.halation.halation_amount = float(s.halation_amount)
    fr.halation.scatter_amount = float(s.scatter_amount)
    fr.halation.boost_ev = float(s.highlight_boost)
    fr.dir_couplers.active = bool(s.couplers) and not film_bw
    fr.dir_couplers.amount = float(s.couplers_amount)

    en = p.enlarger
    en.print_exposure = float(2.0 ** s.print_brightness)
    en.print_exposure_compensation = bool(s.auto_print_compensation)
    en.y_filter_shift = float(s.yellow)
    en.m_filter_shift = float(s.magenta)
    en.preflash_exposure = float(s.preflash)
    if paper == profiles.BW_PAPER:  # Multigrade: contrast grade = enlarger filtration + exposure
        m_n, y_n, exp = profiles.multigrade_pack(s.bw_grade)
        p.settings.neutral_print_filters_from_database = False
        en.c_filter_neutral, en.m_filter_neutral, en.y_filter_neutral = 0.0, m_n, y_n
        en.print_exposure = float(exp * 2.0 ** s.print_brightness)
    elif paper != NO_PRINT and profiles.base_stock(s.film) != s.film:
        # An alias profile (CineStill 800T = Vision3 500T data) has no entry of its own in spektrafilm's
        # neutral-print-filter database; without one the default filtration prints greys strongly green.
        # Its spectral data is the base stock's, so the base stock's neutral filtration is exact.
        from spektrafilm.runtime.params_builder import _get_neutral_print_filters

        ent = _get_neutral_print_filters().get(paper, {}).get(en.illuminant, {}).get(profiles.base_stock(s.film))
        if ent is not None:
            p.settings.neutral_print_filters_from_database = False
            en.c_filter_neutral, en.m_filter_neutral, en.y_filter_neutral = (float(v) for v in ent)

    pr = p.print_render
    morph_active = abs(s.print_contrast - 1.0) > 1e-4 or s.developer_exhaustion > 1e-4
    pr.density_curves_morph = PrintCurvesMorphParams(
        active=morph_active, gamma_factor=float(s.print_contrast),
        developer_exhaustion=float(s.developer_exhaustion))
    pr.glare.active = bool(s.glare) and s.glare_amount > 0
    pr.glare.percent = float(s.glare_amount)

    sc = p.scanner
    sc.unsharp_mask = (0.7, float(s.sharpen)) if (s.sharpen > 0 and not draft) else (0.0, 0.0)
    sc.white_correction = bool(s.white_correction)
    sc.black_correction = bool(s.black_correction)
    return p


def _simulator(s, **kw):
    from spektrafilm import Simulator, digest_params

    return Simulator(digest_params(build_params(s, **kw)))


def _film_half(sim, work):
    from spektrafilm.runtime.topology import Tap

    return sim._pipeline.process(work, collect=Tap.CMY_FILM)


def _print_half(sim, neg):
    from spektrafilm.runtime.topology import Tap

    out = sim._pipeline.process(neg, inject=Tap.CMY_FILM)
    return np.clip(np.nan_to_num(out, nan=0.0), 0.0, 1.0).astype(np.float32)


def fast_print(s: DevelopSettings, neg: np.ndarray, color_space: str = "sRGB") -> np.ndarray:
    """Print + scan through the baked table (fastprint.py): same result as _print_half within ΔE00 ~0.1."""
    from . import fastprint

    return fastprint.printer_for(s, color_space).apply(neg)


def film_label(s: DevelopSettings) -> str:
    if is_digital(s):
        return "Digital"
    st = profiles.stock_by_key(s.film)
    return st.name if st else s.film


def film_kind(s: DevelopSettings) -> str:
    if is_digital(s):
        return "digital"
    st = profiles.stock_by_key(s.film)
    if st is None:
        return "negative"
    return "bw" if st.bw else st.kind


def frame_kind(s: DevelopSettings, show_frame: bool = True) -> str:
    from .borders import resolve_kind

    if not show_frame:
        return "none"
    return resolve_kind(s.border, film_kind(s), s.film_format)


def stamp_text(s: DevelopSettings, exif: dict | None) -> str:
    if not s.date_stamp:
        return ""
    if s.date_text.strip():
        return s.date_text.strip()
    d = (exif or {}).get("date")
    return d or ""


def date_in_margin(s: DevelopSettings, show_frame: bool = True) -> bool:
    """On a 120 strip the data back exposes the date into the film margin, not into the picture."""
    return frame_kind(s, show_frame) == "120"


def shooting_data(exif: dict | None) -> str:
    """'1/125 F5.6 50mm' from EXIF, like a medium-format data back."""
    ex = exif or {}
    parts = []
    et, fn, fl = ex.get("exposure"), ex.get("fnumber"), ex.get("focal")
    if et:
        parts.append(f"1/{round(1 / et)}" if et < 0.5 else f"{et:g}s")
    if fn:
        parts.append(f"F{fn:g}")
    if fl:
        parts.append(f"{fl:g}mm")
    return " ".join(parts)


def border_options(s: DevelopSettings, exif=None, show_frame: bool = True) -> tuple[str, dict, str]:
    """(frame kind, apply_border keyword arguments, date text to stamp into the picture)."""
    kind = frame_kind(s, show_frame)
    text = stamp_text(s, exif)
    margin = kind == "120"
    kw = dict(film_name=film_label(s), edge_text=s.border_text, frame_number=s.frame_number,
              film_kind=film_kind(s), film_key=s.film, film_format=s.film_format, holes=s.edge_holes,
              margin_date=text if margin else "", margin_data=shooting_data(exif) if margin and s.shoot_data else "")
    return kind, kw, ("" if margin else text)


def add_border(img: np.ndarray, s: DevelopSettings, *, exif=None, show_frame: bool | None = None) -> np.ndarray:
    """Date stamp (on the photo) then the film edge / frame. show_frame=None follows the preview setting."""
    from .borders import apply_border, date_stamp

    if show_frame is None:
        show_frame = PREFS["show_frame"]
    kind, kw, text = border_options(s, exif, show_frame)
    if text:
        img = date_stamp(img, text)
    return apply_border(img, kind, **kw)


# ------------------------------------------------------------------ engine

class _LRU(OrderedDict):
    def __init__(self, cap):
        super().__init__()
        self.cap = cap
        self.lock = threading.Lock()

    def get_(self, k):
        with self.lock:
            if k in self:
                self.move_to_end(k)
                return self[k]
        return None

    def put(self, k, v):
        with self.lock:
            self[k] = v
            self.move_to_end(k)
            while len(self) > self.cap:
                self.popitem(last=False)


class Engine:
    def __init__(self):
        install_speedups()
        self._proxies = _LRU(10)  # (path, lens) -> Source (as-shot, linear ProPhoto)
        self._decode_guard = threading.Lock()
        self._decoding: dict = {}
        self._wbimg = _LRU(4)  # (pkey, wb) -> image
        self._frames = _LRU(6)  # (wbkey, rotation/flip/straighten) -> frame
        self._geo = _LRU(6)  # (frame key, crop) -> {meter key: ev} and the cropped image
        self._tiers = _LRU(8)  # (geo key, size) -> working image (float64)
        self._negs = _LRU(8)
        self._sims = _LRU(8)  # (neg key, print settings) -> simulated print (float32, pre-finish)
        self._results = _LRU(48)  # complete key -> uint8 display image (+ info)
        self._originals = _LRU(6)
        self._full = _LRU(1)  # full-resolution frame for detail tiles
        self._thumbs = _LRU(96)
        self._thumb_work = _LRU(2)
        self.last_info: dict = {}

    # -- source & stages
    def proxy(self, path: str, s: DevelopSettings) -> Source:
        key = (path, bool(s.lens_correction) and is_raw(path))
        src = self._proxies.get_(key)
        if src is not None:
            return src
        with self._decode_guard:  # one decode per photo, whichever thread (preview / live / prefetch) asks
            lock = self._decoding.setdefault(key, threading.Lock())
        with lock:
            src = self._proxies.get_(key)
            if src is None:
                src = decode(path, key[1], PROXY_LONG_EDGE)
                src.auto = wb.neutralize(wb.auto_sample(src.image), src.as_shot)
                self._proxies.put(key, src)
        with self._decode_guard:
            self._decoding.pop(key, None)
        return src

    def prefetch(self, path: str, s: DevelopSettings):
        try:
            self.proxy(path, s)
        except Exception:
            pass

    @staticmethod
    def wb_target(s: DevelopSettings, src: Source) -> tuple[float, float]:
        return wb.target_for(s.wb_mode, s.temperature, s.tint, src.as_shot, src.auto)

    def _stages(self, path, s, src):
        pkey = (path, bool(s.lens_correction) and is_raw(path))
        target = self.wb_target(s, src)
        wkey = (pkey, round(target[0], 1), round(target[1], 2))
        img = self._wbimg.get_(wkey)
        if img is None:
            img = wb.apply_matrix(src.image, wb.adaptation_matrix(target, src.as_shot))
            self._wbimg.put(wkey, img)
        fkey = (wkey, s.rotation % 4, s.flip_h, s.flip_v, round(s.straighten, 3))
        frame = self._frames.get_(fkey)
        if frame is None:
            frame = frame_geometry(img, s)
            self._frames.put(fkey, frame)
        gkey = (fkey, geometry_key(s))
        geo = self._geo.get_(gkey)
        if geo is None:
            geo = {"img": crop_frame(frame, s), "ev": {}}
            self._geo.put(gkey, geo)
        mkey = s.subset(METER_FIELDS)
        if mkey not in geo["ev"]:
            geo["ev"][mkey] = meter(geo["img"], s)
        return gkey, frame, geo["img"], geo["ev"][mkey], target

    def _set_info(self, src, frame, geo, target, out_hw, s):
        from .borders import border_inset

        scale = src.full_size[0] / src.image.shape[1]
        h, w = out_hw
        l, t, _, _ = border_inset(frame_kind(s, PREFS["show_frame"]), w, h, s.film_format)
        fh, fw = frame.shape[:2]
        self.last_info = {
            "full_size": src.full_size,
            "frame_size": (round(fw * scale), round(fh * scale)),
            "crop_size": (round(geo.shape[1] * scale), round(geo.shape[0] * scale)),
            "crop_rect": effective_crop(s, fw, fh),
            "inset": (l, t, w, h), "image_size": (w, h),
            "as_shot": src.as_shot, "auto": src.auto, "wb": target, "raw": src.raw, "exif": src.exif,
            "note": src.note,
        }

    # -- previews
    def render(self, path: str, s: DevelopSettings, tier: str, long_edge: int = 1400,
               cancel=lambda: False) -> np.ndarray:
        """Returns a uint8 sRGB display image. tier: 'draft' | 'fine' | 'thumb'."""
        src = self.proxy(path, s)
        if cancel():
            raise RenderCancelled
        gkey, frame, geo, ev, target = self._stages(path, s, src)
        if tier == "thumb":
            return self._thumb(gkey, geo, ev, s)
        draft = tier == "draft"
        size = {"draft": DRAFT_LONG_EDGE, "thumb": THUMB_LONG_EDGE}.get(tier, int(min(max(long_edge, 800), FINE_MAX)))
        tkey = (gkey, size)
        work = self._tiers.get_(tkey)
        if work is None:
            work = resize_long_edge(geo, size).astype(np.float64)
            self._tiers.put(tkey, work)
        pixel_um = float(FILM_FORMATS.get(s.film_format, 36.0)) * 1000.0 / max(work.shape[:2])
        grain_on = not draft and (PREFS["always_grain"] or pixel_um <= GRAIN_VISIBLE_UM)
        nkey = (tkey, s.subset(FILM_FIELDS), round(ev, 4), draft, grain_on, effective_paper(s) == NO_PRINT)
        skey = (nkey, s.subset(PRINT_FIELDS))
        rkey = (skey, s.subset(FINISH_FIELDS), s.subset(BORDER_FIELDS), PREFS["show_frame"])
        hit = self._results.get_(rkey)
        if hit is not None:
            img, info = hit
            self.last_info = dict(info)
            return img
        sim_out = self._sims.get_(skey)
        if sim_out is None and is_digital(s):
            sim_out = digital_render(work * 2.0 ** (ev + s.exposure_ev))
            self._sims.put(skey, sim_out)
        if sim_out is None:
            sim = _simulator(s, draft=draft, grain=grain_on)
            neg = self._negs.get_(nkey)
            if neg is None:
                neg = _film_half(sim, work * (2.0 ** ev))
                self._negs.put(nkey, neg)
            if cancel():
                raise RenderCancelled
            sim_out = _print_half(sim, neg) if draft else fast_print(s, neg)
            self._sims.put(skey, sim_out)
        if cancel():
            raise RenderCancelled
        out = finishing.apply(sim_out, s)
        img = to_u8(add_border(out, s, exif=src.exif))
        self._set_info(src, frame, geo, target, out.shape[:2], s)
        self.last_info["grain_shown"] = grain_on
        self._results.put(rkey, (img, dict(self.last_info)))
        return img

    def _thumb(self, gkey, geo, ev, s):
        """Look thumbnails: own small caches so they never evict the main photo's stages."""
        key = (gkey, s.subset(FILM_FIELDS), s.subset(PRINT_FIELDS), s.subset(FINISH_FIELDS), round(ev, 4))
        hit = self._thumbs.get_(key)
        if hit is not None:
            return hit
        work = self._thumb_work.get_(gkey)
        if work is None:
            work = resize_long_edge(geo, THUMB_LONG_EDGE).astype(np.float64)
            self._thumb_work.put(gkey, work)
        if is_digital(s):
            out = digital_render(work * 2.0 ** (ev + s.exposure_ev))
        else:
            sim = _simulator(s, draft=True, grain=False)
            out = _print_half(sim, _film_half(sim, work * (2.0 ** ev)))
        img = to_u8(finishing.apply(out, s))
        self._thumbs.put(key, img)
        return img

    def strip_thumb(self, path: str, s: DevelopSettings, cancel=lambda: False) -> np.ndarray:
        """Processed filmstrip thumbnail of a photo that is not open: decoded small and kept out of the
        preview caches, so the open photo stays fast."""
        key = (path, bool(s.lens_correction) and is_raw(path))
        src = self._proxies.get_(key)
        if src is None:
            src = decode(path, False, 640)
            src.auto = wb.neutralize(wb.auto_sample(src.image), src.as_shot)
        if cancel():
            raise RenderCancelled
        img = wb.apply_matrix(src.image, wb.adaptation_matrix(self.wb_target(s, src), src.as_shot))
        geo = crop_frame(frame_geometry(img, s), s)
        work = resize_long_edge(np.ascontiguousarray(geo, np.float32), THUMB_LONG_EDGE).astype(np.float64)
        ev = meter(work, s)
        if cancel():
            raise RenderCancelled
        if is_digital(s):
            out = digital_render(work * 2.0 ** (ev + s.exposure_ev))
        else:
            sim = _simulator(s, draft=True, grain=False)
            out = _print_half(sim, _film_half(sim, work * (2.0 ** ev)))
        return to_u8(finishing.apply(out, s))

    def render_uncropped(self, path, s, tier, long_edge, cancel=lambda: False):
        """Processed frame without crop or border — for the crop tool."""
        u = s.copy()
        u.crop_l, u.crop_t, u.crop_r, u.crop_b, u.aspect, u.border = 0.0, 0.0, 1.0, 1.0, "Free", "none"
        u.date_stamp = False
        img = self.render(path, u, tier, long_edge, cancel)
        return img

    def original_display(self, path: str, s: DevelopSettings, long_edge: int) -> np.ndarray:
        """The photo as shot (camera WB, no film), with the current framing and border."""
        size = int(min(max(long_edge, 800), FINE_MAX))
        key = (path, bool(s.lens_correction), geometry_key(s), s.subset(BORDER_FIELDS), s.film,
               s.film_format, PREFS["show_frame"], size)
        hit = self._originals.get_(key)
        if hit is not None:
            return hit
        src = self.proxy(path, s)
        geo = apply_geometry(src.image, s)
        disp = working_to_display(resize_long_edge(geo, size))
        framed = frame_kind(s, PREFS["show_frame"]) != "none" or s.date_stamp
        img = to_u8(add_border(disp.astype(np.float32) / 255.0, s, exif=src.exif)) if framed else disp
        self._originals.put(key, img)
        return img

    def sample_wb(self, path: str, s: DevelopSettings, u: float, v: float) -> tuple[float, float]:
        """Eyedropper: Kelvin/tint that make the as-shot pixel at (u, v) of the photo neutral."""
        src = self.proxy(path, s)
        geo = apply_geometry(src.image, s)
        h, w = geo.shape[:2]
        x, y = int(min(max(u, 0), 0.999) * w), int(min(max(v, 0), 0.999) * h)
        r = max(2, int(0.004 * max(w, h)))
        patch = geo[max(0, y - r):y + r + 1, max(0, x - r):x + r + 1].reshape(-1, 3).mean(axis=0)
        return wb.neutralize(patch, src.as_shot)

    # -- full-resolution detail
    def detail(self, path: str, s: DevelopSettings, rect, cancel=lambda: False):
        """Render a full-resolution tile. rect = (x, y, w, h) as fractions of the framed photo.
        Returns (uint8 tile, (x0, y0, x1, y1) in full-res pixels of the photo, (W, H))."""
        src = self.proxy(path, s)
        _, _, gproxy, ev, target = self._stages(path, s, src)
        fkey = (path, bool(s.lens_correction), round(target[0], 1), round(target[1], 2), geometry_key(s))
        full = self._full.get_(fkey)
        if full is None:
            self._full.clear()
            fsrc = decode(path, bool(s.lens_correction) and is_raw(path), None)
            if cancel():
                raise RenderCancelled
            img = wb.apply_matrix(fsrc.image, wb.adaptation_matrix(target, fsrc.as_shot))
            full = apply_geometry(img, s)
            del img, fsrc
            self._full.put(fkey, full)
        H, W = full.shape[:2]
        x, y, w, h = rect
        x0, y0 = max(0, int(x * W)), max(0, int(y * H))
        x1, y1 = min(W, int(math.ceil((x + w) * W))), min(H, int(math.ceil((y + h) * H)))
        if x1 - x0 < 8 or y1 - y0 < 8:
            return None
        px0, py0 = max(0, x0 - DETAIL_PAD), max(0, y0 - DETAIL_PAD)
        px1, py1 = min(W, x1 + DETAIL_PAD), min(H, y1 + DETAIL_PAD)
        tile_in = full[py0:py1, px0:px1].astype(np.float64) * (2.0 ** ev)
        scale = max(tile_in.shape[:2]) / max(W, H)
        if is_digital(s):
            out = digital_render(tile_in * 2.0 ** s.exposure_ev)
        else:
            sim = _simulator(s, film_format_scale=scale)
            if cancel():
                raise RenderCancelled
            out = fast_print(s, _film_half(sim, tile_in))
        out = finishing.apply(out, s, frame=(px0, py0, W, H))
        text = stamp_text(s, read_exif(path))
        if text and not date_in_margin(s, PREFS["show_frame"]):
            from .borders import date_stamp

            out = date_stamp(out, text, frame=(px0, py0, W, H))
        out = out[y0 - py0:y0 - py0 + (y1 - y0), x0 - px0:x0 - px0 + (x1 - x0)]
        return to_u8(out), (x0, y0, x1, y1), (W, H)

    def drop_full(self):
        self._full.clear()

    def clear(self):
        for c in (self._proxies, self._wbimg, self._frames, self._geo, self._tiers, self._negs, self._sims,
                  self._results, self._originals, self._full):
            c.clear()


# ------------------------------------------------------------------ export

BAND_PIXELS = 8_000_000


def _free_ram_gb() -> float:
    try:
        import ctypes

        class MEMSTAT(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        m = MEMSTAT()
        m.dwLength = ctypes.sizeof(MEMSTAT)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.ullAvailPhys / 2 ** 30
    except Exception:
        return 0.0


def _threadsafe_numba() -> bool:
    try:
        import numba

        return numba.threading_layer() in ("omp", "tbb")
    except Exception:
        return False


FILM_BAND_GB = 2.6  # peak memory of one 8 MP band of the film half (float64 spektrafilm intermediates)


def band_workers() -> int:
    """Film bands developed at once: as many as free memory and cores allow (up to 4)."""
    if not _threadsafe_numba():
        return 1
    cores = os.cpu_count() or 4
    by_ram = int((_free_ram_gb() - 2.0) // FILM_BAND_GB)
    return max(1, min(4, by_ram, max(1, cores // 4)))


def _overlap_px(s: DevelopSettings, pixel_um: float) -> int:
    # halation: widest bounce sigma ~113 µm (5σ < 600 µm); DIR-coupler tail 200 µm decays to e^-3 at 600 µm
    reach_um = 600.0
    if s.diffusion:
        reach_um = max(reach_um, 2000.0)
    return int(math.ceil(reach_um / max(pixel_um, 1e-6))) + 8


def render_full(path: str, s: DevelopSettings, *, output_color_space: str = "sRGB",
                long_edge: int | None = None, progress=None, cancel=lambda: False,
                include_frame: bool = True) -> np.ndarray:
    """Full-quality export render, metered exactly like the preview; large images in overlapping bands."""
    install_speedups()
    configure_thread()
    src = decode(path, bool(s.lens_correction) and is_raw(path), None)
    src_exif = src.exif
    proxy_img = resize_long_edge(src.image, PROXY_LONG_EDGE)
    proxy_auto = wb.neutralize(wb.auto_sample(proxy_img), src.as_shot)
    target = wb.target_for(s.wb_mode, s.temperature, s.tint, src.as_shot, proxy_auto)
    m = wb.adaptation_matrix(target, src.as_shot)
    ev = meter(apply_geometry(wb.apply_matrix(proxy_img, m), s), s)
    del proxy_img
    g = apply_geometry(wb.apply_matrix(src.image, m), s)
    src.image = None
    if long_edge:
        g = resize_long_edge(g, long_edge)
    H, W = g.shape[:2]
    gain = 2.0 ** ev
    if is_digital(s):  # no film: no spatial effects, render in one go
        if progress:
            progress(0.0)
        out = digital_render(g * np.float32(gain * 2.0 ** s.exposure_ev), output_color_space)
        out = finishing.apply(out, s, color_space=output_color_space)
        if progress:
            progress(1.0)
        return add_border(out, s, exif=src_exif, show_frame=include_frame)
    if progress:
        progress(0.0)
    neg = develop_full(g, s, gain, output_color_space=output_color_space, cancel=cancel,
                       progress=(lambda f: progress(0.02 + 0.83 * f)) if progress else None)
    del g
    out = print_full(neg, s, output_color_space=output_color_space, cancel=cancel,
                     progress=(lambda f: progress(0.85 + 0.15 * f)) if progress else None)
    del neg
    return add_border(out, s, exif=src_exif, show_frame=include_frame)


def develop_full(g: np.ndarray, s: DevelopSettings, gain: float, *, output_color_space: str = "sRGB",
                 cancel=lambda: False, progress=None, workers: int | None = None) -> np.ndarray:
    """The film half (exposure, halation, DIR couplers, grain, development) of a full-resolution frame,
    exactly as spektrafilm computes it, in overlapping bands developed in parallel. Returns the negative's
    dye densities, float32 HxWx3."""
    from spektrafilm.runtime.topology import Tap

    H, W = g.shape[:2]
    film_mm = float(FILM_FORMATS.get(s.film_format, 36.0))
    pad = _overlap_px(s, film_mm * 1000.0 / max(H, W))
    band = max(64, BAND_PIXELS // W - 2 * pad)
    if band >= H:
        band, pad = H, 0
    plant = None
    if s.highlight_boost > 0:  # boost normalises by the image-wide maximum: share the brightest pixels
        flat = g.reshape(-1, 3)
        idx = {int(np.argmax(flat[:, c])) for c in range(3)} | {int(np.argmax(flat.sum(1)))}
        plant = flat[sorted(idx)].astype(np.float64) * gain
    neg = np.empty((H, W, 3), np.float32)
    starts = list(range(0, H, band))
    workers = max(1, min(workers or band_workers(), len(starts)))
    sims: dict = {}  # one simulator per worker thread, reused for all of its bands
    done = [0]
    lock = threading.Lock()

    def one(y0):
        if cancel():
            raise RenderCancelled
        tid = threading.get_ident()
        if tid not in sims:
            try:
                import numba

                n = numba.config.NUMBA_NUM_THREADS
                numba.set_num_threads(max(2, (n - 2) // workers) if n > 4 else n)
            except Exception:
                pass
            sim = _simulator(s, output_color_space=output_color_space)
            sims[tid] = (sim, sim._pipeline._resize_service.film_format_mm)
        sim, base_mm = sims[tid]
        y1 = min(H, y0 + band)
        py0, py1 = max(0, y0 - pad), min(H, y1 + pad)
        tile = g[py0:py1].astype(np.float64) * gain
        if plant is not None:
            row = 0 if py0 < y0 else tile.shape[0] - 1
            if row == 0 or py1 > y1:
                tile[row, :len(plant)] = plant
        # same physical pixel size for every band: spektrafilm derives it from the frame's long edge
        sim._pipeline._resize_service.film_format_mm = base_mm * max(tile.shape[:2]) / max(H, W)
        dens = sim._pipeline.process(tile, collect=Tap.CMY_FILM)
        neg[y0:y1] = dens[y0 - py0:y0 - py0 + (y1 - y0)]
        del dens, tile
        with lock:
            done[0] += 1
            if progress:
                progress(done[0] / len(starts))

    if workers == 1:
        for y0 in starts:
            one(y0)
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(one, starts))
    return neg


def print_full(neg: np.ndarray, s: DevelopSettings, *, output_color_space: str = "sRGB", cancel=lambda: False,
               progress=None) -> np.ndarray:
    """Enlarger, paper, scanner (fastprint) and finishing of a developed negative, in row chunks."""
    from . import fastprint

    printer = fastprint.printer_for(s, output_color_space)
    H, W = neg.shape[:2]
    pad = 8 + (int(3 * finishing.CLARITY_SIGMA * max(H, W)) if s.clarity else 0)
    chunk = max(64, 4_000_000 // W)
    starts = list(range(0, H, chunk))
    out = np.empty((H, W, 3), np.float32)
    done = [0]
    lock = threading.Lock()

    def one(y0):
        if cancel():
            raise RenderCancelled
        y1 = min(H, y0 + chunk)
        py0, py1 = max(0, y0 - pad), min(H, y1 + pad)
        res = printer.apply(neg[py0:py1])
        res = finishing.apply(res, s, color_space=output_color_space, frame=(0, py0, W, H))
        out[y0:y1] = res[y0 - py0:y0 - py0 + (y1 - y0)]
        with lock:
            done[0] += 1
            if progress:
                progress(done[0] / len(starts))

    if len(starts) == 1 or not _threadsafe_numba():  # concurrent numba kernels need the omp / tbb layer
        for y0 in starts:
            one(y0)
    else:
        with ThreadPoolExecutor(max_workers=min(4, len(starts))) as ex:
            list(ex.map(one, starts))
    return out


# ------------------------------------------------------------------ saving

def save_image(path: str, rgb: np.ndarray, *, color_space: str, fmt: str, quality: int = 95,
               bit_depth: int = 16) -> None:
    ext = os.path.splitext(path)[1].lower()
    if fmt == "jpeg" or ext in (".jpg", ".jpeg"):
        from PIL import Image
        from spektrafilm.utils.io import _load_icc_profile

        data = (np.clip(rgb, 0, 1) * 255.0 + 0.5).astype(np.uint8)
        icc = None
        try:
            icc = _load_icc_profile(color_space, True)
        except Exception:
            pass
        kw = {"quality": int(quality), "subsampling": 0 if quality >= 90 else 2, "optimize": True}
        if icc:
            kw["icc_profile"] = icc
        Image.fromarray(data, "RGB").save(path, "JPEG", **kw)
        return
    from spektrafilm.utils.io import save_image_oiio

    save_image_oiio(path, rgb, bit_depth=bit_depth, color_space=color_space, cctf_encoding=True)


# ------------------------------------------------------------------ thumbnails

def thumbnail(path: str, size: int = 256) -> np.ndarray | None:
    """Fast thumbnail as uint8 sRGB HxWx3 (embedded JPEG for RAW files)."""
    import io

    from PIL import Image, ImageOps

    try:
        if is_raw(path):
            import rawpy

            with rawpy.imread(path) as raw:
                try:
                    th = raw.extract_thumb()
                    if th.format == rawpy.ThumbFormat.JPEG:
                        im = ImageOps.exif_transpose(Image.open(io.BytesIO(th.data)))
                    else:
                        im = Image.fromarray(th.data)
                except Exception:
                    im = Image.fromarray(raw.postprocess(half_size=True, use_camera_wb=True, output_bps=8))
        else:
            im = ImageOps.exif_transpose(Image.open(path))
        im = im.convert("RGB")
        im.thumbnail((size, size), Image.Resampling.LANCZOS)
        return np.asarray(im)
    except Exception:
        try:
            arr = _load_image(path)
            return working_to_display(resize_long_edge(to_working(arr, "sRGB", True), size))
        except Exception:
            return None
