"""Per-photo develop settings (the UI-level model), option lists and setting groups."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, fields

from .profiles import BW_PAPER, DIGITAL, NO_PRINT, Stock, film_stocks, print_papers, stock_by_key  # noqa: F401

SCHEMA_VERSION = 3

# --- option lists -------------------------------------------------------------

METERING = ["center_weighted", "matrix", "multi_zone", "partial", "highlight_weighted", "median", "average"]
FILM_FORMATS = {  # label -> long edge in mm (what the engine calls film_format_mm)
    "Half frame (18×24)": 24.0,
    "135 (24×36)": 36.0,
    "XPan (24×65)": 65.0,
    "645": 56.0,
    "6×6": 56.0,
    "6×7": 70.0,
    "6×8": 76.0,
    "6×9": 84.0,
    "6×12": 112.0,
    "6×17": 168.0,
    "4×5 in": 127.0,
}
# Film Edge gates: label -> (film, mm along the strip, mm across it). 135 film is 35 mm wide with a 24 mm
# picture; 120 is 61.5 mm wide with a 56 mm picture; 4x5 is sheet film in a filed carrier.
FORMAT_GATES = {
    "Half frame (18×24)": ("135", 18.0, 24.0),
    "135 (24×36)": ("135", 36.0, 24.0),
    "XPan (24×65)": ("135", 65.0, 24.0),
    "645": ("120", 41.5, 56.0),
    "6×6": ("120", 56.0, 56.0),
    "6×7": ("120", 69.5, 56.0),
    "6×8": ("120", 76.0, 56.0),
    "6×9": ("120", 84.0, 56.0),
    "6×12": ("120", 112.0, 56.0),
    "6×17": ("120", 168.0, 56.0),
    "4×5 in": ("sheet", 120.0, 95.0),
}
ASPECTS = {"Original": "orig", "Free": None, "3:2": 3 / 2, "4:3": 4 / 3, "5:4": 5 / 4, "1:1": 1.0,
           "16:9": 16 / 9, "65:24 (XPan)": 65 / 24, "2:3": 2 / 3, "3:4": 3 / 4, "4:5": 4 / 5, "9:16": 9 / 16}
DIFFUSION_FAMILIES = ["black_pro_mist", "pro_mist", "glimmerglass", "cinebloom"]
BORDERS = {  # Film Edge styles ("none" = Film Edge off)
    "none": "Off",
    "auto": "Film strip",
    "filed": "Filed carrier (black)",
    "slide": "Slide mount",
    "white_thin": "White print border",
    "white_wide": "Wide white matte",
}
EDGE_STYLES = [k for k in BORDERS if k != "none"]
EDGE_HOLES = {"white": "White (backlit scan)", "black": "Black"}


# --- develop settings -----------------------------------------------------------

@dataclass
class DevelopSettings:
    # Profile
    film: str = "kodak_portra_400"
    paper: str = "kodak_portra_endura"
    bw_grade: float = 2.0  # Multigrade contrast grade, -1 (= 00) .. 5
    look: str = ""  # name of the applied look (informational)
    # White balance (scene illuminant; see wb.py)
    wb_mode: str = "as_shot"
    temperature: float = 5500.0
    tint: float = 0.0
    lens_correction: bool = False
    # Exposure (film side)
    auto_exposure: bool = True
    metering: str = "center_weighted"
    exposure_ev: float = 0.0
    # Tone & presence (finishing, -100..100)
    contrast: float = 0.0
    highlights: float = 0.0
    shadows: float = 0.0
    whites: float = 0.0
    blacks: float = 0.0
    clarity: float = 0.0
    vibrance: float = 0.0
    saturation: float = 0.0
    # Color grading (finishing)
    cg_shadow_hue: float = 210.0
    cg_shadow_sat: float = 0.0
    cg_mid_hue: float = 40.0
    cg_mid_sat: float = 0.0
    cg_high_hue: float = 45.0
    cg_high_sat: float = 0.0
    cg_balance: float = 0.0
    cg_blending: float = 50.0
    # Vignette (finishing)
    vignette: float = 0.0
    vignette_midpoint: float = 50.0
    # Tone curves: points (x, y) in 0..1 on the display-encoded RGB (master) and per channel
    curve_master: tuple = ((0.0, 0.0), (1.0, 1.0))
    curve_r: tuple = ((0.0, 0.0), (1.0, 1.0))
    curve_g: tuple = ((0.0, 0.0), (1.0, 1.0))
    curve_b: tuple = ((0.0, 0.0), (1.0, 1.0))
    # Colour mixer (HSL), -100..100 per colour band
    hsl_hue_red: float = 0.0
    hsl_hue_orange: float = 0.0
    hsl_hue_yellow: float = 0.0
    hsl_hue_green: float = 0.0
    hsl_hue_aqua: float = 0.0
    hsl_hue_blue: float = 0.0
    hsl_hue_purple: float = 0.0
    hsl_hue_magenta: float = 0.0
    hsl_sat_red: float = 0.0
    hsl_sat_orange: float = 0.0
    hsl_sat_yellow: float = 0.0
    hsl_sat_green: float = 0.0
    hsl_sat_aqua: float = 0.0
    hsl_sat_blue: float = 0.0
    hsl_sat_purple: float = 0.0
    hsl_sat_magenta: float = 0.0
    hsl_lum_red: float = 0.0
    hsl_lum_orange: float = 0.0
    hsl_lum_yellow: float = 0.0
    hsl_lum_green: float = 0.0
    hsl_lum_aqua: float = 0.0
    hsl_lum_blue: float = 0.0
    hsl_lum_purple: float = 0.0
    hsl_lum_magenta: float = 0.0
    # Creative LUT (.cube) applied to the finished image
    lut_name: str = ""
    lut_amount: float = 100.0
    # Film format & effects (film side)
    film_format: str = "135 (24×36)"
    grain: bool = True
    grain_size: float = 0.2
    halation: bool = True
    halation_amount: float = 1.0
    scatter_amount: float = 1.0
    highlight_boost: float = 0.0
    couplers: bool = True
    couplers_amount: float = 1.0
    negative_contrast: float = 1.0
    diffusion: bool = False
    diffusion_family: str = "black_pro_mist"
    diffusion_strength: float = 0.25
    # Enlarger / print (print side)
    print_brightness: float = 0.0  # stops
    # When on, the enlarger cancels film exposure changes (like a lab printer).
    auto_print_compensation: bool = False
    yellow: float = 0.0  # CC units
    magenta: float = 0.0
    preflash: float = 0.0
    print_contrast: float = 1.0
    developer_exhaustion: float = 0.0
    glare: bool = True
    glare_amount: float = 0.03
    # Scanner (print side)
    sharpen: float = 0.7
    white_correction: bool = False
    black_correction: bool = False
    # Geometry
    rotation: int = 0  # quarter turns clockwise
    flip_h: bool = False
    flip_v: bool = False
    straighten: float = 0.0
    aspect: str = "Original"
    crop_l: float = 0.0
    crop_t: float = 0.0
    crop_r: float = 1.0
    crop_b: float = 1.0
    # Film edge / border (applied after rendering)
    border: str = "none"  # "none" = Film Edge off; see BORDERS
    border_text: bool = True
    frame_number: int = 12
    edge_holes: str = "white"  # 135 perforations: "white" (backlit scan) or "black"
    date_stamp: bool = False  # camera date-back imprint (in the picture; in the margin on 120)
    date_text: str = ""  # empty = the date the photo was taken
    shoot_data: bool = False  # 120 data back: shutter, aperture, focal length in the margin

    # -- helpers --
    def copy(self) -> "DevelopSettings":
        return dataclasses.replace(self)

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["_v"] = SCHEMA_VERSION
        return d

    @classmethod
    def from_dict(cls, data: dict | None) -> "DevelopSettings":
        s = cls()
        if not data:
            return s
        data = dict(data)
        v = int(data.get("_v", 1))
        if v < 2:  # v1 defaulted to auto print compensation, which cancelled film exposure edits
            data["auto_print_compensation"] = False
        if v < 3:
            # tint was a green multiplier (1.0 = neutral); WB is now Kelvin + tint in Duv units
            data["tint"] = 0.0
            if data.get("wb_mode") not in ("as_shot", "daylight", "tungsten", "custom"):
                data["wb_mode"] = "as_shot"
            # crop was aspect + zoom + position; it is now an explicit rectangle
            zoom = max(1.0, float(data.get("crop_zoom", 1.0) or 1.0))
            cx, cy = float(data.get("crop_x", 0.5)), float(data.get("crop_y", 0.5))
            size = 1.0 / zoom
            data["crop_l"], data["crop_t"] = cx * (1 - size), cy * (1 - size)
            data["crop_r"], data["crop_b"] = data["crop_l"] + size, data["crop_t"] + size
        if data.get("border") in ("135", "120"):  # 1.3 had fixed strip styles; the strip now follows the format
            data["border"] = "auto"
        valid = {f.name for f in fields(cls)}
        for k, val in data.items():
            if k in valid:
                try:
                    cur = getattr(s, k)
                    if isinstance(cur, tuple):  # curves: list of [x, y] -> tuple of (x, y)
                        pts = tuple(sorted((min(max(float(p[0]), 0.0), 1.0), min(max(float(p[1]), 0.0), 1.0))
                                           for p in val))
                        val = pts if len(pts) >= 2 else cur
                    elif isinstance(cur, bool):
                        val = bool(val)
                    elif isinstance(cur, int):
                        val = int(round(float(val)))
                    elif isinstance(cur, float):
                        val = float(val)
                    setattr(s, k, val)
                except (TypeError, ValueError):
                    pass
        return s

    def subset(self, names) -> tuple:
        return tuple(getattr(self, n) for n in names)

    def is_bw(self) -> bool:
        st = stock_by_key(self.film)
        return bool(st and st.bw)


# --- crop geometry (shared by engine and UI) --------------------------------------

def edge_gate(s: DevelopSettings) -> tuple[str, float, float] | None:
    """(film, mm along, mm across) of the Film Edge gate the picture is exposed in, or None when Film Edge is
    off or its style has no gate (white print borders)."""
    if s.border in ("none", "white_thin", "white_wide") or s.border not in BORDERS:
        return None
    return FORMAT_GATES.get(s.film_format, FORMAT_GATES["135 (24×36)"])


def crop_ratio(s: DevelopSettings, frame_w: int, frame_h: int) -> float | None:
    """The w/h the crop is locked to: the film gate while Film Edge is on (oriented like the crop), else the
    aspect setting; None = free."""
    gate = edge_gate(s)
    if gate:
        _, along, across = gate
        r = max(along, across) / min(along, across)
        w = (min(s.crop_r, 1.0) - max(s.crop_l, 0.0)) * frame_w
        h = (min(s.crop_b, 1.0) - max(s.crop_t, 0.0)) * frame_h
        return r if w >= h else 1.0 / r
    ratio = ASPECTS.get(s.aspect)
    if ratio == "orig":
        ratio = frame_w / max(frame_h, 1)
    return ratio


def geometry_key(s: DevelopSettings) -> tuple:
    """Everything that decides the picture's framing (cache key for cropped images)."""
    return s.subset(GEOMETRY_FIELDS) + (s.film_format if edge_gate(s) else None,)


