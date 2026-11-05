"""Lightroom-style panels: Develop (right) and Navigator / Looks / History (left)."""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from .. import profiles
from ..settings import (
    ASPECTS,
    BORDERS,
    CURVE_FIELDS,
    DIFFUSION_FAMILIES,
    EDGE_HOLES,
    EDGE_STYLES,
    FILM_FORMATS,
    HSL_BANDS,
    HSL_FIELDS,
    METERING,
    NO_PRINT,
    DevelopSettings,
)

PAPER_TOOLTIP = ("Paper = the photographic paper the negative is printed on in the darkroom.\n"
                 "A negative is an inverted orange image; the paper turns it into the final print, and each paper\n"
                 "has its own contrast, colour and saturation (like choosing a paper at a lab).\n"
                 "Cinema print films (2383 / 2393) give the look of a projected film print.\n"
                 "'Direct scan' skips the print: the film itself is scanned — that is how slides are viewed.")
PAPER_NOTES = {
    "kodak_portra_endura": "Portrait paper: soft contrast, gentle colour, natural skin.",
    "kodak_supra_endura": "Portrait / wedding paper: a little more colour and contrast than Portra Endura.",
    "kodak_ultra_endura": "High saturation and contrast for punchy, vivid prints.",
    "kodak_endura_premier": "Kodak's all-round professional paper: rich colour, standard contrast.",
    "kodak_ektacolor_edge": "Consumer lab paper: bright, saturated minilab prints.",
    "fujifilm_crystal_archive_typeii": "Fujifilm lab paper: crisp, clean colour with Fuji's greens.",
    "kodak_2383": "Cinema print film: dense blacks, strong contrast — the look of a projected film.",
    "kodak_2393": "Premium cinema print film: richer colour and contrast than 2383.",
    "ilford_multigrade_iv_rc": "Black & white paper; set its contrast with the grade (00–5).",
    NO_PRINT: "No print: the film itself is scanned (how slides are viewed). Negatives always need a paper.",
}
from ..i18n import tr, translate_tree, trf
from ..wb import WB_LABELS, WB_MODES
from .curve import CurveEditor
from .side import Histogram, HistoryPanel, LooksPanel, Navigator
from .widgets import HUE_GRADIENT, ComboRow, Section, SliderRow, TextRow, ToggleRow

DEFAULTS = DevelopSettings()


class _Binder(QtCore.QObject):
    """Holds field -> control bindings and turns control changes into edit dicts."""

    edited = QtCore.Signal(dict, bool)  # updates, final (False while dragging)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.binds: dict[str, QtWidgets.QWidget] = {}
        self.loading = False

    def emit(self, field, value, final):
        if not self.loading:
            self.edited.emit({field.split("#")[0]: value}, final)

    # A field may be shown in two places: bind the second control as "field#where".
    def slider(self, sec: Section, field: str, label: str, lo, hi, **kw) -> SliderRow:
        row = SliderRow(label, lo, hi, default=getattr(DEFAULTS, field.split("#")[0]), **kw)
        row.valueChanged.connect(lambda v, f=field: self.emit(f, v, False))
        row.committed.connect(lambda v, f=field: self.emit(f, v, True))
        sec.add(row)
        self.binds[field] = row
        return row

    def toggle(self, sec: Section, field: str, label: str, **kw) -> ToggleRow:
        row = ToggleRow(label, **kw)
        row.toggled.connect(lambda v, f=field: self.emit(f, bool(v), True))
        sec.add(row)
        self.binds[field] = row
        return row

    def combo(self, sec: Section, field: str, label: str, items, labels=None, **kw) -> ComboRow:
        row = ComboRow(label, items, labels, **kw)
        row.changed.connect(lambda v, f=field: self.emit(f, v, True))
        sec.add(row)
        self.binds[field] = row
        return row

    def text(self, sec: Section, field: str, label: str, **kw) -> TextRow:
        row = TextRow(label, **kw)
        row.changed.connect(lambda v, f=field: self.emit(f, v, True))
        sec.add(row)
        self.binds[field] = row
        return row

    def load(self, s: DevelopSettings):
        self.loading = True
        try:
            for field, w in self.binds.items():
                w.set_value(getattr(s, field.split("#")[0]))
        finally:
            self.loading = False


def _film_groups():
    films = profiles.film_stocks()
    return [
        ("No film", [(profiles.DIGITAL, "Digital (no film simulation)")]),
        ("Color negative", [(f.key, f.name) for f in films if f.kind == "negative" and not f.bw and f.use != "cine"]),
        ("Slide (positive)", [(f.key, f.name) for f in films if f.kind == "positive"]),
        ("Cine negative", [(f.key, f.name) for f in films if f.kind == "negative" and not f.bw and f.use == "cine"]),
        ("Black & white", [(f.key, f.name) for f in films if f.bw]),
    ]


