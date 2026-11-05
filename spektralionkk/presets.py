"""Import presets from other apps (and export our own).

Supported:
* Lightroom / Adobe Camera Raw presets (.xmp, including ones exported from Lightroom mobile)
* Lightroom Classic legacy presets (.lrtemplate)
* creative LUTs (.cube) — become a Look that applies the LUT
* spektralionkk presets (.sprkpreset, JSON) — import and export

Lightroom settings are mapped to the closest controls here (Basic tone & presence, white balance,
tone curves incl. the parametric curve, HSL, split toning / color grading, vignette, grain,
sharpening, black & white). Anything without an equivalent (Texture, Dehaze, masks, lens profiles,
Adobe's creative profiles with embedded tables, …) is reported back instead of silently dropped.
Imported Lightroom presets use the "Digital (no film)" base, because they were designed for a
neutral digital rendering; you can switch the film afterwards.
"""

from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET

from .profiles import DIGITAL
from .settings import DevelopSettings

CRS = "http://ns.adobe.com/camera-raw-settings/1.0/"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"

_SIMPLE = {  # Lightroom key -> (our field, scale)
    "Exposure2012": ("exposure_ev", 1.0), "Exposure": ("exposure_ev", 1.0),
    "Contrast2012": ("contrast", 1.0), "Highlights2012": ("highlights", 1.0), "Shadows2012": ("shadows", 1.0),
    "Whites2012": ("whites", 1.0), "Blacks2012": ("blacks", 1.0), "Clarity2012": ("clarity", 1.0),
    "Vibrance": ("vibrance", 1.0), "Saturation": ("saturation", 1.0),
    "SplitToningShadowHue": ("cg_shadow_hue", 1.0), "SplitToningShadowSaturation": ("cg_shadow_sat", 1.0),
    "SplitToningHighlightHue": ("cg_high_hue", 1.0), "SplitToningHighlightSaturation": ("cg_high_sat", 1.0),
    "SplitToningBalance": ("cg_balance", 1.0),
    "ColorGradeMidtoneHue": ("cg_mid_hue", 1.0), "ColorGradeMidtoneSat": ("cg_mid_sat", 1.0),
    "ColorGradeBlending": ("cg_blending", 1.0),
    "PostCropVignetteAmount": ("vignette", 1.0), "PostCropVignetteMidpoint": ("vignette_midpoint", 1.0),
}
_BANDS = ("Red", "Orange", "Yellow", "Green", "Aqua", "Blue", "Purple", "Magenta")
for _b in _BANDS:
    _SIMPLE[f"HueAdjustment{_b}"] = (f"hsl_hue_{_b.lower()}", 1.0)
    _SIMPLE[f"SaturationAdjustment{_b}"] = (f"hsl_sat_{_b.lower()}", 1.0)
    _SIMPLE[f"LuminanceAdjustment{_b}"] = (f"hsl_lum_{_b.lower()}", 1.0)
_IGNORED_QUIET = {"Version", "ProcessVersion", "PresetType", "Cluster", "UUID", "SupportsAmount", "SupportsAmount2",
                  "SupportsColor", "SupportsMonochrome", "SupportsHighDynamicRange", "SupportsNormalDynamicRange",
                  "SupportsSceneReferred", "SupportsOutputReferred", "CameraModelRestriction", "Copyright",
                  "ContactInfo", "HasSettings", "AlreadyApplied", "CameraProfile", "LensProfileEnable",
                  "LensProfileSetup", "AutoLateralCA", "LensManualDistortionAmount", "PerspectiveUpright",
                  "ToneCurveName", "ToneCurveName2012", "ConvertToGrayscale", "WhiteBalance", "Temperature", "Tint",
                  "IncrementalTemperature", "IncrementalTint", "GrainAmount", "GrainSize", "GrainFrequency",
                  "Sharpness", "SharpenRadius", "SharpenDetail", "SharpenEdgeMasking", "ParametricShadows",
                  "ParametricDarks", "ParametricLights", "ParametricHighlights", "ParametricShadowSplit",
                  "ParametricMidtoneSplit", "ParametricHighlightSplit", "OverrideLookVignette",
                  "PostCropVignetteFeather", "PostCropVignetteRoundness", "PostCropVignetteStyle",
                  "PostCropVignetteHighlightContrast", "ColorGradeShadowLum", "ColorGradeMidtoneLum",
                  "ColorGradeHighlightLum", "ColorGradeGlobalHue", "ColorGradeGlobalSat", "ColorGradeGlobalLum"}


class ImportedPreset:
    def __init__(self, name: str, values: dict, unsupported: list[str], source: str):
        self.name, self.values, self.unsupported, self.source = name, values, unsupported, source


def _num(v):
    try:
        return float(str(v).strip().replace("+", ""))
    except (TypeError, ValueError):
        return None