def effective_crop(s: DevelopSettings, frame_w: int, frame_h: int) -> tuple[float, float, float, float]:
    """Normalized (l, t, r, b) crop of the straightened frame, honouring the aspect lock (or the Film Edge
    gate): the stored rectangle is shrunk (centred) to the locked aspect ratio if it does not match."""
    l, t = min(max(s.crop_l, 0.0), 1.0), min(max(s.crop_t, 0.0), 1.0)
    r, b = min(max(s.crop_r, l + 0.01), 1.0), min(max(s.crop_b, t + 0.01), 1.0)
    ratio = crop_ratio(s, frame_w, frame_h)
    if ratio:
        w_px, h_px = (r - l) * frame_w, (b - t) * frame_h
        if abs(w_px / max(h_px, 1e-6) - ratio) > 1e-3:
            if w_px / h_px > ratio:
                nw = h_px * ratio / frame_w
                cx = (l + r) / 2
                l, r = cx - nw / 2, cx + nw / 2
            else:
                nh = w_px / ratio / frame_h
                cy = (t + b) / 2
                t, b = cy - nh / 2, cy + nh / 2
    return (l, t, r, b)


# --- stage classification (what each edit invalidates) ------------------------------

SOURCE_FIELDS = ("lens_correction",)
WB_FIELDS = ("wb_mode", "temperature", "tint")
GEOMETRY_FIELDS = ("rotation", "flip_h", "flip_v", "straighten", "aspect", "crop_l", "crop_t", "crop_r", "crop_b")
METER_FIELDS = ("auto_exposure", "metering")
FILM_FIELDS = ("film", "exposure_ev", "film_format", "grain", "grain_size", "halation", "halation_amount",
               "scatter_amount", "highlight_boost", "couplers", "couplers_amount", "negative_contrast",
               "diffusion", "diffusion_family", "diffusion_strength")