def _paper_groups():
    papers = profiles.print_papers()
    return [
        ("Color paper", [(p.key, p.name) for p in papers if not p.bw and p.use != "cine"]),
        ("Cine print film", [(p.key, p.name) for p in papers if not p.bw and p.use == "cine"]),
        ("Black & white paper", [(p.key, p.name) for p in papers if p.bw]),
        ("Slides", [(NO_PRINT, "Direct scan (no print)")]),
    ]


class DevelopPanel(QtWidgets.QWidget):
    """Right panel: histogram + tools, then collapsible develop sections, Sync / Reset at the bottom."""

    edited = QtCore.Signal(dict, bool)
    importRequested = QtCore.Signal(str)  # 'lut' | 'preset'
    toolRequested = QtCore.Signal(str)  # 'crop' | 'wb' | 'split' | 'original'
    cropAction = QtCore.Signal(str)  # 'done' | 'cancel' | 'reset' | 'rotl' | 'rotr' | 'fliph' | 'flipv'
    syncRequested = QtCore.Signal()
    resetRequested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.b = _Binder(self)
        self.b.edited.connect(self.edited)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # --- histogram, camera info, tool strip
        top = QtWidgets.QWidget()
        tl = QtWidgets.QVBoxLayout(top)
        tl.setContentsMargins(10, 8, 10, 6)
        tl.setSpacing(4)
        self.hist = Histogram()
        tl.addWidget(self.hist)
        self.shot = QtWidgets.QLabel("")
        self.shot.setObjectName("Dim")
        self.shot.setAlignment(QtCore.Qt.AlignCenter)
        self.camera = QtWidgets.QLabel("")
        self.camera.setObjectName("Faint")
        self.camera.setAlignment(QtCore.Qt.AlignCenter)
        tl.addWidget(self.shot)
        tl.addWidget(self.camera)
        tools = QtWidgets.QHBoxLayout()
        tools.setSpacing(4)
        self.tool_buttons = {}
        for key, text, tip in (("crop", "⌗ Crop", "Crop & straighten (R)"),
                               ("wb", "◎ WB", "White balance picker (W) — click something neutral"),
                               ("split", "◫ Split", "Before / After split view (Y)"),
                               ("original", "◐ Original", "Show the original photo (\\)")):
            bt = QtWidgets.QToolButton()
            bt.setObjectName("Tool")
            bt.setText(text)
            bt.setToolTip(tip)
            bt.setCheckable(True)
            bt.clicked.connect(lambda _=False, k=key: self.toolRequested.emit(k))
            tools.addWidget(bt)
            self.tool_buttons[key] = bt
        tl.addLayout(tools)
        outer.addWidget(top)

        # --- crop tools (only in crop mode)
        self.crop_sec = Section("Crop & Straighten", resettable=False)
        self.b.combo(self.crop_sec, "aspect", "Aspect", list(ASPECTS.keys()), list(ASPECTS.keys()))
        self.b.slider(self.crop_sec, "straighten", "Angle", -15, 15, step=0.1, decimals=1, suffix="°")
        rot = QtWidgets.QHBoxLayout()
        for key, text, tip in (("rotl", "⟲", "Rotate left"), ("rotr", "⟳", "Rotate right"),
                               ("fliph", "⇋", "Flip horizontal"), ("flipv", "⇵", "Flip vertical"),
                               ("reset", "Reset", "Reset crop and angle")):
            bt = QtWidgets.QToolButton()
            bt.setText(text)
            bt.setToolTip(tip)
            bt.clicked.connect(lambda _=False, k=key: self.cropAction.emit(k))
            rot.addWidget(bt)
        rot.addStretch(1)
        w = QtWidgets.QWidget()
        w.setLayout(rot)
        self.crop_sec.add(w)
        hint = QtWidgets.QLabel("Drag the corners or edges, drag inside to move. Double-click or Enter to apply, "
                                "Esc to cancel.")
        hint.setObjectName("Faint")
        hint.setWordWrap(True)
        self.crop_sec.add(hint)
        db = QtWidgets.QHBoxLayout()
        cancel = QtWidgets.QPushButton("Cancel")
        done = QtWidgets.QPushButton("Done")
        done.setObjectName("Primary")
        cancel.clicked.connect(lambda: self.cropAction.emit("cancel"))
        done.clicked.connect(lambda: self.cropAction.emit("done"))
        db.addStretch(1)
        db.addWidget(cancel)
        db.addWidget(done)
        w = QtWidgets.QWidget()
        w.setLayout(db)
        self.crop_sec.add(w)
        self.crop_sec.setVisible(False)
        outer.addWidget(self.crop_sec)

        # --- scrolling develop sections
        scroll = QtWidgets.QScrollArea()
        scroll.setObjectName("Panel")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        body = QtWidgets.QWidget()
        body.setObjectName("PanelBody")
        self.lay = QtWidgets.QVBoxLayout(body)
        self.lay.setContentsMargins(0, 0, 0, 8)
        self.lay.setSpacing(0)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        self.sections: dict[str, Section] = {}
        b = self.b

        sec = self._sec("Profile", ("film", "paper", "bw_grade"))
        b.combo(sec, "film", "Film", _film_groups(),
                tooltip="The film the photo is exposed and developed on: its colour, contrast, grain and halation.")
        b.combo(sec, "paper", "Paper", _paper_groups(), tooltip=PAPER_TOOLTIP)
        self.paper_note = QtWidgets.QLabel("")
        self.paper_note.setObjectName("Faint")
        self.paper_note.setWordWrap(True)
        sec.add(self.paper_note)
        self.grade = b.slider(sec, "bw_grade", "Contrast grade", -1, 5, step=0.5, decimals=1,
                              sublabel="Multigrade  (−1 = 00)", signed=False,
                              tooltip="Multigrade filtration: 00 softest … 5 hardest")
        self.look_label = QtWidgets.QLabel("")
        self.look_label.setObjectName("Faint")
        sec.add(self.look_label)

        # --- Film Edge: the strip around the picture, and the date back
        sec = self._sec("Film Edge", ("border", "border_text", "frame_number", "edge_holes", "date_stamp",
                                      "date_text", "shoot_data"), collapsed=True)
        self.edge_sec = sec
        self._edge_style = "auto"
        self.edge_switch = sec.add_switch("Film Edge on / off: print the film strip around the picture — "
                                          "rebate, perforations, the stock's edge print and frame numbers")
        self.edge_switch.toggled.connect(self._edge_switched)
        b.combo(sec, "border", "Style", EDGE_STYLES, [BORDERS[k] for k in EDGE_STYLES],
                tooltip="Film strip: the negative or slide as a scan shows it — 135 with perforations, 120 with\n"
                        "its rebate — in the Format below. Or a filed carrier, a slide mount or a white border.")
        b.combo(sec, "film_format#edge", "Film format", list(FILM_FORMATS.keys()), list(FILM_FORMATS.keys()),
                tooltip="Film size. With Film Edge on, the picture is framed in this format's gate (e.g. 6×6 is\n"
                        "square) — move it inside the gate with the Crop tool. It also sets the grain scale.")
        b.combo(sec, "edge_holes", "Perforations", list(EDGE_HOLES), list(EDGE_HOLES.values()))
        b.toggle(sec, "border_text", "Edge print", sublabel="The stock's own lettering, frame numbers, DX code")
        b.slider(sec, "frame_number", "Frame no.", 0, 38, step=1, decimals=0, signed=False)
        sec.add_subhead("Date back")
        b.toggle(sec, "date_stamp", "Date", sublabel="Orange LED date: in the picture on 135, in the margin on 120")
        b.text(sec, "date_text", "Date text", placeholder="from the photo, e.g. '24 11 04",
               tooltip="Leave empty to use the date the photo was taken.")
        b.toggle(sec, "shoot_data", "Shooting data", sublabel="Shutter, aperture and focal length in the 120 margin")
        note = QtWidgets.QLabel("Hide it in the preview only: View ▸ Show Film Frame (Shift+F). Exports include it "
                                "unless you untick “Include the film frame”.")
        note.setObjectName("Faint")
        note.setWordWrap(True)
        sec.add(note)

        sec = self._sec("Basic", ("wb_mode", "temperature", "tint", "exposure_ev", "auto_exposure", "metering",
                                  "contrast", "highlights", "shadows", "whites", "blacks", "clarity", "vibrance",
                                  "saturation"))
        wbrow = QtWidgets.QHBoxLayout()
        wbrow.setContentsMargins(0, 0, 0, 0)
        self.wb_combo = ComboRow("WB", WB_MODES, WB_LABELS)
        self.wb_combo.changed.connect(lambda v: b.emit("wb_mode", v, True))
        b.binds["wb_mode"] = self.wb_combo
        wbrow.addWidget(self.wb_combo, 1)
        self.picker = QtWidgets.QToolButton()
        self.picker.setText("◎")
        self.picker.setToolTip("White balance picker (W): click something that should be neutral grey")
        self.picker.clicked.connect(lambda: self.toolRequested.emit("wb"))
        wbrow.addWidget(self.picker)
        w = QtWidgets.QWidget()
        w.setLayout(wbrow)
        sec.add(w)
        self.temp = SliderRow("Temp", 2000, 12000, step=10, decimals=0, default=5500, mapping="mired",
                              gradient=("#4a7fe0", "#e0b24a"), signed=False, suffix=" K")
        self.tint = SliderRow("Tint", -150, 150, step=1, decimals=0, default=0, gradient=("#4fae5a", "#c45ab4"))
        for row, field in ((self.temp, "temperature"), (self.tint, "tint")):
            row.valueChanged.connect(lambda v, f=field: self._wb_drag(f, v, False))
            row.committed.connect(lambda v, f=field: self._wb_drag(f, v, True))
            sec.add(row)
        sec.add_subhead("Tone")
        b.slider(sec, "exposure_ev", "Exposure", -5, 5, step=0.05, decimals=2, tooltip="Film exposure in stops")
        ae = QtWidgets.QHBoxLayout()
        ae.setContentsMargins(0, 0, 0, 0)
        self.ae = ToggleRow("Auto exposure")
        self.ae.toggled.connect(lambda v: b.emit("auto_exposure", bool(v), True))
        b.binds["auto_exposure"] = self.ae
        ae.addWidget(self.ae, 1)
        self.metering = QtWidgets.QComboBox()
        self.metering.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.metering.setMinimumContentsLength(9)
        for m in METERING:
            self.metering.addItem(m.replace("_", " ").capitalize(), m)
        self.metering.setToolTip("Metering pattern of the virtual camera")
        self.metering.currentIndexChanged.connect(lambda i: b.emit("metering", self.metering.itemData(i), True))
        ae.addWidget(self.metering)
        w = QtWidgets.QWidget()
        w.setLayout(ae)
        sec.add(w)
        for f, lab in (("contrast", "Contrast"), ("highlights", "Highlights"), ("shadows", "Shadows"),
                       ("whites", "Whites"), ("blacks", "Blacks")):
            b.slider(sec, f, lab, -100, 100, step=1, decimals=0)
        sec.add_subhead("Presence")
        for f, lab in (("clarity", "Clarity"), ("vibrance", "Vibrance"), ("saturation", "Saturation")):
            b.slider(sec, f, lab, -100, 100, step=1, decimals=0)

        sec = self._sec("Tone Curve", CURVE_FIELDS, collapsed=True)
        self.curves = CurveEditor()
        self.curves.changed.connect(lambda f, pts, final: self.edited.emit({f: pts}, final))
        sec.add(self.curves)

        sec = self._sec("Color Mixer", HSL_FIELDS, collapsed=True)
        tabs = QtWidgets.QHBoxLayout()
        tg = QtWidgets.QButtonGroup(self)
        self.hsl_pages = QtWidgets.QStackedWidget()
        band_cols = {"red": "#e8463a", "orange": "#ef8a2f", "yellow": "#e8d23a", "green": "#4fbf4f",
                     "aqua": "#3ac9c9", "blue": "#3a6ee8", "purple": "#8a4ae8", "magenta": "#d84ac0"}
        for k, (key, title) in enumerate((("hue", "Hue"), ("sat", "Saturation"), ("lum", "Luminance"))):
            bt = QtWidgets.QPushButton(title)
            bt.setObjectName("Seg")
            bt.setCheckable(True)
            bt.setChecked(k == 0)
            bt.clicked.connect(lambda _=False, i=k: self.hsl_pages.setCurrentIndex(i))
            tg.addButton(bt)
            tabs.addWidget(bt)
            page = QtWidgets.QWidget()
            pl = QtWidgets.QVBoxLayout(page)
            pl.setContentsMargins(0, 4, 0, 0)
            pl.setSpacing(5)
            fake = Section("", resettable=False)  # binder helper needs a Section to add rows to
            for band in HSL_BANDS:
                grad = (band_cols[band], band_cols[band]) if key != "lum" else ("#202020", band_cols[band])
                row = b.slider(fake, f"hsl_{key}_{band}", band.capitalize(), -100, 100, step=1, decimals=0,
                               gradient=grad)
                pl.addWidget(row)
            self.hsl_pages.addWidget(page)
        tabs.addStretch(1)
        w = QtWidgets.QWidget()
        w.setLayout(tabs)
        sec.add(w)
        sec.add(self.hsl_pages)

        sec = self._sec("Color Grading", tuple(f for f in DevelopSettings.__dataclass_fields__ if f.startswith("cg_")),
                        collapsed=True)
        for region, hue_f, sat_f in (("Shadows", "cg_shadow_hue", "cg_shadow_sat"),
                                     ("Midtones", "cg_mid_hue", "cg_mid_sat"),
                                     ("Highlights", "cg_high_hue", "cg_high_sat")):
            sec.add_subhead(region)
            b.slider(sec, hue_f, "Hue", 0, 360, step=1, decimals=0, gradient=HUE_GRADIENT, signed=False, suffix="°")
            b.slider(sec, sat_f, "Saturation", 0, 100, step=1, decimals=0, signed=False)
        sec.add_subhead("Overall")
        b.slider(sec, "cg_balance", "Balance", -100, 100, step=1, decimals=0)
        b.slider(sec, "cg_blending", "Blending", 0, 100, step=1, decimals=0, signed=False)

        sec = self._sec("Enlarger", ("print_brightness", "yellow", "magenta", "preflash", "print_contrast",
                                     "developer_exhaustion", "auto_print_compensation"))
        b.slider(sec, "print_brightness", "Brightness", -3, 3, step=0.05, decimals=2, sublabel="print time, stops")
        b.slider(sec, "yellow", "Yellow", -60, 60, step=1, decimals=0, sublabel="CC filter",
                 gradient=("#4a6fd8", "#d8b84a"))
        b.slider(sec, "magenta", "Magenta", -60, 60, step=1, decimals=0, sublabel="CC filter",
                 gradient=("#4fae5a", "#c45ab4"))
        b.slider(sec, "preflash", "Pre-flash", 0, 0.1, step=0.001, decimals=1, scale=100, sublabel="×100",
                 signed=False, tooltip="Uniform pre-exposure of the paper: lifts and softens the print's shadows")
        b.slider(sec, "print_contrast", "Paper contrast", 0.6, 1.6, step=0.01, decimals=2, signed=False)
        b.slider(sec, "developer_exhaustion", "Developer", 0, 1, step=0.02, decimals=2, sublabel="exhaustion",
                 signed=False)
        b.toggle(sec, "auto_print_compensation", "Lab auto-print",
                 sublabel="Printer cancels film exposure changes")

        sec = self._sec("Film & Grain", ("film_format", "grain", "grain_size", "halation", "halation_amount",
                                         "scatter_amount", "highlight_boost", "couplers", "couplers_amount",
                                         "negative_contrast"), collapsed=True)
        b.combo(sec, "film_format", "Film format", list(FILM_FORMATS.keys()), list(FILM_FORMATS.keys()),
                tooltip="Larger formats enlarge less: finer grain, tighter halation")
        b.toggle(sec, "grain", "Grain", sublabel="Simulated at 100% zoom and in exports")
        b.slider(sec, "grain_size", "Grain size", 0.02, 1.2, step=0.01, decimals=2, sublabel="µm² particle",
                 signed=False)
        b.toggle(sec, "halation", "Halation", sublabel="Red glow around very bright lights; best seen at 100%",
                 tooltip="Light reflected from the film base back into the emulsion. Its physical radius is a "
                         "fraction of a millimetre, so it shows as a fine red fringe at fitted size.")
        b.slider(sec, "halation_amount", "Halation", 0, 4, step=0.05, decimals=2, signed=False)
        b.slider(sec, "scatter_amount", "Scatter", 0, 3, step=0.05, decimals=2, signed=False)
        b.slider(sec, "highlight_boost", "Highlight boost", 0, 6, step=0.1, decimals=1, signed=False,
                 tooltip="Restores the energy of clipped highlights (lamps, sun, reflections) so they bloom and "
                         "halate like real light sources. A digital photo clips them at white.")
        b.toggle(sec, "couplers", "DIR couplers", sublabel="Inter-layer effects: saturation, edge contrast")
        b.slider(sec, "couplers_amount", "Couplers", 0, 2, step=0.05, decimals=2, signed=False)
        b.slider(sec, "negative_contrast", "Negative gamma", 0.6, 1.5, step=0.01, decimals=2, signed=False)

        sec = self._sec("Effects", ("vignette", "vignette_midpoint", "glare", "glare_amount", "diffusion",
                                    "diffusion_family", "diffusion_strength"), collapsed=True)
        sec.add_subhead("Vignette")
        b.slider(sec, "vignette", "Amount", -100, 100, step=1, decimals=0)
        b.slider(sec, "vignette_midpoint", "Midpoint", 0, 100, step=1, decimals=0, signed=False)
        sec.add_subhead("Print surface")
        b.toggle(sec, "glare", "Surface glare")
        b.slider(sec, "glare_amount", "Glare", 0, 0.25, step=0.005, decimals=1, scale=100, suffix="%", signed=False)
        sec.add_subhead("Lens filter")
        b.toggle(sec, "diffusion", "Diffusion filter")
        b.combo(sec, "diffusion_family", "Type", DIFFUSION_FAMILIES,
                ["Black mist", "Pro mist", "Glimmer glass", "Cine bloom"])
        b.slider(sec, "diffusion_strength", "Strength", 0, 2, step=0.125, decimals=3, signed=False)
        sec.add_subhead("Creative LUT")
        lrow = QtWidgets.QHBoxLayout()
        lrow.setContentsMargins(0, 0, 0, 0)
        lab = QtWidgets.QLabel("LUT")
        lab.setMinimumWidth(86)
        lrow.addWidget(lab)
        self.lut_combo = QtWidgets.QComboBox()
        self.lut_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.lut_combo.setMinimumContentsLength(8)
        self.lut_combo.setToolTip(".cube LUTs for standard (sRGB / Rec.709) images")
        self.lut_combo.currentIndexChanged.connect(
            lambda i: b.emit("lut_name", self.lut_combo.itemData(i) or "", True) if i >= 0 else None)
        lrow.addWidget(self.lut_combo, 1)
        imp = QtWidgets.QToolButton()
        imp.setText("Import…")
        imp.setToolTip("Import a .cube LUT")
        imp.clicked.connect(lambda: self.importRequested.emit("lut"))
        lrow.addWidget(imp)
        w = QtWidgets.QWidget()
        w.setLayout(lrow)
        sec.add(w)
        b.slider(sec, "lut_amount", "Amount", 0, 100, step=1, decimals=0, signed=False, suffix="%")
        self.refresh_luts()

        sec = self._sec("Detail", ("sharpen", "white_correction", "black_correction"), collapsed=True)
        b.slider(sec, "sharpen", "Sharpening", 0, 2, step=0.05, decimals=2, signed=False)
        b.toggle(sec, "white_correction", "White point correction")
        b.toggle(sec, "black_correction", "Black point correction")

        sec = self._sec("Lens", ("lens_correction",), collapsed=True)
        b.toggle(sec, "lens_correction", "Lens correction", sublabel="Lensfun profile from EXIF (RAW files)")
        self.lay.addStretch(1)

        foot = QtWidgets.QWidget()
        foot.setObjectName("PanelFoot")
        foot.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        fl = QtWidgets.QHBoxLayout(foot)
        fl.setContentsMargins(10, 6, 10, 6)
        self.sync_btn = QtWidgets.QPushButton("Sync…")
        self.sync_btn.setToolTip("Copy chosen settings from this photo to the selected photos (Ctrl+Shift+S)")
        reset = QtWidgets.QPushButton("Reset")
        reset.setToolTip("Reset this photo to the default settings (Ctrl+R)")
        self.sync_btn.clicked.connect(self.syncRequested)
        reset.clicked.connect(self.resetRequested)
        fl.addWidget(self.sync_btn, 1)
        fl.addWidget(reset, 1)
        outer.addWidget(foot)
        self._wb_shown = (5500.0, 0.0)

    def _sec(self, title, fields, **kw):
        sec = Section(title, **kw)
        sec.resetRequested.connect(lambda f=tuple(fields): self.edited.emit(
            {k: getattr(DEFAULTS, k) for k in f}, True))
        self.lay.addWidget(sec)
        self.sections[title] = sec
        return sec

    def _edge_switched(self, on: bool):
        if self.b.loading:
            return
        if on:
            self.edge_sec.set_collapsed(False)
        self.edited.emit({"border": (self._edge_style or "auto") if on else "none"}, True)

    # --- white balance: dragging Temp/Tint switches to Custom, starting from what is shown
    def _wb_drag(self, field, value, final):
        if self.b.loading:
            return
        T = value if field == "temperature" else self.temp.value()
        t = value if field == "tint" else self.tint.value()
        self.edited.emit({"wb_mode": "custom", "temperature": float(T), "tint": float(t)}, final)

    def refresh_luts(self, select: str | None = None):
        from .. import luts

        cur = select if select is not None else (self.lut_combo.currentData() or "")
        self.lut_combo.blockSignals(True)
        self.lut_combo.clear()
        self.lut_combo.addItem("None", "")
        for name in luts.available():
            self.lut_combo.addItem(name, name)
        i = self.lut_combo.findData(cur)
        self.lut_combo.setCurrentIndex(max(0, i))
        self.lut_combo.blockSignals(False)

    def set_wb_display(self, T, tint):
        self._wb_shown = (T, tint)
        self.temp.set_value(T)
        self.tint.set_value(tint)

    def set_tool(self, key, on):
        bt = self.tool_buttons.get(key)
        if bt is not None:
            bt.setChecked(on)

    def load(self, s: DevelopSettings, *, raw: bool, wb_shown=None):
        self.b.load(s)
        i = self.metering.findData(s.metering)
        self.metering.blockSignals(True)
        self.metering.setCurrentIndex(max(0, i))
        self.metering.blockSignals(False)
        if s.wb_mode == "custom":
            self.set_wb_display(s.temperature, s.tint)
        elif wb_shown:
            self.set_wb_display(*wb_shown)
        bw_paper = s.paper == profiles.BW_PAPER
        digital = s.film == profiles.DIGITAL
        self.grade.setVisible(bw_paper and not digital)
        self.b.binds["paper"].setEnabled(not digital)
        self.curves.set_curves({f: getattr(s, f) for f in CURVE_FIELDS})
        if self.lut_combo.findData(s.lut_name) < 0 and s.lut_name:
            self.refresh_luts(s.lut_name)
        self.lut_combo.blockSignals(True)
        self.lut_combo.setCurrentIndex(max(0, self.lut_combo.findData(s.lut_name)))
        self.lut_combo.blockSignals(False)
        self.b.binds["lut_amount"].setEnabled(bool(s.lut_name))
        film = profiles.stock_by_key(s.film)
        self.look_label.setText(trf("Look: {name}", name=tr(s.look)) if s.look else "")
        from ..engine import effective_paper, frame_kind

        if digital:
            note = tr("No paper: the Digital profile is not printed.")
        else:
            note = tr(PAPER_NOTES.get(s.paper, ""))
            used = effective_paper(s)
            if used != s.paper:  # e.g. 'Direct scan' chosen for a negative
                st = profiles.stock_by_key(used)
                note += trf(" A negative still needs a paper: printed on {paper}.", paper=st.name if st else used)
        self.paper_note.setText(note)
        edge_on = s.border != "none"
        if edge_on:
            self._edge_style = s.border
        self.edge_switch.blockSignals(True)
        self.edge_switch.setChecked(edge_on)
        self.edge_switch.blockSignals(False)
        edge_kind = frame_kind(s)
        enable = {
            "grain_size": s.grain, "halation_amount": s.halation, "scatter_amount": s.halation,
            "highlight_boost": s.halation, "couplers_amount": s.couplers and not (film and film.bw),
            "couplers": not (film and film.bw), "glare_amount": s.glare, "diffusion_family": s.diffusion,
            "diffusion_strength": s.diffusion, "lens_correction": raw,
            "border": edge_on, "film_format#edge": edge_on, "edge_holes": edge_kind == "135",
            "border_text": edge_kind in ("135", "120", "slide"),
            "frame_number": edge_kind in ("135", "120", "slide") and s.border_text,
            "date_text": s.date_stamp, "shoot_data": edge_kind == "120", "vignette_midpoint": s.vignette != 0,
        }
        for f, on in enable.items():
            w = self.b.binds.get(f)
            if w is not None:
                w.setEnabled(bool(on))
        self.metering.setEnabled(s.auto_exposure)
        slide = s.paper == NO_PRINT or digital
        for f in ("print_brightness", "yellow", "magenta", "preflash", "print_contrast", "developer_exhaustion"):
            self.b.binds[f].setEnabled(not slide)
        for f in ("film_format", "grain", "grain_size", "halation", "halation_amount", "scatter_amount",
                  "highlight_boost", "couplers", "couplers_amount", "negative_contrast", "glare", "glare_amount",
                  "diffusion", "diffusion_family", "diffusion_strength"):
            # film-only controls have nothing to act on with the Digital (no film) profile
            self.b.binds[f].setEnabled(bool(enable.get(f, True)) and not digital)

    def set_info(self, info: dict):
        ex = (info or {}).get("exif") or {}
        self.shot.setText(ex.get("shot", ""))
        cam = " · ".join(x for x in (ex.get("camera", ""), ex.get("lens", "")) if x)
        fs = (info or {}).get("full_size")
        if fs:
            cam = (cam + "   ·   " if cam else "") + f"{fs[0]} × {fs[1]}"
        self.camera.setText(cam)


