"""Dark darkroom theme (Lightroom-like greys) with a safelight-red accent."""

from PySide6 import QtCore, QtGui, QtWidgets

BG = "#151516"           # window / canvas surround
PANEL = "#1e1e20"        # side panels
PANEL_HEAD = "#262629"   # section header bars
PANEL_2 = "#2b2b2f"      # inputs, hover
LINE = "#323236"         # separators
TEXT = "#e6e4e1"
TEXT_DIM = "#9a9894"
TEXT_FAINT = "#64625f"
ACCENT = "#e4573d"       # safelight red
ACCENT_SOFT = "#4a2620"
CANVAS = "#101011"

# Inter for text; the system fallbacks supply the arrows, stars, icons and Chinese characters Inter lacks
# (Windows: Segoe UI Symbol / Emoji, Microsoft YaHei; macOS: Apple Symbols / Color Emoji, PingFang SC).
FALLBACKS = ["Segoe UI Variable Text", "Segoe UI", "Segoe UI Symbol", "Segoe UI Emoji", "Microsoft YaHei UI",
             "Helvetica Neue", "Apple Symbols", "Apple Color Emoji", "PingFang SC", "Hiragino Sans GB"]
FONT_STACK = '"Inter", ' + ", ".join(f'"{f}"' for f in FALLBACKS) + ", sans-serif"