PRINT_FIELDS = ("paper", "bw_grade", "print_brightness", "auto_print_compensation", "yellow", "magenta",
                "preflash", "print_contrast", "developer_exhaustion", "glare", "glare_amount", "sharpen",
                "white_correction", "black_correction")
HSL_BANDS = ("red", "orange", "yellow", "green", "aqua", "blue", "purple", "magenta")
HSL_FIELDS = tuple(f"hsl_{k}_{b}" for k in ("hue", "sat", "lum") for b in HSL_BANDS)
CURVE_FIELDS = ("curve_master", "curve_r", "curve_g", "curve_b")
FINISH_FIELDS = ("contrast", "highlights", "shadows", "whites", "blacks", "clarity", "vibrance", "saturation",
                 "cg_shadow_hue", "cg_shadow_sat", "cg_mid_hue", "cg_mid_sat", "cg_high_hue", "cg_high_sat",
                 "cg_balance", "cg_blending", "vignette", "vignette_midpoint") + CURVE_FIELDS + HSL_FIELDS + (
                 "lut_name", "lut_amount")
BORDER_FIELDS = ("border", "border_text", "frame_number", "edge_holes", "date_stamp", "date_text", "shoot_data")

# What a Look sets (everything else — exposure, WB, crop, border — is left alone).
LOOK_FIELDS = ("film", "paper", "bw_grade", "grain", "grain_size", "halation", "halation_amount",
               "scatter_amount", "highlight_boost", "couplers", "couplers_amount", "negative_contrast",
               "diffusion", "diffusion_family", "diffusion_strength", "print_brightness", "yellow", "magenta",
               "preflash", "print_contrast", "developer_exhaustion", "glare", "glare_amount", "sharpen",
               ) + FINISH_FIELDS

