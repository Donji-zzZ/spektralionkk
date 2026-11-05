"""Built-in Looks: film + paper + finishing presets.

The camera-inspired looks are approximations of the character commonly described for those
cameras' colour modes, built from this app's film simulation and finishing tools. They are not the
manufacturers' own profiles (those are proprietary) and the names only describe the inspiration;
spektralionkk is not affiliated with Ricoh, Leica or Fujifilm.

A look sets the fields in settings.LOOK_FIELDS (anything not listed takes its default) and leaves
exposure, white balance, crop and border alone. A camera-inspired look also gives the Film Edge its own
lettering (edge_label, see borders.LOOK_EDGES) instead of the name of the stock it is built on.
"""

from __future__ import annotations

from .settings import LOOK_FIELDS, DevelopSettings

# name -> (category, description, values)
LOOKS: dict[str, tuple[str, str, dict]] = {
    # ---- camera-inspired -------------------------------------------------------------
    "Positive Film (GR-inspired)": (
        "Camera-inspired", "Punchy slide-film colour, deep contrast, warm highlights over cool shadows.",
        dict(film="fujifilm_provia_100f", paper="none", contrast=18, highlights=-10, vibrance=12,
             cg_shadow_hue=200, cg_shadow_sat=14, cg_high_hue=45, cg_high_sat=12, vignette=-18,
             edge_label="positive_film")),
    "Negative Film (GR-inspired)": (
        "Camera-inspired", "Soft, faded lab-print look: lifted blacks, cyan shadows, muted greens.",
        dict(film="kodak_portra_160", paper="kodak_portra_endura", print_contrast=0.88, blacks=22, shadows=15,
             highlights=-12, saturation=-14, cg_shadow_hue=190, cg_shadow_sat=22, cg_high_hue=40,
             cg_high_sat=10, grain_size=0.25, edge_label="negative_film")),
    # The Leica-inspired looks aim at the dense "German" rendering: deep, rich colour rather than bright colour
    # (darker blues, greens and reds), deep blacks, strong local contrast and the lenses' dark corners.
    "Classic (Leica-inspired)": (
        "Camera-inspired", "Deep, dense colour: rich reds, dark blues, cool greens, deep shadows and strong "
                           "vignetting — the classic German rendering.",
        dict(film="kodak_portra_400", paper="kodak_endura_premier", yellow=5, contrast=12, clarity=12, blacks=-10,
             shadows=-4, highlights=-14, saturation=4, vibrance=4, grain_size=0.25, hsl_hue_green=10,
             hsl_sat_green=-8, hsl_sat_yellow=-16, hsl_lum_blue=-14, hsl_lum_green=-10, hsl_lum_red=-8,
             cg_shadow_hue=200, cg_shadow_sat=10, cg_high_hue=40, cg_high_sat=6, vignette=-28,
             edge_label="leica_classic")),
    "Contemporary (Leica-inspired)": (
        "Camera-inspired", "Crisp and vivid but dense: deep blues and greens, strong local contrast, clean "
                           "neutral whites.",
        dict(film="kodak_ektar_100", paper="kodak_endura_premier", yellow=12, contrast=18, clarity=24,
             vibrance=14, blacks=-6, highlights=-10, whites=4, grain_size=0.12, hsl_hue_green=8,
             hsl_sat_yellow=-10, hsl_lum_blue=-14, hsl_lum_green=-6, vignette=-18,
             edge_label="leica_contemporary")),
    "Eternal (Leica-inspired)": (
        "Camera-inspired", "Cinematic and dense: teal shadows, amber highlights, restrained colour, deep blacks.",
        dict(film="kodak_vision3_250d", paper="kodak_2383", saturation=-12, contrast=16, blacks=-12, clarity=10,
             cg_shadow_hue=192, cg_shadow_sat=24, cg_high_hue=38, cg_high_sat=18, hsl_hue_green=14,
             hsl_sat_green=-12, hsl_lum_blue=-10, vignette=-24, edge_label="leica_eternal")),
    "Monochrome (Leica-inspired)": (
        "Camera-inspired", "Deep blacks and crisp midtone contrast with dark corners (Tri-X on Multigrade "
                           "grade 3½).",
        dict(film="kodak_tri_x_400", paper="ilford_multigrade_iv_rc", bw_grade=3.5, clarity=20, blacks=-8,
             highlights=-8, vignette=-24, edge_label="leica_monochrome")),
    "Chrome Classic (Fujifilm-inspired)": (
        "Camera-inspired", "Muted slide colour with hard shadows — documentary feel.",
        dict(film="kodak_ektachrome_100", paper="none", saturation=-32, contrast=12, shadows=-12,
             highlights=-10, cg_shadow_hue=205, cg_shadow_sat=8, edge_label="chrome_classic")),
    "Neg Classic (Fujifilm-inspired)": (
        "Camera-inspired", "Hard, low-saturation negative look with cyan-leaning shadows and warm skin.",
        dict(film="fujifilm_c200", paper="fujifilm_crystal_archive_typeii", contrast=16, saturation=-12,
             shadows=-8, cg_shadow_hue=185, cg_shadow_sat=16, cg_high_hue=30, cg_high_sat=8,
             edge_label="neg_classic")),
    "Eterna (Fujifilm-inspired)": (
        "Camera-inspired", "Flat cinema negative look with lots of shadow detail.",
        dict(film="kodak_vision3_250d", paper="kodak_2383", print_contrast=0.85, saturation=-22, shadows=18,
             highlights=-15, blacks=6, edge_label="eterna")),
    "Acros (Fujifilm-inspired)": (
        "Camera-inspired", "Fine-grained, smooth black-and-white (Neopan Acros 100 II, grade 2½).",
        dict(film="fujifilm_neopan_acros_100_ii", paper="ilford_multigrade_iv_rc", bw_grade=2.5,
             grain_size=0.12)),
    # ---- classic films -----------------------------------------------------------
    "Portra 400 Portrait": (
        "Film classics", "The wedding and portrait staple: warm skin, gentle contrast.",
        dict(film="kodak_portra_400", paper="kodak_portra_endura")),
    "Gold 200 Summer": (
        "Film classics", "Consumer-film warmth and saturation, a little nostalgic.",
        dict(film="kodak_gold_200", paper="kodak_ektacolor_edge", vibrance=8, cg_high_hue=45, cg_high_sat=10)),
    "Ektar 100 Landscape": (
        "Film classics", "Ultra-saturated, fine grain — skies and foliage.",
        dict(film="kodak_ektar_100", paper="kodak_endura_premier", vibrance=10, clarity=8)),
    "Superia-style X-Tra 400": (
        "Film classics", "Fujifilm consumer negative: cool greens, punchy.",
        dict(film="fujifilm_xtra_400", paper="fujifilm_crystal_archive_typeii", contrast=8)),
    "Kodachrome 64": (
        "Film classics", "The legendary slide film: deep reds, dense shadows.",
        dict(film="kodak_kodachrome_64", paper="none")),
    "Velvia 100": (
        "Film classics", "Vivid slide film for landscapes.",
        dict(film="fujifilm_velvia_100", paper="none")),
    "Provia 100F": (
        "Film classics", "Accurate, neutral slide film.",
        dict(film="fujifilm_provia_100f", paper="none")),
    "Pro 400H Airy": (
        "Film classics", "Pastel, airy greens and skin — overexposed-film look.",
        dict(film="fujifilm_pro_400h", paper="fujifilm_crystal_archive_typeii", blacks=10, shadows=10,
             saturation=-8)),
    # ---- cinema --------------------------------------------------------------------
    "CineStill 800T Night": (
        "Cinema", "Tungsten film without anti-halation, printed on photo paper: red glow around lights, "
                  "teal shadows.",
        dict(film="cinestill_800t", paper="kodak_portra_endura", halation_amount=1.5, highlight_boost=2.0,
             cg_shadow_hue=190, cg_shadow_sat=18, vibrance=12, blacks=6)),
    "Vision3 500T Tungsten": (
        "Cinema", "Motion-picture negative printed on Vision 2383.",
        dict(film="kodak_vision3_500t", paper="kodak_2383")),
    "Vision3 50D Daylight": (
        "Cinema", "Fine-grain daylight cine stock on 2383.",
        dict(film="kodak_vision3_50d", paper="kodak_2383")),
    "Bleach Bypass": (
        "Cinema", "Desaturated, high-contrast, silver-retained look.",
        dict(film="kodak_vision3_250d", paper="kodak_2383", saturation=-55, contrast=30, clarity=15,
             print_contrast=1.15)),
    # ---- black & white ----------------------------------------------------------------
    "Tri-X 400": (
        "Black & white", "Classic reportage B&W, grade 2.",
        dict(film="kodak_tri_x_400", paper="ilford_multigrade_iv_rc", bw_grade=2.0, grain_size=0.3)),
    "HP5 Plus Pushed": (
        "Black & white", "Gritty, contrasty — HP5 printed hard (grade 4).",
        dict(film="ilford_hp5_plus_400", paper="ilford_multigrade_iv_rc", bw_grade=4.0, grain_size=0.55,
             clarity=10)),
    "T-Max 100 Fine": (
        "Black & white", "Smooth tonality and very fine grain.",
        dict(film="kodak_tmax_100", paper="ilford_multigrade_iv_rc", bw_grade=2.0, grain_size=0.1)),
    "Soft Grade 1": (
        "Black & white", "Low-contrast, delicate print on grade 1.",
        dict(film="fujifilm_neopan_acros_100_ii", paper="ilford_multigrade_iv_rc", bw_grade=1.0)),
}

CATEGORIES = ["Camera-inspired", "Film classics", "Cinema", "Black & white", "My Looks"]


def look_values(values: dict) -> dict:
    """Complete field dict for a look: listed values, everything else in LOOK_FIELDS at its default."""
    d = DevelopSettings()
    out = {f: getattr(d, f) for f in LOOK_FIELDS}
    out.update({k: v for k, v in values.items() if k in LOOK_FIELDS})
    return out


def capture(s: DevelopSettings) -> dict:
    """The look-relevant part of the current settings (for 'Save Look…')."""
    d = DevelopSettings()
    return {f: getattr(s, f) for f in LOOK_FIELDS if getattr(s, f) != getattr(d, f) or f in ("film", "paper")}
