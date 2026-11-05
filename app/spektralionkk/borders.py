"""Film Edge (the film strip around the picture), the date back, and print borders.

The strip is drawn to scale in millimetres of real film: 135 is 35 mm wide around a 24 mm picture with
Kodak-standard perforations (1.98 x 2.79 mm, 4.75 mm pitch, 2 mm from the edge) and the stock's edge print
outside them; 120 is 61.5 mm wide around a 56 mm picture with the edge print in its 2.75 mm rebate. Sizes
follow the picture, so the frame looks the same in the preview, at 100 % and in a full-resolution export.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .settings import FORMAT_GATES

REBATE = (12, 11, 10)
HOLE_WHITE = (246, 245, 241)
HOLE_BLACK = (2, 2, 2)
REBATE_UNDER_BLACK_HOLES = (24, 23, 21)
PAPER_WHITE = (246, 244, 239)
MOUNT = (214, 211, 204)  # slide mount plastic
DATE_ORANGE = (255, 138, 36)

# stock -> (135 edge print, 120 edge print, brand, style)
EDGE_PRINT = {
    "kodak_ektar_100": ("KODAK EKTAR 100", "EKTAR 100", "KODAK", "kodak"),
    "kodak_portra_160": ("KODAK PORTRA 160", "PORTRA 160", "KODAK", "kodak"),
    "kodak_portra_400": ("KODAK PORTRA 400", "PORTRA 400", "KODAK", "kodak"),
    "kodak_portra_800": ("KODAK PORTRA 800", "PORTRA 800", "KODAK", "kodak"),
    "kodak_portra_800_push1": ("KODAK PORTRA 800", "PORTRA 800", "KODAK", "kodak"),
    "kodak_portra_800_push2": ("KODAK PORTRA 800", "PORTRA 800", "KODAK", "kodak"),
    "kodak_gold_200": ("KODAK GOLD 200", "GOLD 200", "KODAK", "kodak"),
    "kodak_ultramax_400": ("KODAK ULTRAMAX 400", "UMAX 400", "KODAK", "kodak"),
    "kodak_verita_200d": ("KODAK VERITA 200D", "VERITA 200D", "KODAK", "kodak"),
    "kodak_vision3_50d": ("EASTMAN 5203", "5203", "EASTMAN", "eastman"),
    "kodak_vision3_250d": ("EASTMAN 5207", "5207", "EASTMAN", "eastman"),
    "kodak_vision3_200t": ("EASTMAN 5213", "5213", "EASTMAN", "eastman"),
    "kodak_vision3_500t": ("EASTMAN 5219", "5219", "EASTMAN", "eastman"),
    "cinestill_800t": ("CINESTILL 800T", "800T", "CINESTILL", "eastman"),
    "fujifilm_pro_400h": ("PRO400H", "PRO400H", "FUJI", "fuji"),
    "fujifilm_c200": ("FUJICOLOR C200", "C200", "FUJI", "fuji"),
    "fujifilm_xtra_400": ("X-TRA400", "S-400", "FUJI", "fuji"),
    "kodak_ektachrome_100": ("KODAK E100", "E100", "KODAK", "kodak_slide"),
    "kodak_kodachrome_64": ("KODACHROME 64", "KR 64", "KODAK", "kodak_slide"),
    "fujifilm_velvia_100": ("RVP100", "RVP100", "FUJI", "fuji_slide"),
    "fujifilm_provia_100f": ("RDPIII", "RDPIII", "FUJI", "fuji_slide"),
    "fujifilm_neopan_acros_100_ii": ("NEOPAN ACROS II", "ACROS II", "FUJI", "fuji_bw"),
    "ilford_hp5_plus_400": ("ILFORD HP5 PLUS", "HP5 PLUS", "ILFORD", "bw"),
    "kodak_tmax_100": ("KODAK 100TMX", "100TMX", "KODAK", "bw"),
    "kodak_tri_x_400": ("KODAK 400TX", "400TX", "KODAK", "bw"),
}
# Film Edge lettering of looks that are not a film stock (the camera-inspired looks): the look's own name, not
# the stock it happens to be built on. key (settings.edge_label) -> (135 text, 120 text, style, mark);
# mark "red_name" sets the first word in red. Plain lettering in the app's own font, not a maker's logo.
LOOK_EDGES = {
    "positive_film": ("POSITIVE FILM", "POSITIVE FILM", "kodak_slide", ""),
    "negative_film": ("NEGATIVE FILM", "NEGATIVE FILM", "kodak", ""),
    "leica_classic": ("LEICA CLASSIC", "LEICA CLASSIC", "leica", "red_name"),
    "leica_contemporary": ("LEICA CONTEMPORARY", "LEICA CONTEMPORARY", "leica", "red_name"),
    "leica_eternal": ("LEICA ETERNAL", "LEICA ETERNAL", "leica", "red_name"),
    "leica_monochrome": ("LEICA MONOCHROME", "LEICA MONOCHROME", "leica", "red_name"),
    "chrome_classic": ("CHROME CLASSIC", "CHROME CLASSIC", "fuji_slide", ""),
    "neg_classic": ("NEG CLASSIC", "NEG CLASSIC", "fuji", ""),
    "eterna": ("ETERNA 250D", "ETERNA 250D", "fuji_cine", ""),
}
ACCENT_RED = (214, 28, 38)
EDGE_COLOR = {"kodak": (255, 146, 54), "kodak_slide": (255, 212, 118), "fuji": (255, 184, 44),
              "fuji_slide": (255, 158, 58), "eastman": (150, 196, 245), "bw": (224, 222, 216),
              "fuji_bw": (224, 222, 216), "leica": (238, 235, 228), "fuji_cine": (150, 196, 245)}
EDGE_FONT = {"kodak": "kodak", "kodak_slide": "kodak", "bw": "kodak", "fuji": "fuji", "fuji_slide": "fuji",
             "fuji_bw": "fuji", "eastman": "fuji", "leica": "kodak", "fuji_cine": "fuji"}
CINE_STYLES = ("eastman", "fuji_cine")  # motion-picture stock: small lettering, one mark

# strip geometry (mm): film width, picture height across the film, extra film shown beyond each frame end
STRIP = {"135": (35.0, 24.0, 1.6), "120": (61.5, 56.0, 3.0)}


def resolve_kind(kind: str, film_kind: str, film_format: str) -> str:
    """'auto' = Film strip: the 135 or 120 strip of the chosen format (a filed carrier for sheet film).
    Other styles are used as they are."""
    if not kind or kind == "none":
        return "none"
    if kind in ("auto", "135", "120"):
        family = FORMAT_GATES.get(film_format, FORMAT_GATES["135 (24×36)"])[0]
        return family if family in STRIP else "filed"
    return kind


def edge_style(film_key: str, film_name: str, film_kind: str, edge_label: str = ""):
    """(135 text, 120 text, brand, colour, font kind, style, mark) of the edge print: a look's own lettering
    (LOOK_EDGES) when it has one, else the stock's."""
    look = LOOK_EDGES.get(edge_label or "")
    if look:
        t135, t120, style, mark = look
        return t135, t120, t120, EDGE_COLOR[style], EDGE_FONT[style], style, mark
    ent = EDGE_PRINT.get(film_key)
    if film_kind == "digital":  # no stock to name: perforations, frame numbers and DX code only
        ent = ("", "", "", "kodak")
    elif ent is None:
        name = (film_name or "").upper()
        style = "bw" if film_kind == "bw" else ("kodak_slide" if film_kind == "positive" else "kodak")
        ent = (name, name, name.split(" ")[0] if name else "", style)
    t135, t120, brand, style = ent
    return t135, t120, brand, EDGE_COLOR[style], EDGE_FONT[style], style, ""