def _curve_points(seq):
    """Lightroom curve: list of 'x, y' strings or flat numbers, 0..255 -> ((x, y), ...) in 0..1."""
    pts = []
    if seq and isinstance(seq[0], str):
        for item in seq:
            parts = [p for p in re.split(r"[,\s]+", item.strip()) if p]
            if len(parts) >= 2:
                pts.append((float(parts[0]) / 255.0, float(parts[1]) / 255.0))
    else:
        nums = [float(v) for v in seq]
        pts = [(nums[i] / 255.0, nums[i + 1] / 255.0) for i in range(0, len(nums) - 1, 2)]
    pts = tuple(sorted(pts))
    return pts if len(pts) >= 2 else None


def _parametric_to_curve(base, p):
    """Bake Lightroom's parametric curve (Shadows / Darks / Lights / Highlights) into curve points."""
    if not any(p.get(k) for k in ("ParametricShadows", "ParametricDarks", "ParametricLights", "ParametricHighlights")):
        return base
    s1 = (p.get("ParametricShadowSplit") or 25) / 100.0
    s2 = (p.get("ParametricMidtoneSplit") or 50) / 100.0
    s3 = (p.get("ParametricHighlightSplit") or 75) / 100.0
    xs = [0.0, s1 / 2, (s1 + s2) / 2, s2, (s2 + s3) / 2, (s3 + 1) / 2, 1.0]
    deltas = [0.0, (p.get("ParametricShadows") or 0) / 100 * 0.10, (p.get("ParametricDarks") or 0) / 100 * 0.10, 0.0,
              (p.get("ParametricLights") or 0) / 100 * 0.10, (p.get("ParametricHighlights") or 0) / 100 * 0.10, 0.0]
    from .finish import curve_lut
    import numpy as np

    lut = curve_lut(base)
    grid = np.linspace(0, 1, len(lut))
    pts = []
    for x, d in zip(xs, deltas):
        pts.append((x, float(min(max(np.interp(x, grid, lut) + d, 0.0), 1.0))))
    return tuple(pts)


def _map(params: dict, name: str, source: str) -> ImportedPreset:
    v: dict = {"film": DIGITAL}
    unsupported = []
    gray = str(params.get("ConvertToGrayscale", "")).strip().lower() == "true"
    for key, val in params.items():
        if key.startswith("_"):
            continue
        if key in _SIMPLE:
            n = _num(val)
            if n is not None:
                field, scale = _SIMPLE[key]
                v[field] = n * scale
            continue
        if key in _IGNORED_QUIET or key.startswith(("ToneCurve", "Crop", "GrayMixer" if not gray else "~")):
            continue
        n = _num(val)  # report only real adjustments we can't reproduce (non-zero numbers)
        if n is not None and abs(n) > 1e-6:
            unsupported.append(key)
    # white balance
    wbm = str(params.get("WhiteBalance", "")).strip().lower()
    if wbm in ("as shot", "asshot"):
        v["wb_mode"] = "as_shot"
    elif wbm == "auto":
        v["wb_mode"] = "auto"
    elif wbm in ("daylight", "cloudy", "shade", "tungsten", "fluorescent", "flash"):
        v["wb_mode"] = wbm
    elif _num(params.get("Temperature")) and wbm in ("custom", ""):
        v.update(wb_mode="custom", temperature=_num(params["Temperature"]), tint=_num(params.get("Tint")) or 0.0)
    elif _num(params.get("IncrementalTemperature")) is not None:  # presets for JPEGs: relative shift
        it, tt = _num(params.get("IncrementalTemperature")) or 0.0, _num(params.get("IncrementalTint")) or 0.0
        if it or tt:
            mired = 1e6 / 5500.0 - it * 0.9
            v.update(wb_mode="custom", temperature=round(1e6 / max(mired, 40.0)), tint=tt)
    # tone curves
    for key, field in (("ToneCurvePV2012", "curve_master"), ("ToneCurvePV2012Red", "curve_r"),
                       ("ToneCurvePV2012Green", "curve_g"), ("ToneCurvePV2012Blue", "curve_b")):
        if key in params and isinstance(params[key], (list, tuple)):
            pts = _curve_points(list(params[key]))
            if pts:
                v[field] = pts
    v["curve_master"] = _parametric_to_curve(v.get("curve_master", ((0.0, 0.0), (1.0, 1.0))),
                                             {k: _num(params.get(k)) for k in params if k.startswith("Parametric")})
    if v["curve_master"] == ((0.0, 0.0), (1.0, 1.0)):
        v.pop("curve_master")
    # black & white
    if str(params.get("ConvertToGrayscale", "")).strip().lower() == "true":
        v["saturation"] = -100.0
        v["vibrance"] = 0.0
    # grain
    amt = _num(params.get("GrainAmount"))
    if amt:
        size = _num(params.get("GrainSize")) or 25.0
        v["grain"] = True
        v["grain_size"] = round(min(1.2, 0.08 + amt / 100.0 * 0.5 * (0.5 + size / 50.0)), 3)
    elif amt == 0:
        v["grain"] = False
    sh = _num(params.get("Sharpness"))
    if sh is not None:
        v["sharpen"] = round(min(2.0, sh / 40.0 * 0.7), 3)
    if params.get("_has_look_table"):
        unsupported.append("Adobe creative profile (embedded colour table)")
    # keep values in range
    for f in list(v):
        if f in ("contrast", "highlights", "shadows", "whites", "blacks", "clarity", "vibrance", "saturation",
                 "vignette", "cg_balance") or f.startswith("hsl_"):
            v[f] = max(-100.0, min(100.0, float(v[f])))
        elif f in ("cg_shadow_sat", "cg_mid_sat", "cg_high_sat", "cg_blending", "vignette_midpoint"):
            v[f] = max(0.0, min(100.0, float(v[f])))
        elif f == "exposure_ev":
            v[f] = max(-5.0, min(5.0, float(v[f])))
    unsupported = sorted(set(u for u in unsupported if u))
    return ImportedPreset(name, v, unsupported, source)