# Groups offered by Copy / Paste / Sync.
SYNC_GROUPS = {
    "Look & profile": ("film", "paper", "bw_grade", "look"),
    "White balance": WB_FIELDS,
    "Exposure": ("auto_exposure", "metering", "exposure_ev"),
    "Tone & presence": ("contrast", "highlights", "shadows", "whites", "blacks", "clarity", "vibrance",
                        "saturation"),
    "Color grading": tuple(f for f in FINISH_FIELDS if f.startswith("cg_")),
    "Tone curve": CURVE_FIELDS,
    "Color mixer (HSL)": HSL_FIELDS,
    "Creative LUT": ("lut_name", "lut_amount"),
    "Film & grain": ("film_format", "grain", "grain_size", "halation", "halation_amount", "scatter_amount",
                     "highlight_boost", "couplers", "couplers_amount", "negative_contrast"),
    "Enlarger & print": ("print_brightness", "auto_print_compensation", "yellow", "magenta", "preflash",
                         "print_contrast", "developer_exhaustion"),
    "Effects": ("vignette", "vignette_midpoint", "glare", "glare_amount", "diffusion", "diffusion_family",
                "diffusion_strength"),
    "Detail": ("sharpen", "white_correction", "black_correction"),
    "Lens correction": ("lens_correction",),
    "Film edge & border": BORDER_FIELDS,
    "Crop & rotate": GEOMETRY_FIELDS,
}