# ------------------------------------------------------------------ date back

def date_stamp(img, text: str, frame=None):
    """Classic camera date-back imprint (orange LED digits, slightly glowing) near the bottom-right of the
    photo. frame = (x0, y0, W, H): this image's offset inside the whole photo (for 100% detail tiles)."""
    if not text:
        return img
    u8 = img.dtype == np.uint8
    arr = img if u8 else (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)
    h, w = arr.shape[:2]
    x0, y0, W, H = frame if frame else (0, 0, w, h)
    size = max(8.0, min(W, H) * 0.045)  # digit height
    font = _mono_font(round(size * 1.25))
    layer = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(layer)
    tw = _seg_width(text, size, d, font)
    x = W - tw - min(W, H) * 0.06 - x0
    y = H - size - min(W, H) * 0.06 - y0
    if x + tw < 0 or y + size * 1.4 < 0 or x > w or y > h:  # the stamp is outside this tile
        return img
    _seg_draw(d, text, x, y, size, font)
    out = _glow_onto(arr.astype(np.float32) / 255.0, layer, size)
    return (out * 255 + 0.5).astype(np.uint8) if u8 else out.astype(np.float32)


def _glow_onto(base: np.ndarray, layer: Image.Image, size: float) -> np.ndarray:
    """Screen-blend an orange LED exposure (with its glow) from an 'L' mask onto a float RGB image."""
    core = np.asarray(layer.filter(ImageFilter.GaussianBlur(max(0.4, size * 0.03))), np.float32) / 255.0
    glow = np.asarray(layer.filter(ImageFilter.GaussianBlur(max(1.0, size * 0.25))), np.float32) / 255.0
    col = np.array(DATE_ORANGE, np.float32) / 255.0
    add = (core * 0.95 + glow * 0.55)[..., None] * col  # light added to the print (screen blend)
    return 1.0 - (1.0 - base) * (1.0 - np.clip(add, 0, 1))