QSS = f"""
* {{ font-family: {FONT_STACK}; font-size: 9pt; color: {TEXT}; }}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget#Panel, QScrollArea#Panel, QWidget#PanelBody {{ background: {PANEL}; }}
QWidget#TopBar, QWidget#ToolBar {{ background: {PANEL}; }}
QWidget#TopBar {{ border-bottom: 1px solid {LINE}; }}
QWidget#ToolBar {{ border-top: 1px solid {LINE}; }}
QWidget#Filmstrip {{ background: {PANEL}; border-top: 1px solid {LINE}; }}
QWidget#PanelFoot {{ background: {PANEL}; border-top: 1px solid {LINE}; }}
QLabel#PanelTitle {{ font-size: 10.5pt; font-weight: 600; }}
QLabel#Dim {{ color: {TEXT_DIM}; }}
QLabel#Faint {{ color: {TEXT_FAINT}; font-size: 8pt; }}
QLabel#SubHead {{ color: {TEXT_DIM}; font-weight: 600; font-size: 8.5pt; padding-top: 4px; }}
QLabel#FileInfo {{ color: {TEXT_DIM}; }}
QWidget#SectionHead {{ background: {PANEL_HEAD}; border-top: 1px solid {LINE}; }}
QPushButton#SectionHeader {{ border: none; font-size: 9pt; font-weight: 600; text-align: left; padding: 6px 2px; background: transparent; letter-spacing: 0.2px; }}
QPushButton#SectionHeader:hover {{ color: white; }}
QFrame#Separator {{ background: {LINE}; max-height: 1px; min-height: 1px; border: none; }}
QToolButton {{ background: transparent; border: none; border-radius: 5px; padding: 4px 7px; }}
QToolButton:hover {{ background: {PANEL_2}; }}
QToolButton:checked {{ background: {ACCENT_SOFT}; color: white; }}
QToolButton#Mini {{ color: {TEXT_DIM}; padding: 1px 4px; }}
QToolButton#Tool {{ border: 1px solid {LINE}; padding: 4px 9px; }}
QToolButton#Tool:checked {{ border-color: {ACCENT}; }}
QPushButton {{ background: {PANEL_2}; border: 1px solid {LINE}; border-radius: 5px; padding: 4px 12px; }}
QPushButton:hover {{ border-color: #4a4a50; }}
QPushButton:default, QPushButton#Primary {{ background: {ACCENT}; border-color: {ACCENT}; color: white; font-weight: 600; }}
QPushButton:disabled {{ color: {TEXT_FAINT}; }}
QPushButton#Seg {{ border-radius: 10px; padding: 2px 12px; background: transparent; border: 1px solid {LINE}; color: {TEXT_DIM}; font-weight: 600; }}
QPushButton#Seg:checked {{ border-color: {ACCENT}; color: {ACCENT}; background: {ACCENT_SOFT}; }}
QPushButton#Zoom {{ border: none; background: transparent; color: {TEXT_DIM}; padding: 2px 6px; font-size: 8.5pt; font-weight: 600; }}
QPushButton#Zoom:checked {{ color: {TEXT}; background: {PANEL_2}; }}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{ background: {PANEL_2}; border: 1px solid {LINE}; border-radius: 4px; padding: 2px 6px; selection-background-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 16px; }}
QComboBox QAbstractItemView {{ background: {PANEL_2}; border: 1px solid {LINE}; selection-background-color: {ACCENT_SOFT}; outline: none; }}
QLineEdit#Value {{ background: transparent; border: 1px solid transparent; border-radius: 3px; padding: 0px 2px; }}
QLineEdit#Value:hover {{ border-color: {LINE}; }}
QLineEdit#Value:focus {{ border-color: {ACCENT}; background: {PANEL_2}; }}
QLineEdit#Value:disabled {{ color: {TEXT_FAINT}; }}
QSlider::groove:horizontal {{ height: 2px; background: #45454b; border-radius: 1px; }}
QSlider::sub-page:horizontal, QSlider::add-page:horizontal {{ background: transparent; }}
QSlider::handle:horizontal {{ background: {TEXT}; width: 9px; height: 9px; margin: -4px 0; border-radius: 4px; }}
QSlider::handle:horizontal:hover {{ background: white; }}
QSlider:disabled::handle:horizontal {{ background: {TEXT_FAINT}; }}
QCheckBox::indicator {{ width: 13px; height: 13px; border-radius: 3px; border: 1px solid #55555b; background: {PANEL_2}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QCheckBox#HeadSwitch::indicator {{ width: 24px; height: 12px; border-radius: 6px; border: 1px solid #55555b; background: {PANEL_2}; }}
QCheckBox#HeadSwitch::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QListWidget, QTreeWidget {{ background: transparent; border: none; outline: none; }}
QListWidget#Looks::item, QListWidget#History::item {{ padding: 2px 4px; border-radius: 4px; }}
QListWidget#Looks::item:hover, QListWidget#History::item:hover {{ background: {PANEL_2}; }}
QListWidget#Looks::item:selected, QListWidget#History::item:selected {{ background: {ACCENT_SOFT}; color: white; }}
QListWidget#Strip::item {{ border: 2px solid transparent; border-radius: 4px; margin: 2px; }}
QListWidget#Strip::item:selected {{ border-color: {ACCENT}; background: {ACCENT_SOFT}; }}
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #3a3a3f; border-radius: 4px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 9px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: #3a3a3f; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; border: none; width: 0; height: 0; }}
QMenuBar {{ background: {PANEL}; }}
QMenuBar::item:selected {{ background: {PANEL_2}; }}
QMenu {{ background: {PANEL_2}; border: 1px solid {LINE}; }}
QMenu::item:selected {{ background: {ACCENT_SOFT}; }}
QMenu::item:checked {{ color: {ACCENT}; }}
QToolTip {{ background: {PANEL_2}; color: {TEXT}; border: 1px solid {LINE}; padding: 4px; }}
QProgressBar {{ background: {PANEL_2}; border: none; border-radius: 4px; height: 8px; text-align: center; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
QProgressBar#ExportBar {{ border-radius: 2px; max-height: 5px; }}
QProgressBar#ExportBar::chunk {{ border-radius: 2px; }}
QLabel#ExportLabel {{ color: {TEXT_DIM}; }}
QSplitter::handle {{ background: {LINE}; }}
QStatusBar {{ background: {PANEL}; color: {TEXT_DIM}; }}
"""


def load_fonts() -> str | None:
    """Register the bundled Inter font (SIL Open Font License). Returns the family name if loaded."""
    import os

    folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "fonts")
    family = None
    for name in ("Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf", "Inter-Bold.ttf"):
        fid = QtGui.QFontDatabase.addApplicationFont(os.path.join(folder, name))
        if fid >= 0 and not family:
            fams = QtGui.QFontDatabase.applicationFontFamilies(fid)
            family = fams[0] if fams else None
    return family