FIELD_LABELS = {
    "film": "Film", "paper": "Paper", "bw_grade": "Grade", "look": "Look", "wb_mode": "White balance",
    "temperature": "Temperature", "tint": "Tint", "lens_correction": "Lens correction",
    "auto_exposure": "Auto exposure", "metering": "Metering", "exposure_ev": "Exposure",
    "contrast": "Contrast", "highlights": "Highlights", "shadows": "Shadows", "whites": "Whites",
    "blacks": "Blacks", "clarity": "Clarity", "vibrance": "Vibrance", "saturation": "Saturation",
    "cg_shadow_hue": "Shadows hue", "cg_shadow_sat": "Shadows color", "cg_mid_hue": "Midtones hue",
    "cg_mid_sat": "Midtones color", "cg_high_hue": "Highlights hue", "cg_high_sat": "Highlights color",
    "cg_balance": "Grading balance", "cg_blending": "Grading blending", "vignette": "Vignette",
    "vignette_midpoint": "Vignette midpoint", "film_format": "Film format", "grain": "Grain",
    "grain_size": "Grain size", "halation": "Halation", "halation_amount": "Halation amount",
    "scatter_amount": "Scatter", "highlight_boost": "Highlight boost", "couplers": "DIR couplers",
    "couplers_amount": "Couplers", "negative_contrast": "Negative contrast", "diffusion": "Diffusion filter",
    "diffusion_family": "Diffusion type", "diffusion_strength": "Diffusion strength",
    "print_brightness": "Print brightness", "auto_print_compensation": "Lab auto-print", "yellow": "Yellow",
    "magenta": "Magenta", "preflash": "Pre-flash", "print_contrast": "Paper contrast",
    "developer_exhaustion": "Developer", "glare": "Surface glare", "glare_amount": "Glare",
    "sharpen": "Sharpening", "white_correction": "White point", "black_correction": "Black point",
    "rotation": "Rotate", "flip_h": "Flip horizontal", "flip_v": "Flip vertical", "straighten": "Angle",
    "aspect": "Aspect", "crop_l": "Crop", "crop_t": "Crop", "crop_r": "Crop", "crop_b": "Crop",
    "border": "Film Edge", "border_text": "Edge print", "frame_number": "Frame number",
    "edge_holes": "Perforations", "date_stamp": "Date stamp", "date_text": "Date text",
    "shoot_data": "Shooting data",
    "curve_master": "Tone curve", "curve_r": "Red curve", "curve_g": "Green curve", "curve_b": "Blue curve",
    "lut_name": "Creative LUT", "lut_amount": "LUT amount",
}
FIELD_LABELS.update({f"hsl_{k}_{b}": f"{b.capitalize()} {dict(hue='hue', sat='saturation', lum='luminance')[k]}"
                     for k in ("hue", "sat", "lum") for b in HSL_BANDS})