# 7-segment LED digits, slanted like a camera date back.
_SEGS = {"0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd", "6": "afgedc",
         "7": "abc", "8": "abcdefg", "9": "abcdfg", "-": "g"}
_SLANT = 0.12


def _seg_advance(ch, size, d, font):
    if ch in _SEGS:
        return size * 0.80
    if ch == " ":
        return size * 0.45
    if ch in "'.:":
        return size * 0.30
    return d.textlength(ch, font=font) + size * 0.12


def _seg_width(text, size, d, font):
    return sum(_seg_advance(c, size, d, font) for c in text) + size * _SLANT


def _seg_draw(d, text, x, y, size, font):
    t = size * 0.14  # stroke
    hw, gap = t / 2, t * 0.18
    cw = size * 0.56  # cell width

    def slant(pts):
        return [(px + (y + size - py) * _SLANT, py) for px, py in pts]

    def hseg(xa, xb, yc):
        return [(xa + gap, yc), (xa + gap + hw, yc - hw), (xb - gap - hw, yc - hw), (xb - gap, yc),
                (xb - gap - hw, yc + hw), (xa + gap + hw, yc + hw)]

    def vseg(xc, ya, yb):
        return [(xc, ya + gap), (xc + hw, ya + gap + hw), (xc + hw, yb - gap - hw), (xc, yb - gap),
                (xc - hw, yb - gap - hw), (xc - hw, ya + gap + hw)]

    for ch in text:
        if ch in _SEGS:
            xl, xr = x + hw, x + cw - hw
            yt, ym, yb = y + hw, y + size / 2, y + size - hw
            shapes = {"a": hseg(xl, xr, yt), "g": hseg(xl, xr, ym), "d": hseg(xl, xr, yb),
                      "f": vseg(xl, yt, ym), "b": vseg(xr, yt, ym), "e": vseg(xl, ym, yb), "c": vseg(xr, ym, yb)}
            for sname in _SEGS[ch]:
                d.polygon(slant(shapes[sname]), fill=255)
        elif ch == "'":
            d.polygon(slant(vseg(x + hw * 2, y, y + size * 0.42)), fill=255)
        elif ch in ".:":
            dots = (y + size - t, ) if ch == "." else (y + size * 0.25, y + size * 0.7)
            for dy in dots:
                d.polygon(slant([(x + hw, dy), (x + hw + t, dy), (x + hw + t, dy + t), (x + hw, dy + t)]), fill=255)
        elif ch != " ":
            d.text((x, y + size), ch, font=font, fill=255, anchor="ls")
        x += _seg_advance(ch, size, d, font)


# ------------------------------------------------------------------ fonts

# Windows font file -> the same face (or the closest) on macOS and Linux
_FONT_ALIASES = {
    "arialbd.ttf": ("Arial Bold.ttf", "LiberationSans-Bold.ttf", "DejaVuSans-Bold.ttf"),
    "arial.ttf": ("Arial.ttf", "LiberationSans-Regular.ttf", "DejaVuSans.ttf"),
    "segoeuib.ttf": ("Arial Bold.ttf", "DejaVuSans-Bold.ttf"),
    "segoeui.ttf": ("Arial.ttf", "DejaVuSans.ttf"),
    "bahnschrift.ttf": ("DIN Condensed Bold.ttf", "DIN Alternate Bold.ttf", "DejaVuSansCondensed-Bold.ttf"),
    "consolab.ttf": ("Courier New Bold.ttf", "DejaVuSansMono-Bold.ttf"),
    "courbd.ttf": ("Courier New Bold.ttf",),
}
_BUNDLED_FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "fonts")