def tabular(font: QtGui.QFont) -> QtGui.QFont:
    """Tabular (fixed-width) figures so numbers don't jitter while a slider moves."""
    try:
        font.setFeature(QtGui.QFont.Tag("tnum"), 1)
    except Exception:
        pass
    return font


def apply(app: QtWidgets.QApplication) -> None:
    family = load_fonts()
    if family:
        QtGui.QFont.insertSubstitutions(family, FALLBACKS)
        f = QtGui.QFont(family, 9)
        f.setFamilies([family] + FALLBACKS)
        f.setHintingPreference(QtGui.QFont.PreferNoHinting)
        f.setStyleStrategy(QtGui.QFont.PreferAntialias)
        app.setFont(f)
    app.setStyle("Fusion")
    pal = QtGui.QPalette()
    pal.setColor(QtGui.QPalette.Window, QtGui.QColor(BG))
    pal.setColor(QtGui.QPalette.Base, QtGui.QColor(PANEL_2))
    pal.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(PANEL))
    pal.setColor(QtGui.QPalette.Text, QtGui.QColor(TEXT))
    pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor(TEXT))
    pal.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(TEXT))
    pal.setColor(QtGui.QPalette.Button, QtGui.QColor(PANEL_2))
    pal.setColor(QtGui.QPalette.Highlight, QtGui.QColor(ACCENT))
    pal.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("white"))
    pal.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor(PANEL_2))
    pal.setColor(QtGui.QPalette.ToolTipText, QtGui.QColor(TEXT))
    for role in (QtGui.QPalette.Text, QtGui.QPalette.WindowText, QtGui.QPalette.ButtonText):
        pal.setColor(QtGui.QPalette.Disabled, role, QtGui.QColor(TEXT_FAINT))
    app.setPalette(pal)
    app.setStyleSheet(QSS)


def draw_icon(size: int = 256) -> QtGui.QImage:
    """App icon: a film frame with sprocket holes and a safelight-red lens."""
    img = QtGui.QImage(size, size, QtGui.QImage.Format_ARGB32_Premultiplied)
    img.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(img)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    s = size / 256.0
    grad = QtGui.QLinearGradient(0, 0, 0, size)
    grad.setColorAt(0, QtGui.QColor("#2b2b2f"))
    grad.setColorAt(1, QtGui.QColor("#131314"))
    p.setBrush(grad)
    p.setPen(QtCore.Qt.NoPen)
    p.drawRoundedRect(QtCore.QRectF(8 * s, 8 * s, 240 * s, 240 * s), 52 * s, 52 * s)
    strip = QtCore.QRectF(28 * s, 58 * s, 200 * s, 140 * s)
    p.setBrush(QtGui.QColor("#0a0a0a"))
    p.drawRoundedRect(strip, 10 * s, 10 * s)
    p.setBrush(QtGui.QColor("#d9d6cf"))
    for i in range(7):
        x = (38 + i * 28) * s
        p.drawRoundedRect(QtCore.QRectF(x, 66 * s, 14 * s, 12 * s), 3 * s, 3 * s)
        p.drawRoundedRect(QtCore.QRectF(x, 178 * s, 14 * s, 12 * s), 3 * s, 3 * s)
    p.setBrush(QtGui.QColor("#3a1f1a"))
    p.drawRect(QtCore.QRectF(40 * s, 88 * s, 176 * s, 80 * s))
    rg = QtGui.QRadialGradient(QtCore.QPointF(128 * s, 128 * s), 46 * s)
    rg.setColorAt(0, QtGui.QColor("#ff8a68"))
    rg.setColorAt(0.55, QtGui.QColor(ACCENT))
    rg.setColorAt(1, QtGui.QColor("#7a2414"))
    p.setBrush(rg)
    p.drawEllipse(QtCore.QPointF(128 * s, 128 * s), 44 * s, 44 * s)
    p.setBrush(QtGui.QColor(20, 10, 8, 200))
    p.drawEllipse(QtCore.QPointF(128 * s, 128 * s), 16 * s, 16 * s)
    p.end()
    return img


def app_icon() -> QtGui.QIcon:
    icon = QtGui.QIcon()
    for sz in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(QtGui.QPixmap.fromImage(draw_icon(sz)))
    return icon