class LeftPanel(QtWidgets.QWidget):
    """Navigator (+ zoom presets), Looks, History, and Copy / Paste."""

    zoomPreset = QtCore.Signal(str)  # 'fit' | 'fill' | '100' | '200'
    copyRequested = QtCore.Signal()
    pasteRequested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        nav_sec = Section("Navigator", resettable=False)
        grp = QtWidgets.QButtonGroup(self)
        self.zoom_buttons = {}
        for key, text in (("fit", "FIT"), ("fill", "FILL"), ("100", "100%"), ("200", "200%")):
            bt = QtWidgets.QPushButton(text)
            bt.setObjectName("Zoom")
            bt.setCheckable(True)
            grp.addButton(bt)
            bt.clicked.connect(lambda _=False, k=key: self.zoomPreset.emit(k))
            nav_sec.extra.addWidget(bt)
            self.zoom_buttons[key] = bt
        self.zoom_buttons["fit"].setChecked(True)
        self.navigator = Navigator()
        nav_sec.form.setContentsMargins(6, 6, 6, 6)
        nav_sec.add(self.navigator)
        outer.addWidget(nav_sec)

        self.looks_sec = Section("Looks", resettable=False)
        add = QtWidgets.QToolButton()
        add.setObjectName("Mini")
        add.setText("＋")
        add.setToolTip("Save the current settings as a Look")
        self.looks_sec.extra.addWidget(add)
        self.looks = LooksPanel()
        add.clicked.connect(self.looks.saveLook)
        self.looks_sec.form.setContentsMargins(0, 0, 0, 0)
        self.looks_sec.add(self.looks)
        outer.addWidget(self.looks_sec, 1)

        self.hist_sec = Section("History", resettable=False, collapsed=True)
        self.history = HistoryPanel()
        self.history.setFixedHeight(190)
        self.hist_sec.form.setContentsMargins(0, 0, 0, 0)
        self.hist_sec.add(self.history)
        outer.addWidget(self.hist_sec, 0)

        foot = QtWidgets.QWidget()
        foot.setObjectName("PanelFoot")
        foot.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        fl = QtWidgets.QHBoxLayout(foot)
        fl.setContentsMargins(10, 6, 10, 6)
        copy = QtWidgets.QPushButton("Copy…")
        copy.setToolTip("Copy settings of this photo (Ctrl+Shift+C)")
        paste = QtWidgets.QPushButton("Paste")
        paste.setToolTip("Paste copied settings to this and the selected photos (Ctrl+Shift+V)")
        copy.clicked.connect(self.copyRequested)
        paste.clicked.connect(self.pasteRequested)
        fl.addWidget(copy, 1)
        fl.addWidget(paste, 1)
        outer.addWidget(foot)

    def set_zoom_state(self, pct, fit):
        key = "fit" if fit else {100: "100", 200: "200"}.get(int(round(pct)), None)
        for k, bt in self.zoom_buttons.items():
            bt.setChecked(k == key)