def _font_dirs():
    if sys.platform.startswith("win"):
        return [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")]
    if sys.platform == "darwin":
        return ["/System/Library/Fonts/Supplemental", "/System/Library/Fonts", "/Library/Fonts",
                os.path.expanduser("~/Library/Fonts")]
    return ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype/liberation", "/usr/share/fonts/TTF",
            os.path.expanduser("~/.local/share/fonts")]


@lru_cache(maxsize=32)
def _font_file(*names, bold: bool = True):
    """The first of these fonts found on this system (Windows names, mapped to their macOS / Linux equivalents);
    the bundled Inter when none is installed."""
    for name in names:
        for cand in (name,) + _FONT_ALIASES.get(name, ()):
            for d in _font_dirs():
                p = os.path.join(d, cand)
                if os.path.exists(p):
                    return p
    p = os.path.join(_BUNDLED_FONTS, "Inter-Bold.ttf" if bold else "Inter-Regular.ttf")
    return p if os.path.exists(p) else None


@lru_cache(maxsize=8)
def _mono_font(px: int):
    p = _font_file("consolab.ttf", "courbd.ttf", "lucon.ttf")
    if p:
        try:
            return ImageFont.truetype(p, max(6, px))
        except OSError:
            pass
    return _font(px)


@lru_cache(maxsize=16)
def _font(px: int, bold=True):
    p = _font_file(*(("arialbd.ttf", "segoeuib.ttf") if bold else ("arial.ttf", "segoeui.ttf")), bold=bold)
    if p:
        try:
            return ImageFont.truetype(p, max(6, px))
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=max(6, px))
    except TypeError:
        return ImageFont.load_default()


@lru_cache(maxsize=32)
def _edge_font(kind: str, cap_px: int):
    """A font whose capital letters are cap_px tall: a bold grotesque for Kodak / Ilford, a narrow DIN-style
    face for Fujifilm and Eastman cine stock."""
    p = _font_file("bahnschrift.ttf", "arialbd.ttf") if kind == "fuji" else _font_file("arialbd.ttf",
                                                                                         "segoeuib.ttf")
    try:
        ref = ImageFont.truetype(p, 100) if p else None
    except OSError:
        ref = None
    if ref is None:
        return _font(max(6, round(cap_px / 0.72)))
    if kind == "fuji":
        try:
            ref.set_variation_by_axes([600, 75])  # Bahnschrift: semibold, condensed
        except Exception:
            pass
    x0, y0, x1, y1 = ref.getbbox("H")
    ratio = max(1, y1 - y0) / 100.0
    f = ImageFont.truetype(p, max(6, round(cap_px / ratio)))
    if kind == "fuji":
        try:
            f.set_variation_by_axes([600, 75])
        except Exception:
            pass
    return f


# ------------------------------------------------------------------ geometry

def strip_layout(kind: str, w: int, h: int, film_format: str):
    """For a 135 / 120 strip around a w x h picture: (horizontal, px per mm, rebate px, end margin px)."""
    family = "135" if kind == "135" else "120"
    _, along, across = FORMAT_GATES.get(film_format, FORMAT_GATES["135 (24×36)" if family == "135" else "6×7"])
    if FORMAT_GATES.get(film_format, ("",))[0] != family:  # style forced on a format of the other film
        along, across = (36.0, 24.0) if family == "135" else (69.5, 56.0)
    horizontal = (w >= h) == (along >= across) if along != across else True
    width_mm, pic_mm, end_mm = STRIP[family]
    across_px = h if horizontal else w
    px_mm = across_px / pic_mm
    rebate = round((width_mm - pic_mm) / 2 * px_mm)
    end = round(end_mm * px_mm)
    return horizontal, px_mm, rebate, end