# ------------------------------------------------------------------ XMP

def parse_xmp(path: str) -> ImportedPreset:
    tree = ET.parse(path)
    root = tree.getroot()
    params: dict = {}
    name = None
    for desc in root.iter(f"{{{RDF}}}Description"):
        for k, val in desc.attrib.items():
            if k.startswith(f"{{{CRS}}}"):
                params[k[len(CRS) + 2:]] = val
        for child in desc:
            if not child.tag.startswith(f"{{{CRS}}}"):
                continue
            key = child.tag[len(CRS) + 2:]
            items = [li.text or "" for li in child.iter(f"{{{RDF}}}li")]
            if key == "Name" and items:
                name = items[0].strip() or name
            elif key == "Look":
                params["_has_look_table"] = True
            elif items:
                params[key] = items
            elif child.text and child.text.strip():
                params[key] = child.text.strip()
    if not params:
        raise ValueError("No Lightroom / Camera Raw settings found in this .xmp")
    if isinstance(params.get("Name"), str):
        name = params.pop("Name")
    name = name or os.path.splitext(os.path.basename(path))[0]
    return _map(params, name, "Lightroom preset (.xmp)")


# ------------------------------------------------------------------ lrtemplate

def parse_lrtemplate(path: str) -> ImportedPreset:
    text = open(path, encoding="utf-8", errors="replace").read()
    m = re.search(r"settings\s*=\s*\{", text)
    if not m:
        raise ValueError("No 'settings' table found in this .lrtemplate")
    i, depth = m.end(), 1
    while i < len(text) and depth:
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    body = text[m.end():i - 1]
    params: dict = {}
    for km in re.finditer(r"(\w+)\s*=\s*(\{[^{}]*\}|\"[^\"]*\"|[-+0-9.eE]+|true|false)", body):
        key, val = km.group(1), km.group(2)
        if val.startswith("{"):
            params[key] = [float(x) for x in re.findall(r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?", val)]
        elif val.startswith('"'):
            params[key] = val.strip('"')
        else:
            params[key] = val
    title = re.search(r'title\s*=\s*(?:ZSTR\s*)?"([^"]+)"', text)
    name = title.group(1) if title else os.path.splitext(os.path.basename(path))[0]
    return _map(params, name, "Lightroom preset (.lrtemplate)")


# ------------------------------------------------------------------ our own format

def export_preset(path: str, name: str, values: dict):
    data = {"format": "sprktralionkk-preset", "version": 1, "name": name,
            "values": {k: (list(map(list, v)) if isinstance(v, tuple) else v) for k, v in values.items()}}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)


def parse_sprkpreset(path: str) -> ImportedPreset:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("format") != "sprktralionkk-preset":
        raise ValueError("Not a spektralionkk preset")
    vals = DevelopSettings.from_dict(data.get("values", {}))
    clean = {k: getattr(vals, k) for k in data.get("values", {}) if hasattr(vals, k)}
    return ImportedPreset(data.get("name") or os.path.splitext(os.path.basename(path))[0], clean, [],
                          "spektralionkk preset")


# ------------------------------------------------------------------ entry point

EXT = ".sprkpreset"
IMPORT_FILTER = ("Presets and LUTs (*.xmp *.lrtemplate *.cube *.sprkpreset);;"
                 "Lightroom / Camera Raw presets (*.xmp *.lrtemplate);;LUT (*.cube);;"
                 "spektralionkk preset (*.sprkpreset);;All files (*)")


def import_file(path: str) -> ImportedPreset:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".xmp":
        return parse_xmp(path)
    if ext == ".lrtemplate":
        return parse_lrtemplate(path)
    if ext == ".sprkpreset":
        return parse_sprkpreset(path)
    if ext == ".cube":
        from . import luts

        lut_name = luts.import_cube(path)
        return ImportedPreset(lut_name, {"film": DIGITAL, "lut_name": lut_name, "lut_amount": 100.0}, [],
                              "LUT (.cube)")
    raise ValueError(f"Unsupported preset type: {ext}")