class GroupsDialog(QtWidgets.QDialog):
    """Copy / Sync settings dialog with group check boxes (Lightroom's Copy Settings)."""

    def __init__(self, title, groups, checked, button, parent=None, note=""):
        super().__init__(parent)
        self.setWindowTitle(tr(title))
        lay = QtWidgets.QVBoxLayout(self)
        if note:
            lab = QtWidgets.QLabel(tr(note))
            lab.setObjectName("Dim")
            lab.setWordWrap(True)
            lay.addWidget(lab)
        self.boxes = {}
        for g in groups:
            cb = QtWidgets.QCheckBox(tr(g).replace("&", "&&"))
            cb.setChecked(g in checked)
            lay.addWidget(cb)
            self.boxes[g] = cb
        row = QtWidgets.QHBoxLayout()
        all_b = QtWidgets.QPushButton("Check all")
        none_b = QtWidgets.QPushButton("Check none")
        all_b.clicked.connect(lambda: [cb.setChecked(True) for cb in self.boxes.values()])
        none_b.clicked.connect(lambda: [cb.setChecked(False) for cb in self.boxes.values()])
        row.addWidget(all_b)
        row.addWidget(none_b)
        row.addStretch(1)
        lay.addLayout(row)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.button(QtWidgets.QDialogButtonBox.Ok).setText(button)
        bb.button(QtWidgets.QDialogButtonBox.Ok).setObjectName("Primary")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        translate_tree(self)

    def groups(self):
        return [g for g, cb in self.boxes.items() if cb.isChecked()]