def border_inset(kind: str, w: int, h: int, film_format: str = "135 (24×36)") -> tuple[int, int, int, int]:
    """(left, top, right, bottom) border sizes in pixels for a picture of w x h."""
    short, long_ = min(w, h), max(w, h)
    if kind in ("135", "120"):
        horizontal, _, rebate, end = strip_layout(kind, w, h, film_format)
        return (end, rebate, end, rebate) if horizontal else (rebate, end, rebate, end)
    if kind == "filed":
        b = round(short * 0.045)
        return (b, b, b, b)
    if kind == "slide":  # 50 mm square mount around the picture
        side = round(long_ * 50.0 / 35.0)
        lx, ty = (side - w) // 2, (side - h) // 2
        return (lx, ty, side - w - lx, side - h - ty)
    if kind == "white_thin":
        b = round(short * 0.035)
        return (b, b, b, b)
    if kind == "white_wide":
        b = round(short * 0.10)
        return (b, b, b, round(b * 1.6))
    return (0, 0, 0, 0)


# ------------------------------------------------------------------ compositing

def apply_border(rgb: np.ndarray, kind: str, *, film_name: str = "", edge_text: bool = True,
                 frame_number: int = 12, film_kind: str = "negative", film_key: str = "",
                 film_format: str = "135 (24×36)", holes: str = "white", margin_date: str = "",
                 margin_data: str = "", edge_label: str = "") -> np.ndarray:
    """rgb: float HxWx3 in [0,1] (any display encoding). Returns a new, larger float32 image.
    margin_date / margin_data: date-back text exposed into a 120 strip's lower rebate.
    edge_label: a look's own lettering (LOOK_EDGES) instead of the stock's."""
    if not kind or kind == "none":
        return rgb
    if kind in ("135", "120"):
        return _strip(rgb, kind, film_name=film_name, edge_text=edge_text, frame_number=frame_number,
                      film_kind=film_kind, film_key=film_key, film_format=film_format, holes=holes,
                      margin_date=margin_date, margin_data=margin_data, edge_label=edge_label)
    h, w = rgb.shape[:2]
    l, t, r, b = border_inset(kind, w, h, film_format)
    W, H = w + l + r, h + t + b
    photo = Image.fromarray((np.clip(rgb, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB")

    if kind == "slide":
        canvas = Image.new("RGB", (W, H), MOUNT)
        d = ImageDraw.Draw(canvas)
        short = min(W, H)
        # subtle moulded bevel around the window, then the photo with softly rounded corners
        bev = max(2, round(short * 0.012))
        d.rounded_rectangle([l - bev, t - bev, l + w + bev - 1, t + h + bev - 1], radius=bev * 2,
                            fill=(196, 193, 186))
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=max(2, round(short * 0.01)), fill=255)
        canvas.paste(photo, (l, t), mask)
        if edge_text:
            fs = max(7, round(short * 0.028))
            font = _font(fs, bold=False)
            look = LOOK_EDGES.get(edge_label or "")
            label = look[0] if look else (film_name or "").upper()
            x = W / 2 - d.textlength(label, font=font) / 2
            y = t + h + (H - t - h) * 0.42 - fs / 2
            if look and look[3] == "red_name" and " " in label:  # the look's first word in red
                first, label = label.split(" ", 1)
                d.text((x, y), first + " ", font=font, fill=ACCENT_RED)
                x += d.textlength(first + " ", font=font)
            d.text((x, y), label, font=font, fill=(120, 117, 110))
            num = f"{frame_number:02d}"
            d.text((W / 2 - d.textlength(num, font=font) / 2, t * 0.5 - fs / 2), num, font=font, fill=(120, 117, 110))
        return np.asarray(canvas, dtype=np.float32) / 255.0

    if kind in ("white_thin", "white_wide"):
        canvas = Image.new("RGB", (W, H), PAPER_WHITE)
        canvas.paste(photo, (l, t))
        if kind == "white_wide":  # a hairline keyline around the photo
            d = ImageDraw.Draw(canvas)
            k = max(1, round(min(w, h) * 0.0015))
            d.rectangle([l - 2 * k, t - 2 * k, l + w + 2 * k - 1, t + h + 2 * k - 1], outline=(70, 68, 64), width=k)
            canvas.paste(photo, (l, t))
        return np.asarray(canvas, dtype=np.float32) / 255.0

    # filed-out negative carrier: rough, slightly wavy black frame line
    canvas = Image.new("RGB", (W, H), REBATE)
    rng = np.random.default_rng(7)
    mask = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(mask)
    jitter = max(1, round(min(w, h) * 0.006))
    pts = []
    steps = 90
    for i in range(steps):
        pts.append((l + w * i / steps, t + rng.integers(-jitter, jitter + 1)))
    for i in range(steps):
        pts.append((l + w + rng.integers(-jitter, jitter + 1), t + h * i / steps))
    for i in range(steps):
        pts.append((l + w - w * i / steps, t + h + rng.integers(-jitter, jitter + 1)))
    for i in range(steps):
        pts.append((l + rng.integers(-jitter, jitter + 1), t + h - h * i / steps))
    d.polygon(pts, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(max(0.6, jitter * 0.4)))
    big = Image.new("RGB", (W, H), REBATE)
    big.paste(photo, (l, t))
    canvas = Image.composite(big, canvas, mask)
    return np.asarray(canvas, dtype=np.float32) / 255.0


def _strip(rgb, kind, *, film_name, edge_text, frame_number, film_kind, film_key, film_format, holes,
           margin_date, margin_data, edge_label=""):
    h0, w0 = rgb.shape[:2]
    horizontal, px, rebate, end = strip_layout(kind, w0, h0, film_format)
    pic = np.clip(rgb, 0, 1)
    if not horizontal:  # draw a horizontal strip, then turn it back
        pic = np.rot90(pic, k=-1)
    h, w = pic.shape[:2]
    W, H = w + 2 * end, h + 2 * rebate
    black_holes = kind == "135" and holes == "black"
    canvas = Image.new("RGB", (W, H), REBATE_UNDER_BLACK_HOLES if black_holes else REBATE)
    d = ImageDraw.Draw(canvas)
    style = edge_style(film_key, film_name, film_kind, edge_label)

    if kind == "135":
        # perforations: 1.98 mm along x 2.79 mm across, 4.75 mm pitch, outer edge 2.01 mm from the film edge
        pitch, hw, hh, edge = 4.75 * px, 1.98 * px, 2.79 * px, 2.01 * px
        rad = 0.5 * px
        n = int(W / pitch) + 3
        x_first = W / 2 - pitch * (n // 2) + pitch / 2 - hw / 2
        fill = HOLE_BLACK if black_holes else HOLE_WHITE
        for i in range(n):
            x = x_first + i * pitch
            for y in (edge, H - edge - hh):
                d.rounded_rectangle([x, y, x + hw, y + hh], radius=rad, fill=fill)

    if edge_text and rebate >= 4:
        bands = [Image.new("RGBA", (W, rebate), (0, 0, 0, 0)) for _ in range(2)]  # upper / lower rebate
        _edge_print(bands[0], bands[1], kind, px, style, frame_number, film_key)
        for band, y in zip(bands, (0, H - rebate)):
            band = band.filter(ImageFilter.GaussianBlur(max(0.35, 0.03 * px)))  # latent-image softness
            canvas.paste(band, (0, y), band)

    # the picture in its gate, corners very slightly rounded
    photo = Image.fromarray((pic * 255 + 0.5).astype(np.uint8), "RGB")
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=max(1, round((0.35 if kind == "135"
                                                                                      else 0.6) * px)), fill=255)
    canvas.paste(photo, (end, rebate), mask)
    out = np.asarray(canvas, dtype=np.float32) / 255.0

    if kind == "120" and (margin_date or margin_data) and rebate >= 4:  # data back: in the lower rebate
        size = 1.45 * px
        layer = Image.new("L", (W, rebate), 0)
        ld = ImageDraw.Draw(layer)
        font = _mono_font(round(size * 1.2))
        y = (rebate - size) / 2
        if margin_data:
            _seg_draw(ld, margin_data, end + 4.0 * px, y, size, font)
        if margin_date:
            _seg_draw(ld, margin_date, W - end - 4.0 * px - _seg_width(margin_date, size, ld, font), y, size, font)
        out = np.array(out)
        out[H - rebate:] = _glow_onto(out[H - rebate:], layer, size)
    if not horizontal:
        out = np.rot90(out, k=1)
    return np.ascontiguousarray(out, dtype=np.float32)


def _edge_print(top: Image.Image, bottom: Image.Image, kind, px, style, frame, film_key):
    """Edge print into the upper and lower rebate bands (each W x rebate, y = 0 at the band's top)."""
    import zlib

    t135, t120, brand, color, fkind, name, mark = style
    col = color + (238,)
    n = max(0, int(frame))
    W, R = top.size
    dt, db = ImageDraw.Draw(top), ImageDraw.Draw(bottom)

    def text(d, x, baseline, s, cap_mm, fill=None):
        f = _edge_font(fkind, max(5, round(cap_mm * px)))
        d.text((x, baseline), s, font=f, fill=fill or col, anchor="ls")
        return x + d.textlength(s, font=f)

    def name(d, x, baseline, s, cap_mm):
        """The stock's or the look's name; mark 'red_name' sets its first word in red."""
        if mark == "red_name" and " " in s:
            first, rest = s.split(" ", 1)
            x = text(d, x, baseline, first + " ", cap_mm, fill=ACCENT_RED + (250,))
            s = rest
        return text(d, x, baseline, s, cap_mm)

    def width(s, cap_mm):
        return dt.textlength(s, font=_edge_font(fkind, max(5, round(cap_mm * px))))

    def arrow(d, x, baseline, cap_mm, right=True):
        a = cap_mm * px
        y0 = baseline - a * 0.78
        if right:
            d.polygon([(x, y0), (x, y0 + a * 0.56), (x + a * 0.62, y0 + a * 0.28)], fill=col)
        else:
            d.polygon([(x + a * 0.62, y0), (x + a * 0.62, y0 + a * 0.56), (x, y0 + a * 0.28)], fill=col)
        return x + a * 0.9

    if kind == "135":
        cap = 1.15
        top_base = 1.62 * px  # in the 2 mm between the film edge and the perforations
        bot_base = R - 0.42 * px
        if name in CINE_STYLES:  # motion-picture stock: the maker's name and stock number, small, one mark
            db.rectangle([0.015 * W, bot_base - 0.55 * px, 0.06 * W, bot_base - 0.25 * px], fill=col)
            text(db, 0.20 * W, bot_base, t135, 0.95)
            return
        # upper edge: the stock name, then (room permitting) the half-frame mark and the frame number
        gap = 1.6 * px
        end = name(dt, 0.07 * W, top_base, t135, cap)
        num, half = str(n), f"{max(0, n - 1)}A"
        x_num = max(0.84 * W, end + gap)
        if x_num + width(num, cap * 1.12) <= W - 0.5 * px:
            if fkind == "fuji" and end + gap + width(half, cap) + gap <= x_num:
                text(dt, max(0.40 * W, end + gap), top_base, half, cap)
            text(dt, x_num, top_base, num, cap * 1.12)
        # lower edge: frame markers, and the DX code in the space left between them
        spans = []
        x = 0.335 * W
        if x + width(half, cap) + 1.2 * px < 0.81 * W:
            e = text(db, arrow(db, x, bot_base, cap) + 0.2 * px, bot_base, half, cap)
            spans.append((x - 1.0 * px, e + 1.0 * px))
        if 0.81 * W + width(num, cap * 1.12) < W - 0.5 * px:
            e = text(db, 0.81 * W, bot_base, num, cap * 1.12)
            spans.append((0.81 * W - 1.0 * px, e + 1.0 * px))
        rng = np.random.default_rng(zlib.crc32((film_key or t135).encode()))
        x = 0.0
        while x < W:
            bw = (0.36 if rng.random() < 0.55 else 0.72) * px
            tall = rng.random() < 0.6
            if not any(a < x + bw and x < b for a, b in spans):
                db.rectangle([x, R - (1.80 if tall else 1.05) * px, x + bw, R - 0.28 * px], fill=color + (215,))
            x += bw + 0.36 * px
        return

    # 120: stock and frame numbers with their arrows along the upper rebate, a group every 45 mm
    cap = 1.3
    base = R / 2 + cap / 2 * px
    x, k = 3.0 * px, 0
    while x < W - 8 * px and k < 40:
        label, num = (t120 if k % 2 == 0 else brand), n + k
        if x + width(f"{label} {num}", cap) + 2.5 * px > W:
            break
        e = name(dt, x, base, label, cap)
        e = text(dt, e + 1.8 * px, base, str(num), cap)
        e = arrow(dt, e + 0.7 * px, base, cap, right=False)
        x = max(x + 22.5 * px, e + 4.0 * px)  # long names (a look's) push the next group along
        k += 1
