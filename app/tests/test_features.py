"""New features: Digital profile, presets (XMP / lrtemplate / cube / own), curves, HSL, frames, date stamp.

Run: .venv\\Scripts\\python.exe -I -X utf8 -W ignore app\\tests\\test_features.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="sprk_feat_")
sys.path.insert(0, os.path.join(HERE, ".."))
import numpy as np
from PIL import Image

from spektralionkk import engine, live, luts, presets
from spektralionkk.settings import DevelopSettings

OUT = os.path.join(HERE, "out")
SRC = os.path.join(OUT, "test_input.jpg")
fails = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


XMP = """<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about="" xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
   crs:PresetType="Normal" crs:Version="16.0" crs:ProcessVersion="15.4"
   crs:Exposure2012="+0.35" crs:Contrast2012="+18" crs:Highlights2012="-40" crs:Shadows2012="+25"
   crs:Whites2012="-10" crs:Blacks2012="+12" crs:Clarity2012="+8" crs:Vibrance="+10" crs:Saturation="-15"
   crs:Texture="+20" crs:Dehaze="+5" crs:WhiteBalance="As Shot"
   crs:HueAdjustmentGreen="-30" crs:SaturationAdjustmentGreen="-40" crs:LuminanceAdjustmentOrange="+10"
   crs:SplitToningShadowHue="200" crs:SplitToningShadowSaturation="20" crs:SplitToningHighlightHue="40"
   crs:SplitToningHighlightSaturation="15" crs:SplitToningBalance="-10"
   crs:PostCropVignetteAmount="-25" crs:GrainAmount="30" crs:GrainSize="30" crs:Sharpness="40"
   crs:ParametricShadows="10" crs:ParametricHighlights="-5">
   <crs:Name><rdf:Alt><rdf:li xml:lang="x-default">Test Faded Film</rdf:li></rdf:Alt></crs:Name>
   <crs:ToneCurvePV2012><rdf:Seq><rdf:li>0, 25</rdf:li><rdf:li>128, 132</rdf:li><rdf:li>255, 240</rdf:li></rdf:Seq></crs:ToneCurvePV2012>
   <crs:ToneCurvePV2012Blue><rdf:Seq><rdf:li>0, 20</rdf:li><rdf:li>255, 255</rdf:li></rdf:Seq></crs:ToneCurvePV2012Blue>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>"""

LRT = """s = {
	id = "1A2B", internalName = "Warm Matte", title = ZSTR "Warm Matte",
	type = "Develop",
	value = {
		settings = {
			Contrast2012 = -12, Exposure2012 = 0.2, Saturation = -8, Temperature = 6200, Tint = 8,
			WhiteBalance = "Custom", ToneCurvePV2012 = { 0, 30, 64, 70, 192, 190, 255, 245, },
			ConvertToGrayscale = false,
		},
		uuid = "1A2B",
	},
	version = 0,
}"""


def main():
    from spektrafilm.utils.numba_warmup import warmup
    warmup()
    live.warmup()
    eng = engine.Engine()
    lp = live.LivePreview(eng)
    tmp = tempfile.mkdtemp()

    # --- Digital profile
    d = DevelopSettings(film="digital")
    img = eng.render(SRC, d, "fine", 1200)
    check(img.shape[2] == 3 and 0.25 < img.mean() / 255 < 0.7, f"Digital (no film) renders (mean {img.mean()/255:.2f})")
    lv = lp.render(SRC, d, 1200)
    check(np.abs(lv.astype(int) - img.astype(int)).mean() < 1.5, "Digital live preview matches the refined render")

    # --- XMP preset
    p = os.path.join(tmp, "faded.xmp")
    open(p, "w", encoding="utf-8").write(XMP)
    pr = presets.import_file(p)
    v = pr.values
    check(pr.name == "Test Faded Film", f"XMP name read ({pr.name})")
    check(v.get("contrast") == 18 and v.get("highlights") == -40 and v.get("exposure_ev") == 0.35,
          "XMP Basic tone mapped")
    check(v.get("hsl_hue_green") == -30 and v.get("hsl_sat_green") == -40 and v.get("hsl_lum_orange") == 10,
          "XMP HSL mapped")
    check(v.get("cg_shadow_hue") == 200 and v.get("cg_high_sat") == 15, "XMP split toning mapped")
    check(v.get("curve_master") and abs(v["curve_master"][0][1] - 25 / 255 - 0.0) < 0.05, "XMP tone curve mapped")
    check(v.get("curve_b") is not None, "XMP blue channel curve mapped")
    check("Texture" in pr.unsupported and "Dehaze" in pr.unsupported, f"unsupported settings reported {pr.unsupported}")
    s = DevelopSettings.from_dict(v)
    a = eng.render(SRC, s, "fine", 1200)
    check(np.abs(a.astype(int) - img.astype(int)).mean() > 3, "XMP preset changes the picture")
    la = lp.render(SRC, s, 1200)
    check(np.abs(la.astype(int) - a.astype(int)).mean() < 2.5,
          f"preset live preview ≈ refined ({np.abs(la.astype(int) - a.astype(int)).mean():.2f}/255)")

    # --- lrtemplate
    p2 = os.path.join(tmp, "warm.lrtemplate")
    open(p2, "w", encoding="utf-8").write(LRT)
    pr2 = presets.import_file(p2)
    check(pr2.name == "Warm Matte" and pr2.values.get("wb_mode") == "custom" and pr2.values.get("temperature") == 6200,
          f"lrtemplate parsed ({pr2.name}, {pr2.values.get('wb_mode')}, {pr2.values.get('temperature')})")
    check(len(pr2.values.get("curve_master", ())) == 4, "lrtemplate tone curve parsed")

    # --- .cube LUT (warming 3D LUT, 17^3)
    n = 17
    grid = np.linspace(0, 1, n)
    lines = ['TITLE "Warm test"', f"LUT_3D_SIZE {n}"]
    for b in grid:
        for g in grid:
            for r in grid:
                lines.append(f"{min(1, r * 1.08):.6f} {g:.6f} {b * 0.9:.6f}")
    pc = os.path.join(tmp, "warm_test.cube")
    open(pc, "w").write("\n".join(lines))
    pr3 = presets.import_file(pc)
    check(pr3.values.get("lut_name") == "warm_test" and "warm_test" in luts.available(), "LUT imported into the store")
    s3 = DevelopSettings(film="digital", lut_name="warm_test", lut_amount=100)
    c = eng.render(SRC, s3, "fine", 1200).astype(float)
    base = img.astype(float)
    check((c[..., 0] - c[..., 2]).mean() > (base[..., 0] - base[..., 2]).mean() + 5, "LUT warms the image")
    lc = lp.render(SRC, s3, 1200).astype(float)
    check(np.abs(lc - c).mean() < 2.0, "LUT live preview ≈ refined")

    # --- own preset round trip
    p4 = os.path.join(tmp, "mine.sprkpreset")
    presets.export_preset(p4, "Mine", {"film": "kodak_gold_200", "curve_master": ((0, 0.05), (1, 0.95)), "saturation": 12})
    pr4 = presets.import_file(p4)
    check(pr4.values.get("film") == "kodak_gold_200" and pr4.values.get("curve_master") == ((0.0, 0.05), (1.0, 0.95)),
          "own preset export/import round trip")

    # --- Film Edge and the date back
    s5 = DevelopSettings(film="fujifilm_velvia_100", paper="none", border="slide")
    sl = eng.render(SRC, s5, "fine", 1200)
    check(engine.frame_kind(s5) == "slide" and abs(sl.shape[0] - sl.shape[1]) <= 2, f"slide mount {sl.shape}")
    check(engine.frame_kind(DevelopSettings(film="fujifilm_velvia_100", paper="none", border="auto")) == "135",
          "Film strip on a slide film = 135 strip")
    s6 = DevelopSettings(border="auto", film_format="6×7")
    check(engine.frame_kind(s6) == "120", "Film strip for 6×7 = 120 strip")
    check(engine.frame_kind(DevelopSettings(border="auto", film="digital")) == "135",
          "film strip on Digital too (no stock lettering)")
    check(engine.frame_kind(DevelopSettings(border="auto", film_format="4×5 in")) == "filed", "4×5 = filed carrier")
    check(DevelopSettings.from_dict({"border": "120"}).border == "auto", "1.3 strip styles load as Film strip")
    sq = eng.render(SRC, DevelopSettings(border="auto", film_format="6×6"), "fine", 1200)
    l, t, w, h = eng.last_info["inset"]
    check(abs(w - h) <= 1 and sq.shape[0] > h and sq.shape[1] > w, f"6×6 gate frames the picture square ({w}x{h})")
    xp = DevelopSettings(border="auto", film_format="XPan (24×65)")
    eng.render(SRC, xp, "fine", 1200)
    _, _, w2, h2 = eng.last_info["inset"]
    check(abs(max(w2, h2) / min(w2, h2) - 65 / 24) < 0.02, f"XPan gate is 65:24 ({w2}x{h2})")
    wh = eng.render(SRC, DevelopSettings(border="auto"), "fine", 1200).astype(int)
    bk = eng.render(SRC, DevelopSettings(border="auto", edge_holes="black"), "fine", 1200).astype(int)
    check(wh.shape == bk.shape and wh.mean() > bk.mean() + 3, "white / black perforations")
    m120 = DevelopSettings(border="auto", film_format="6×7", date_stamp=True, date_text="'24 11 04",
                           shoot_data=True)
    a = eng.render(SRC, m120, "fine", 1200).astype(int)
    l3, t3, w3, h3 = eng.last_info["inset"]
    m120.date_stamp, m120.shoot_data = False, False
    b2 = eng.render(SRC, m120, "fine", 1200).astype(int)
    pic = np.abs(a[t3:t3 + h3, l3:l3 + w3] - b2[t3:t3 + h3, l3:l3 + w3]).max()
    margin = np.abs(a[t3 + h3:] - b2[t3 + h3:]).max()
    check(pic <= 2 and margin > 60, f"120 data back prints into the margin, not the picture ({pic}, {margin})")
    s7 = DevelopSettings(date_stamp=True, date_text="'24 11 04")
    ds = eng.render(SRC, s7, "fine", 1200).astype(int)
    plain = eng.render(SRC, DevelopSettings(), "fine", 1200).astype(int)
    dd = np.abs(ds - plain).sum(-1)
    ys, xs = np.nonzero(dd > 30)
    h, w = dd.shape
    check(len(ys) > 500 and ys.min() > h * 0.75 and xs.min() > w * 0.6,
          f"date stamp drawn bottom-right only ({len(ys)} px, rows {ys.min() if len(ys) else '-'}+)")
    eng.render(SRC, DevelopSettings(border="auto"), "fine", 1200)
    _, _, pw, ph = eng.last_info["inset"]
    engine.PREFS["show_frame"] = False
    nf = eng.render(SRC, DevelopSettings(border="auto"), "fine", 1200)
    engine.PREFS["show_frame"] = True
    check(nf.shape[:2] == (ph, pw), "frame hidden in preview when 'show frame' is off (gate kept)")
    full = engine.render_full(SRC, DevelopSettings(border="auto"), long_edge=1200, include_frame=False)
    check(abs(full.shape[0] / full.shape[1] - ph / pw) < 0.01, "export without frame keeps the gate's framing")
    framed = engine.render_full(SRC, DevelopSettings(border="auto"), long_edge=1200)
    check(framed.shape[0] > full.shape[0] and framed.shape[1] > full.shape[1], "export with the film strip")

    # --- a look's own edge lettering (camera-inspired looks name themselves, not the stock they use)
    from spektralionkk.borders import LOOK_EDGES, edge_style
    from spektralionkk.looks import LOOKS, look_values
    from spektralionkk.settings import SYNC_GROUPS

    camera = {n: v for n, (cat, _, v) in LOOKS.items() if cat == "Camera-inspired"}
    named = {n for n, v in camera.items() if v.get("edge_label")}
    check(named == set(camera) - {"Acros (Fujifilm-inspired)"} and
          all(v["edge_label"] in LOOK_EDGES for n, v in camera.items() if n in named),
          f"camera-inspired looks have their own edge lettering ({len(named)}; Acros keeps its stock's)")
    check(not any(v.get("edge_label") for n, (cat, _, v) in LOOKS.items() if cat != "Camera-inspired"),
          "film looks keep the stock's edge print")
    for name, want in (("Classic (Leica-inspired)", "LEICA CLASSIC"),
                       ("Chrome Classic (Fujifilm-inspired)", "CHROME CLASSIC"),
                       ("Positive Film (GR-inspired)", "POSITIVE FILM")):
        lv = look_values(LOOKS[name][2])
        st = edge_style(lv["film"], "", "negative", lv["edge_label"])
        check(st[0] == want and "KODAK" not in st[0] and "FUJI" not in st[0], f"{name}: edge reads {st[0]!r}")

    def strip_for(look):
        s = DevelopSettings(border="auto")
        for k, v in look_values(LOOKS[look][2]).items():
            setattr(s, k, v)
        return (engine.add_border(np.full((400, 600, 3), 0.4, np.float32), s, show_frame=True) * 255).astype(int)

    def red(img):  # red, not the orange of Kodak lettering (G / R stays ~0.57 for orange, even anti-aliased)
        r = img[..., 0]
        return (r > 120) & (img[..., 1] < 0.35 * r) & (img[..., 2] < 0.35 * r)

    def red_dot_px(img):
        return int(red(img[: (img.shape[0] - 400) // 2]).sum())  # in the upper rebate

    leica, ektar = strip_for("Contemporary (Leica-inspired)"), strip_for("Ektar 100 Landscape")
    check(leica.shape == ektar.shape and red_dot_px(leica) > 20 and red_dot_px(ektar) == 0,
          f"Leica-inspired look: LEICA in red on the film edge ({red_dot_px(leica)} px), not on Ektar's")
    check(np.abs(leica - ektar)[: (leica.shape[0] - 400) // 2].mean() > 1.0, "...and its own lettering")
    m = DevelopSettings(border="slide")
    for k, v in look_values(LOOKS["Monochrome (Leica-inspired)"][2]).items():
        setattr(m, k, v)
    mount = (engine.add_border(np.full((400, 600, 3), 0.4, np.float32), m, show_frame=True) * 255).astype(int)
    check(int(red(mount).sum()) > 10, "slide mount label with LEICA in red")
    old = DevelopSettings.from_dict({"look": "Classic (Leica-inspired)", "film": "kodak_portra_400", "_v": 3})
    check(old.edge_label == "leica_classic", "photos styled before 1.4 get their look's edge lettering")
    check("edge_label" in SYNC_GROUPS["Look & profile"] and "edge_label" not in SYNC_GROUPS["Film edge & border"],
          "the lettering is copied with the look, not with the frame style")
    Image.fromarray(leica.astype(np.uint8)).save(os.path.join(OUT, "frame_look_edge.png"))
    Image.fromarray(sl).save(os.path.join(OUT, "frame_slide.png"))
    Image.fromarray(ds.astype(np.uint8)).save(os.path.join(OUT, "date_stamp.png"))
    print("FEATURE TESTS", "FAILED: " + "; ".join(fails) if fails else "PASSED")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
