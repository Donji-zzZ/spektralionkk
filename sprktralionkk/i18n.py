"""Interface language: English or Simplified Chinese.

The language is chosen in the installer (it writes HKCU\\Software\\sprktralionkk\\Language) or in the app
(View ▸ Language, takes effect after a restart). Without either, the app follows the Windows display language.
SPRK_LANG=en|zh_CN overrides everything (tests).

Strings are written in English in the code; tr() looks them up in the table below. translate_tree() translates
the static texts, tooltips and menus of a finished widget tree; dynamic texts call tr() / trf() directly.
"""

from __future__ import annotations

import os
import re

LANG = "en"
REG_KEY = r"Software\sprktralionkk"
LANGS = {"en": "English", "zh_CN": "简体中文"}


def _registry_language() -> str | None:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY) as k:
            v, _ = winreg.QueryValueEx(k, "Language")
        v = str(v).lower()
        if v.startswith(("zh", "chinese")):
            return "zh_CN"
        if v.startswith(("en", "english")):
            return "en"
    except Exception:
        pass
    return None


def _system_language() -> str:
    try:
        import ctypes

        lid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return "zh_CN" if (lid & 0x3FF) == 0x04 else "en"
    except Exception:
        return "en"


def init(lang: str | None = None) -> str:
    global LANG
    lang = lang or os.environ.get("SPRK_LANG") or _registry_language() or _system_language()
    LANG = "zh_CN" if lang.lower().startswith("zh") else "en"
    return LANG


def save_language(lang: str) -> None:
    """Remember the choice (same registry value the installer writes); used from the next start."""
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_KEY) as k:
        winreg.SetValueEx(k, "Language", 0, winreg.REG_SZ, "chinesesimplified" if lang == "zh_CN" else "english")


def tr(text: str) -> str:
    if LANG == "en" or not text:
        return text
    hit = ZH.get(text)
    if hit is not None:
        return hit
    # keep leading / trailing decoration (indent, ellipsis-free variants) when only the core is known
    m = re.match(r"^(\s*)(.*?)(\s*)$", text, re.S)
    if m and m.group(2) in ZH:
        return m.group(1) + ZH[m.group(2)] + m.group(3)
    return text


def trf(template: str, **kw) -> str:
    """Translate a template, then fill it: trf('Added {n} photo(s)', n=3)."""
    return tr(template).format(**kw)


def translate_tree(root) -> None:
    """Translate the static texts of a widget and everything inside it (labels, buttons, tooltips, combo
    items, placeholders, group titles, menus and their actions)."""
    if LANG == "en" or root is None:
        return
    from PySide6 import QtGui, QtWidgets

    widgets = [root] + root.findChildren(QtWidgets.QWidget)
    actions = set(root.findChildren(QtGui.QAction))
    for w in widgets:
        actions.update(w.actions())
        tip = w.toolTip()
        if tip:
            w.setToolTip(tr(tip))
        if isinstance(w, QtWidgets.QLabel):
            t = w.text()
            if t:
                w.setText(tr(t))
        elif isinstance(w, QtWidgets.QAbstractButton):
            t = w.text()
            if t:
                w.setText(tr(t))
        elif isinstance(w, QtWidgets.QComboBox):
            for i in range(w.count()):
                t = w.itemText(i)
                if t:
                    w.setItemText(i, tr(t))
        elif isinstance(w, QtWidgets.QLineEdit):
            ph = w.placeholderText()
            if ph:
                w.setPlaceholderText(tr(ph))
        elif isinstance(w, QtWidgets.QGroupBox):
            w.setTitle(tr(w.title()))
        elif isinstance(w, QtWidgets.QMenu):
            w.setTitle(tr(w.title()))
        if w.isWindow() and w.windowTitle():
            w.setWindowTitle(tr(w.windowTitle()))
    for a in actions:
        t = a.text()
        if t:
            a.setText(tr(t))
        tip = a.toolTip()
        if tip and tip != t:
            a.setToolTip(tr(tip))
        m = a.menu()
        if m is not None:
            m.setTitle(tr(m.title()))


ZH: dict[str, str] = {}


def _add(table: dict):
    ZH.update(table)


# ---------------------------------------------------------------- menus, top bar, toolbar
_add({
    "&File": "文件(&F)", "&Edit": "编辑(&E)", "&Photo": "照片(&P)", "&View": "视图(&V)", "&Help": "帮助(&H)",
    "Open Photos…": "打开照片…", "Open Folder…": "打开文件夹…", "Export…": "导出…",
    "Import Presets && LUTs…": "导入预设与 LUT…", "Export Current Settings as Preset…": "将当前设置导出为预设…",
    "Open Presets && LUTs Folder": "打开预设与 LUT 文件夹", "Remove Selected from Library": "从图库中移除所选照片",
    "Exit": "退出", "Undo": "撤销", "Redo": "重做", "Copy Settings…": "拷贝设置…", "Paste Settings": "粘贴设置",
    "Sync Settings…": "同步设置…", "Select All Photos": "全选照片", "Reset Photo": "重置照片",
    "Save Current as Default for New Photos": "将当前设置存为新照片的默认值",
    "Restore Factory Defaults for New Photos": "新照片恢复出厂默认值",
    "Crop & Straighten": "裁剪与拉直", "Crop && Straighten": "裁剪与拉直", "White Balance Picker": "白平衡吸管",
    "Save Look…": "存储风格…", "Rotate Left": "向左旋转", "Rotate Right": "向右旋转", "Set Rating": "设置星级",
    "Flag": "旗标", "Pick": "选取", "Reject": "排除", "Unflag": "取消旗标", "No stars": "无星级",
    "Before (Original)": "修改前（原图）", "Before | After Split": "前后对比分屏", "Show Clipping": "显示溢出警告",
    "Fit": "适合", "Fill": "填满", "Zoom In": "放大", "Zoom Out": "缩小", "Previous Photo": "上一张照片",
    "Next Photo": "下一张照片", "Left Panel": "左侧面板", "Develop Panel": "修改面板",
    "Show Film Frame && Date Stamp in Preview": "在预览中显示胶片边框与日期",
    "Render Grain in Fitted Preview (slower)": "适合视图下也渲染颗粒（较慢）",
    "Keyboard Shortcuts": "键盘快捷键", "About {APP_NAME}": "关于 {APP_NAME}", "Language": "语言",
    "Open…": "打开…", "Folder…": "文件夹…", "Open photos (Ctrl+O)": "打开照片（Ctrl+O）",
    "Open a folder (Ctrl+Shift+O)": "打开文件夹（Ctrl+Shift+O）", "Export (Ctrl+E)": "导出（Ctrl+E）",
    "Show / hide the left panel (F7)": "显示 / 隐藏左侧面板（F7）",
    "Show / hide the Develop panel (F8)": "显示 / 隐藏修改面板（F8）",
    "◐ Before": "◐ 修改前", "Show the original photo (\\)": "显示原图（\\）", "◫ Before | After": "◫ 前 | 后",
    "Split view with a draggable divider (Y)": "可拖动分隔线的前后对比（Y）", "▲ Clipping": "▲ 溢出",
    "Show clipped highlights (red) and shadows (blue) (J)": "显示溢出的高光（红）与暗部（蓝）（J）",
    "Stop exporting": "停止导出", "Show": "显示", "Show the exported file in Explorer": "在资源管理器中显示导出的文件",
    "Details": "详情", "Exporting…": "正在导出…", "Exporting {name}": "正在导出 {name}",
    "  ·  {i} of {n}": "  ·  第 {i} 张，共 {n} 张", "⚠ Exported {written}, {failed} failed": "⚠ 已导出 {written} 张，{failed} 张失败",
    "Export stopped · {written} saved": "导出已停止 · 已保存 {written} 张", "✓ Exported 1 photo": "✓ 已导出 1 张照片",
    "✓ Exported {n} photos": "✓ 已导出 {n} 张照片", "Stopping…": "正在停止…",
    "An export is already running (top left). Stop it with ✕ first.": "已有导出正在进行（左上角），请先点 ✕ 停止。",
    "Exported {n} file(s)": "已导出 {n} 个文件", "Exported {n} file(s) to {folder}": "已导出 {n} 个文件到 {folder}",
    "These photos could not be exported:\n\n": "以下照片无法导出：\n\n",
    "Restart now": "立即重启", "Later": "稍后",
    "The language changes the next time sprktralionkk starts.": "界面语言将在下次启动 sprktralionkk 时切换。",
})

# ---------------------------------------------------------------- develop panel
_add({
    "Profile": "胶片与相纸", "Film": "胶片", "Paper": "相纸", "Contrast grade": "反差等级",
    "Multigrade  (−1 = 00)": "多级反差（−1 = 00）", "Multigrade filtration: 00 softest … 5 hardest": "多级反差滤镜：00 最柔 … 5 最硬",
    "The film the photo is exposed and developed on: its colour, contrast, grain and halation.":
        "照片在哪种胶片上曝光、冲洗：决定色彩、反差、颗粒与光晕。",
    "Paper = the photographic paper the negative is printed on in the darkroom.\n"
    "A negative is an inverted orange image; the paper turns it into the final print, and each paper\n"
    "has its own contrast, colour and saturation (like choosing a paper at a lab).\n"
    "Cinema print films (2383 / 2393) give the look of a projected film print.\n"
    "'Direct scan' skips the print: the film itself is scanned — that is how slides are viewed.":
        "相纸 = 暗房里用来印放负片的相纸。\n负片是反相的橙色影像，相纸把它变成最终的照片；每种相纸都有自己的\n"
        "反差、色彩和饱和度（就像在冲印店选择相纸）。\n电影拷贝片（2383 / 2393）呈现电影放映拷贝的观感。\n"
        "“直接扫描”不经过印放，直接扫描胶片本身——反转片就是这样观看的。",
    "Portrait paper: soft contrast, gentle colour, natural skin.": "人像相纸：反差柔和，色彩温和，肤色自然。",
    "Portrait / wedding paper: a little more colour and contrast than Portra Endura.":
        "人像 / 婚礼相纸：色彩和反差比 Portra Endura 略强。",
    "High saturation and contrast for punchy, vivid prints.": "高饱和、高反差，印出鲜艳有力的照片。",
    "Kodak's all-round professional paper: rich colour, standard contrast.": "柯达的全能专业相纸：色彩饱满，反差标准。",
    "Consumer lab paper: bright, saturated minilab prints.": "民用冲印相纸：明亮、饱和的冲印店照片。",
    "Fujifilm lab paper: crisp, clean colour with Fuji's greens.": "富士冲印相纸：色彩清爽干净，富士特有的绿色。",
    "Cinema print film: dense blacks, strong contrast — the look of a projected film.":
        "电影拷贝片：黑色浓郁、反差强——电影放映的观感。",
    "Premium cinema print film: richer colour and contrast than 2383.": "高级电影拷贝片：色彩和反差比 2383 更丰富。",
    "Black & white paper; set its contrast with the grade (00–5).": "黑白相纸；用反差等级（00–5）设置反差。",
    "No print: the film itself is scanned (how slides are viewed). Negatives always need a paper.":
        "不印放：直接扫描胶片本身（反转片的观看方式）。负片必须印在相纸上。",
    " A negative still needs a paper: printed on {paper}.": " 负片仍需印在相纸上：使用 {paper}。",
    "No paper: the Digital profile is not printed.": "无相纸：数码配置不经过印放。",
    "No film": "无胶片", "Color negative": "彩色负片", "Slide (positive)": "反转片（正片）", "Cine negative": "电影负片",
    "Black & white": "黑白", "Color paper": "彩色相纸", "Cine print film": "电影拷贝片", "Black & white paper": "黑白相纸",
    "Slides": "反转片", "Digital (no film simulation)": "数码（无胶片模拟）", "Direct scan (no print)": "直接扫描（不印放）",
    "Film Edge": "胶片边框", "Style": "样式", "Film format": "胶片画幅", "Perforations": "齿孔", "Edge print": "片边字码",
    "Frame no.": "片号", "Date back": "日期后背", "Date": "日期", "Date text": "日期文字", "Shooting data": "拍摄参数",
    "Film Edge on / off: print the film strip around the picture — rebate, perforations, the stock's edge print "
    "and frame numbers": "胶片边框开 / 关：在画面周围印出胶片条——片基边、齿孔、胶片自带的片边字码和片号",
    "Film strip: the negative or slide as a scan shows it — 135 with perforations, 120 with\nits rebate — in the "
    "Format below. Or a filed carrier, a slide mount or a white border.":
        "胶片条：扫描时看到的负片或反转片——135 带齿孔，120 带片基边——按下方的画幅显示。\n"
        "也可选锉边底片夹、幻灯片框或白边。",
    "Film size. With Film Edge on, the picture is framed in this format's gate (e.g. 6×6 is\nsquare) — move it "
    "inside the gate with the Crop tool. It also sets the grain scale.":
        "胶片尺寸。开启胶片边框时，画面按此画幅的片门取景（例如 6×6 是正方形）——\n可用裁剪工具在片门内移动画面。它也决定颗粒的尺度。",
    "The stock's own lettering, frame numbers, DX code": "胶片自带的字样、片号和 DX 码",
    "Orange LED date: in the picture on 135, in the margin on 120": "橙色 LED 日期：135 印在画面内，120 印在片边",
    "from the photo, e.g. '24 11 04": "取自照片，例如 '24 11 04",
    "Leave empty to use the date the photo was taken.": "留空则使用照片的拍摄日期。",
    "Shutter, aperture and focal length in the 120 margin": "在 120 片边印出快门、光圈和焦距",
    "Hide it in the preview only: View ▸ Show Film Frame (Shift+F). Exports include it unless you untick "
    "“Include the film frame”.": "只在预览中隐藏：视图 ▸ 显示胶片边框（Shift+F）。导出时会包含边框，除非取消勾选“包含胶片边框”。",
    "Off": "关闭", "Film strip": "胶片条", "Filed carrier (black)": "锉边底片夹（黑边）", "Slide mount": "幻灯片框",
    "White print border": "白色相纸边", "Wide white matte": "宽白卡纸边", "White (backlit scan)": "白色（透光扫描）",
    "Black": "黑色", "Half frame (18×24)": "半格（18×24）", "4×5 in": "4×5 英寸",
    "Basic": "基本", "WB": "白平衡", "Temp": "色温", "Tint": "色调", "Tone": "影调", "Exposure": "曝光",
    "Auto exposure": "自动曝光", "Metering pattern of the virtual camera": "虚拟相机的测光模式",
    "White balance picker (W): click something that should be neutral grey": "白平衡吸管（W）：点击应为中性灰的地方",
    "Film exposure in stops": "胶片曝光（档）", "Contrast": "对比度", "Highlights": "高光", "Shadows": "阴影",
    "Whites": "白色色阶", "Blacks": "黑色色阶", "Presence": "偏好", "Clarity": "清晰度", "Vibrance": "自然饱和度",
    "Saturation": "饱和度", "Tone Curve": "色调曲线", "Color Mixer": "颜色混合器", "Hue": "色相", "Luminance": "明亮度",
    "Color Grading": "颜色分级", "Midtones": "中间调", "Overall": "整体", "Balance": "平衡", "Blending": "混合",
    "Enlarger": "放大机", "Brightness": "亮度", "print time, stops": "印放时间（档）", "Yellow": "黄", "Magenta": "品红",
    "CC filter": "CC 滤镜", "Pre-flash": "预曝光", "×100": "×100",
    "Uniform pre-exposure of the paper: lifts and softens the print's shadows": "相纸均匀预曝光：提亮并柔化照片暗部",
    "Paper contrast": "相纸反差", "Developer": "显影液", "exhaustion": "疲劳度", "Lab auto-print": "冲印机自动补偿",
    "Printer cancels film exposure changes": "印放机自动抵消胶片曝光的变化",
    "Film & Grain": "胶片与颗粒", "Larger formats enlarge less: finer grain, tighter halation": "画幅越大放大越少：颗粒更细，光晕更紧",
    "Grain": "颗粒", "Simulated at 100% zoom and in exports": "在 100% 缩放和导出时模拟", "Grain size": "颗粒大小",
    "µm² particle": "µm² 颗粒", "Halation": "光晕", "Red glow around very bright lights; best seen at 100%": "强光周围的红色光晕；100% 查看最明显",
    "Light reflected from the film base back into the emulsion. Its physical radius is a fraction of a millimetre, "
    "so it shows as a fine red fringe at fitted size.": "光线从片基反射回乳剂层形成的光晕。其物理半径不到一毫米，因此在适合视图下只是细细的红边。",
    "Scatter": "散射", "Highlight boost": "高光增强",
    "Restores the energy of clipped highlights (lamps, sun, reflections) so they bloom and halate like real light "
    "sources. A digital photo clips them at white.": "恢复被截断高光（灯、太阳、反光）的能量，让它们像真实光源一样泛光、产生光晕。数码照片会把它们截断为白色。",
    "DIR couplers": "DIR 成色剂", "Inter-layer effects: saturation, edge contrast": "层间效应：饱和度、边缘反差",
    "Couplers": "成色剂", "Negative gamma": "负片反差系数",
    "Effects": "效果", "Vignette": "暗角", "Amount": "数量", "Midpoint": "中点", "Print surface": "相纸表面",
    "Surface glare": "表面眩光", "Glare": "眩光", "Lens filter": "镜头滤镜", "Diffusion filter": "柔焦滤镜", "Type": "类型",
    "Strength": "强度", "Black mist": "黑柔", "Pro mist": "白柔", "Glimmer glass": "微光镜", "Cine bloom": "电影柔光",
    "Creative LUT": "创意 LUT", ".cube LUTs for standard (sRGB / Rec.709) images": "适用于标准（sRGB / Rec.709）图像的 .cube LUT",
    "Import…": "导入…", "Import a .cube LUT": "导入 .cube LUT", "None": "无",
    "Detail": "细节", "Sharpening": "锐化", "White point correction": "白点校正", "Black point correction": "黑点校正",
    "Lens": "镜头", "Lens correction": "镜头校正", "Lensfun profile from EXIF (RAW files)": "根据 EXIF 使用 Lensfun 配置（RAW 文件）",
    "Sync…": "同步…", "Reset": "重置",
    "Copy chosen settings from this photo to the selected photos (Ctrl+Shift+S)": "把此照片选定的设置拷贝到所选照片（Ctrl+Shift+S）",
    "Reset this photo to the default settings (Ctrl+R)": "将此照片恢复为默认设置（Ctrl+R）",
    "Aspect": "比例", "Angle": "角度", "Cancel": "取消", "Done": "完成",
    "Drag the corners or edges, drag inside to move. Double-click or Enter to apply, Esc to cancel.":
        "拖动角或边调整，在框内拖动可移动。双击或按 Enter 应用，Esc 取消。",
    "Rotate left": "向左旋转", "Rotate right": "向右旋转", "Flip horizontal": "水平翻转", "Flip vertical": "垂直翻转",
    "Reset crop and angle": "重置裁剪与角度", "Original": "原始", "Free": "自由",
    "⌗ Crop": "⌗ 裁剪", "Crop & straighten (R)": "裁剪与拉直（R）", "◎ WB": "◎ 白平衡",
    "White balance picker (W) — click something neutral": "白平衡吸管（W）——点击中性色的地方", "◫ Split": "◫ 对比",
    "Before / After split view (Y)": "前后对比视图（Y）", "◐ Original": "◐ 原图", "Reset {title}": "重置{title}",
    "Double-click to reset": "双击重置", "Look: {name}": "风格：{name}",
    "Reset this channel's curve": "重置此通道的曲线",
    "Click to add a point · drag to move · double-click to remove": "单击添加点 · 拖动移动 · 双击删除",
    "Drag left/right to adjust {zone}": "左右拖动以调整{zone}", "Click to show clipping": "点击显示溢出",
})

# ---------------------------------------------------------------- left panel, looks, filmstrip
_add({
    "Navigator": "导航器", "Looks": "风格", "History": "历史记录", "Copy…": "拷贝…", "Paste": "粘贴",
    "FIT": "适合", "FILL": "填满", "Save the current settings as a Look": "将当前设置存为风格",
    "Copy settings of this photo (Ctrl+Shift+C)": "拷贝此照片的设置（Ctrl+Shift+C）",
    "Paste copied settings to this and the selected photos (Ctrl+Shift+V)": "将拷贝的设置粘贴到此照片和所选照片（Ctrl+Shift+V）",
    "Check all": "全选", "Check none": "全不选",
    "Camera-inspired": "相机风格", "Film classics": "经典胶片", "Cinema": "电影", "My Looks": "我的风格",
    "Your saved look": "你存储的风格", "Imported {src}": "导入自 {src}",
    "   Save your own, or right-click ▸ Import": "   存储你自己的风格，或右键 ▸ 导入",
    " — right-click to export or delete": " —— 右键可导出或删除",
    "Save current settings as a Look…": "将当前设置存为风格…",
    "Import presets (.xmp, .lrtemplate, .cube)…": "导入预设（.xmp、.lrtemplate、.cube）…",
    "Export current settings as a preset file…": "将当前设置导出为预设文件…",
    "Export “{name}” as a preset file…": "将“{name}”导出为预设文件…", "Delete “{name}”": "删除“{name}”",
    "Positive Film (GR-inspired)": "正片（GR 风格）", "Negative Film (GR-inspired)": "负片（GR 风格）",
    "Classic (Leica-inspired)": "经典（徕卡风格）", "Contemporary (Leica-inspired)": "当代（徕卡风格）",
    "Eternal (Leica-inspired)": "永恒（徕卡风格）", "Monochrome (Leica-inspired)": "单色（徕卡风格）",
    "Chrome Classic (Fujifilm-inspired)": "经典正片（富士风格）", "Neg Classic (Fujifilm-inspired)": "经典负片（富士风格）",
    "Eterna (Fujifilm-inspired)": "Eterna 电影（富士风格）", "Acros (Fujifilm-inspired)": "Acros（富士风格）",
    "Portra 400 Portrait": "Portra 400 人像", "Gold 200 Summer": "Gold 200 夏日", "Ektar 100 Landscape": "Ektar 100 风光",
    "Superia-style X-Tra 400": "Superia 风格 X-Tra 400", "Pro 400H Airy": "Pro 400H 清透",
    "CineStill 800T Night": "CineStill 800T 夜景", "Vision3 500T Tungsten": "Vision3 500T 钨丝灯",
    "Vision3 50D Daylight": "Vision3 50D 日光", "Bleach Bypass": "漂白旁路", "HP5 Plus Pushed": "HP5 Plus 增感",
    "T-Max 100 Fine": "T-Max 100 细腻", "Soft Grade 1": "柔和 1 号反差",
    "Punchy slide-film colour, deep contrast, warm highlights over cool shadows.": "反转片般浓烈的色彩，深沉的反差，暖高光配冷阴影。",
    "Soft, faded lab-print look: lifted blacks, cyan shadows, muted greens.": "柔和褪色的冲印观感：黑位提升，青色阴影，绿色低调。",
    "Gentle contrast, warm and slightly muted, timeless.": "反差温和，偏暖略淡，经久耐看。",
    "Clean, crisp and saturated with strong local contrast.": "干净利落、饱和，局部反差强。",
    "Cinematic and restrained: teal shadows, amber highlights, low saturation.": "电影感且克制：青色阴影，琥珀色高光，低饱和。",
    "Rich black-and-white with crisp midtone contrast (Tri-X on Multigrade grade 3).": "层次丰富的黑白，中间调反差清晰（Tri-X 印在多级反差 3 号相纸上）。",
    "Muted slide colour with hard shadows — documentary feel.": "低调的反转片色彩，硬朗的阴影——纪实感。",
    "Hard, low-saturation negative look with cyan-leaning shadows and warm skin.": "硬朗、低饱和的负片观感，阴影偏青，肤色偏暖。",
    "Flat cinema negative look with lots of shadow detail.": "平淡的电影负片观感，暗部细节丰富。",
    "Fine-grained, smooth black-and-white (Neopan Acros 100 II, grade 2½).": "颗粒细腻、过渡顺滑的黑白（Neopan Acros 100 II，2½ 号反差）。",
    "The wedding and portrait staple: warm skin, gentle contrast.": "婚礼与人像的经典之选：肤色温暖，反差柔和。",
    "Consumer-film warmth and saturation, a little nostalgic.": "民用胶卷的温暖与饱和，带点怀旧。",
    "Ultra-saturated, fine grain — skies and foliage.": "极高饱和，颗粒细腻——适合天空与植物。",
    "Fujifilm consumer negative: cool greens, punchy.": "富士民用负片：偏冷的绿色，色彩有力。",
    "The legendary slide film: deep reds, dense shadows.": "传奇反转片：深红色，浓重的阴影。",
    "Vivid slide film for landscapes.": "适合风光的鲜艳反转片。", "Accurate, neutral slide film.": "准确、中性的反转片。",
    "Pastel, airy greens and skin — overexposed-film look.": "粉彩般清透的绿色与肤色——过曝胶片的观感。",
    "Tungsten film without anti-halation, printed on photo paper: red glow around lights, teal shadows.":
        "去除防光晕层的灯光型胶片，印在相纸上：灯光周围有红色光晕，阴影偏青。",
    "Motion-picture negative printed on Vision 2383.": "电影负片印在 Vision 2383 拷贝片上。",
    "Fine-grain daylight cine stock on 2383.": "细颗粒日光型电影胶片，印在 2383 上。",
    "Desaturated, high-contrast, silver-retained look.": "低饱和、高反差的留银观感。",
    "Classic reportage B&W, grade 2.": "经典纪实黑白，2 号反差。",
    "Gritty, contrasty — HP5 printed hard (grade 4).": "粗粝、强反差——HP5 用硬反差（4 号）印放。",
    "Smooth tonality and very fine grain.": "影调顺滑，颗粒极细。", "Low-contrast, delicate print on grade 1.": "低反差、细腻的 1 号反差照片。",
    "All photos": "全部照片", "Picks only": "仅显示选取", "Hide rejects": "隐藏排除的照片", "Rated ★ or more": "★ 及以上",
    "Rated ★★★ or more": "★★★ 及以上", "Rated ★★★★★": "★★★★★", " ({n} photos)": "（{n} 张）",
    "⚑  Pick": "⚑  选取", "✕  Reject": "✕  排除", "Show in Explorer": "在资源管理器中显示", "Rejected": "已排除",
    "Rating": "星级", "Apply Look": "应用风格", "Copy File Path": "复制文件路径",
    "Copy Settings from This Photo": "拷贝此照片的设置", "Sync Settings from the Open Photo…": "从当前打开的照片同步设置…",
    "Open in Default App": "用默认程序打开", "Remove from Library": "从图库中移除", "Remove {n} from Library": "从图库中移除 {n} 张",
    "Show": "显示", "Reset Settings": "重置设置", "Export": "导出", "Rotate": "旋转",
})

# ---------------------------------------------------------------- messages, dialogs
_add({
    "Open photos": "打开照片", "Photos ({exts});;All files (*)": "照片 ({exts});;所有文件 (*)",
    "Open a folder of photos": "打开照片文件夹", "Edit": "编辑", "Multiple settings": "多项设置",
    "Developing…": "正在冲洗…", "Save Look": "存储风格", "Name for this look:": "风格名称：", " (mine)": "（我的）",
    "Saved look “{name}”": "已存储风格“{name}”", "Imported {n} preset(s) into My Looks.": "已将 {n} 个预设导入“我的风格”。",
    "Nothing was imported.": "没有导入任何内容。", " Click one in the Looks list to apply it.": " 在风格列表中点击即可应用。",
    "Import presets": "导入预设", "Export preset": "导出预设", "{app} preset (*{ext})": "{app} 预设 (*{ext})",
    "Saved preset “{name}” — share it, or import it with File ▸ Import": "已存储预设“{name}”——可分享，或用 文件 ▸ 导入 导入",
    "Copy Settings": "拷贝设置", "Copy": "拷贝", "Paste settings": "粘贴设置", "Pasted to {n} photo(s)": "已粘贴到 {n} 张照片",
    "Sync Settings to {n} photo(s)": "将设置同步到 {n} 张照片", "Synchronize": "同步", "Sync settings": "同步设置",
    "Synced {g} group(s) to {n} photo(s)": "已将 {g} 组设置同步到 {n} 张照片",
    "Saved as the default for new photos": "已存为新照片的默认值", "New photos will use factory defaults": "新照片将使用出厂默认值",
    "Keyboard shortcuts": "键盘快捷键", "Direct scan": "直接扫描",
    "Frame hidden in the preview — exports still follow the Export dialog": "预览中已隐藏边框——导出仍按导出对话框的设置",
    "No supported photos found there.": "那里没有找到支持的照片。", "Added {n} photo(s)": "已添加 {n} 张照片",
    "Already in the library": "已在图库中", "Direct scan is for slide films — a negative needs a paper": "直接扫描只适用于反转片——负片需要相纸",
    "Slides can't be printed on negative paper — showing the direct scan": "反转片不能印在负片相纸上——改为显示直接扫描",
    "Digital (no film)": "数码（无胶片）", "embedded JPEG (RAW codec not supported)": "内嵌 JPEG（不支持该 RAW 编码）",
    "  ·  grain shown at 100% and in exports": "  ·  颗粒在 100% 缩放和导出时显示", "Could not render": "无法渲染",
    "Click on something that should be neutral grey (Esc to cancel)": "点击应为中性灰的地方（Esc 取消）",
    "Import LUT": "导入 LUT", "Cube LUTs (*.cube);;All files (*)": "Cube LUT (*.cube);;所有文件 (*)",
    "Imported LUT “{name}”": "已导入 LUT“{name}”", " (imported)": "（已导入）",
    "\n\nSettings with no equivalent here were skipped (the rest of each preset is applied):\n":
        "\n\n以下设置在本软件中没有对应项，已跳过（预设的其余部分照常应用）：\n",
    "\n\nCould not read:\n": "\n\n无法读取：\n", "{label} — {n} photos": "{label} —— {n} 张照片",
    "Copied {n} group(s)": "已拷贝 {n} 组设置", "Copy settings first (Copy…)": "请先拷贝设置（拷贝…）",
    "Ctrl/Shift-click other photos in the filmstrip first": "请先在胶片栏中按住 Ctrl / Shift 点选其他照片",
    "Copy the checked settings from the current photo to the selected photos.": "把当前照片中勾选的设置拷贝到所选照片。",
    "Open some photos first": "请先打开一些照片", "Full-resolution detail rendered in {secs}s": "全分辨率细节渲染用时 {secs} 秒",
    "Rendered in {secs}s": "渲染用时 {secs} 秒", "Delete Look": "删除风格", "Delete “{name}”?": "删除“{name}”？",
    "White balance picker: {T} K, tint {tint}": "白平衡吸管：{T} K，色调 {tint}", "Crop": "裁剪", "Rating cleared": "已清除星级",
    "Opened": "已打开", "Slide film: scanned directly (no print)": "反转片：直接扫描（不印放）",
    "B&W film: printing on Ilford Multigrade IV RC": "黑白胶片：印在 Ilford Multigrade IV RC 上", "direct scan": "直接扫描",
    "LUT: {name}": "LUT：{name}", "Rotate {d}": "旋转{d}", "left": "向左", "right": "向右", "Rated {n}★": "已评 {n}★",
    "Printing on {paper}": "印在 {paper} 上", "Flagged as pick": "已标为选取", "Flagged as rejected": "已标为排除",
    "Flag removed": "已取消旗标",
    "Center weighted": "中央重点测光", "Matrix": "矩阵测光", "Multi zone": "多区测光", "Partial": "局部测光",
    "Highlight weighted": "高光优先测光", "Median": "中值测光", "Average": "平均测光",
    "Copied the settings of {name} (everything except crop) — right-click ▸ Paste": "已拷贝 {name} 的设置（裁剪除外）——右键 ▸ 粘贴",
    "Reset all edits of {n} photos?": "重置 {n} 张照片的全部修改？", "Copied": "已拷贝",
    "White balance: {T} K, tint {tint}": "白平衡：{T} K，色调 {tint}",
    "Open photos or a folder to start\n\nCtrl+O  ·  Ctrl+Shift+O  ·  or drop files here\n\nRAW (NEF, CR2/CR3, ARW, RAF, "
    "DNG, …) · JPEG · TIFF · PNG · EXR": "打开照片或文件夹开始\n\nCtrl+O  ·  Ctrl+Shift+O  ·  或把文件拖到这里\n\n"
                                         "RAW（NEF、CR2/CR3、ARW、RAF、DNG…）· JPEG · TIFF · PNG · EXR",
    "Fit · {pct}%": "适合 · {pct}%", "BEFORE": "修改前", "AFTER": "修改后",
    "Spectral film & print simulation\npowered by spektrafilm": "光谱胶片与印放模拟\n基于 spektrafilm",
    "Loading film engine…": "正在加载胶片引擎…", "Preparing film engine…": "正在准备胶片引擎…", "Refining…": "正在精细渲染…",
    "Rendering full-resolution detail…": "正在渲染全分辨率细节…", "Not enough memory for this operation.": "内存不足，无法完成此操作。",
    "Original view: {exc}": "原图视图：{exc}", "White balance picker: {exc}": "白平衡吸管：{exc}",
    "LibRaw can't decode this RAW's compression yet (for example Nikon High Efficiency or JPEG XL DNG), so you are "
    "editing the camera's embedded full-size JPEG instead.":
        "LibRaw 暂时无法解码这种 RAW 压缩（例如尼康高效率 RAW 或 JPEG XL DNG），因此你正在编辑相机内嵌的全尺寸 JPEG。",
    "Presets and LUTs (*.xmp *.lrtemplate *.cube *.sprkpreset);;Lightroom / Camera Raw presets (*.xmp *.lrtemplate);;"
    "LUT (*.cube);;sprktralionkk preset (*.sprkpreset);;All files (*)":
        "预设与 LUT (*.xmp *.lrtemplate *.cube *.sprkpreset);;Lightroom / Camera Raw 预设 (*.xmp *.lrtemplate);;"
        "LUT (*.cube);;sprktralionkk 预设 (*.sprkpreset);;所有文件 (*)",
    "Lightroom preset (.xmp)": "Lightroom 预设（.xmp）", "Lightroom preset (.lrtemplate)": "Lightroom 预设（.lrtemplate）",
    "sprktralionkk preset": "sprktralionkk 预设", "LUT (.cube)": "LUT（.cube）",
    "No Lightroom / Camera Raw settings found in this .xmp": "这个 .xmp 中没有 Lightroom / Camera Raw 设置",
    "No 'settings' table found in this .lrtemplate": "这个 .lrtemplate 中没有 settings 表",
    "Not a sprktralionkk preset": "不是 sprktralionkk 预设",
    "Adobe creative profile (embedded colour table)": "Adobe 创意配置文件（内嵌颜色表）",
})

# ---------------------------------------------------------------- export dialog
_add({
    "Current photo": "当前照片", "Selected photos ({n})": "所选照片（{n}）", "All photos in library ({n})": "图库中的全部照片（{n}）",
    "Format": "格式", "JPEG quality": "JPEG 质量", "Colour space": "色彩空间", "Size": "尺寸",
    "Full resolution": "全分辨率", "Long edge 6000 px": "长边 6000 像素", "Long edge 4096 px": "长边 4096 像素",
    "Long edge 3000 px": "长边 3000 像素", "Long edge 2048 px": "长边 2048 像素", "Long edge 1080 px": "长边 1080 像素",
    "Same folder as each photo": "与各照片相同的文件夹", "Browse…": "浏览…", "Folder": "文件夹",
    "File name suffix": "文件名后缀", "Include the film frame and date stamp": "包含胶片边框与日期", "Frame": "边框",
    "Uses each photo's Film Edge settings (border, edge print, date stamp).\nUntick to export just the picture.":
        "使用每张照片的胶片边框设置（边框、片边字码、日期）。\n取消勾选则只导出画面。",
    "Full-quality renders run on the CPU: roughly 20–60 s for a 24–45 MP RAW. Progress shows next to Export… at the "
    "top left, and you can keep editing meanwhile.":
        "全质量渲染在 CPU 上进行：24–45 MP 的 RAW 大约需要 20–60 秒。进度显示在左上角“导出…”旁边，期间可以继续修图。",
    "Export folder": "导出文件夹", "{name}: not enough memory — try a smaller export size": "{name}：内存不足——请尝试较小的导出尺寸",
})

# ---------------------------------------------------------------- settings labels (history), WB, sync groups
_add({
    "Look & profile": "风格与胶片", "White balance": "白平衡", "Tone & presence": "影调与偏好", "Color grading": "颜色分级",
    "Tone curve": "色调曲线", "Color mixer (HSL)": "颜色混合器（HSL）", "Film & grain": "胶片与颗粒",
    "Enlarger & print": "放大机与印放", "Film edge & border": "胶片边框", "Crop & rotate": "裁剪与旋转",
    "Grade": "反差等级", "Look": "风格", "Temperature": "色温", "Metering": "测光", "Shadows hue": "阴影色相",
    "Shadows color": "阴影色彩", "Midtones hue": "中间调色相", "Midtones color": "中间调色彩", "Highlights hue": "高光色相",
    "Highlights color": "高光色彩", "Grading balance": "分级平衡", "Grading blending": "分级混合", "Vignette midpoint": "暗角中点",
    "Halation amount": "光晕数量", "Negative contrast": "负片反差", "Diffusion type": "柔焦类型", "Diffusion strength": "柔焦强度",
    "Print brightness": "印放亮度", "White point": "白点", "Black point": "黑点", "Frame number": "片号",
    "Date stamp": "日期", "Red curve": "红色曲线", "Green curve": "绿色曲线", "Blue curve": "蓝色曲线", "LUT amount": "LUT 数量",
    "Flip horizontal": "水平翻转", "Flip vertical": "垂直翻转",
    "As Shot": "原照设置", "Auto": "自动", "Daylight": "日光", "Cloudy": "阴天", "Shade": "阴影处", "Tungsten": "白炽灯",
    "Fluorescent": "荧光灯", "Flash": "闪光灯", "Custom": "自定",
    "Red": "红色", "Orange": "橙色", "Green": "绿色", "Aqua": "浅绿色", "Blue": "蓝色", "Purple": "紫色",
    "hue": "色相", "saturation": "饱和度", "luminance": "明亮度", "on": "开", "off": "关",
})
for _band, _zh in (("Red", "红色"), ("Orange", "橙色"), ("Yellow", "黄色"), ("Green", "绿色"), ("Aqua", "浅绿色"),
                   ("Blue", "蓝色"), ("Purple", "紫色"), ("Magenta", "洋红")):
    for _k, _kz in (("hue", "色相"), ("saturation", "饱和度"), ("luminance", "明亮度")):
        ZH[f"{_band} {_k}"] = f"{_zh}{_kz}"

# ---------------------------------------------------------------- keyboard shortcuts help
_add({
    "Ctrl+O / Ctrl+Shift+O\tOpen photos / folder": "Ctrl+O / Ctrl+Shift+O\t打开照片 / 文件夹",
    "Ctrl+E\t\tExport": "Ctrl+E\t\t导出", "← / →\t\tPrevious / next photo": "← / →\t\t上一张 / 下一张",
    "R\t\tCrop & straighten (Enter = apply, Esc = cancel)": "R\t\t裁剪与拉直（Enter 应用，Esc 取消）",
    "W\t\tWhite balance picker": "W\t\t白平衡吸管", "\\\t\tBefore (original)": "\\\t\t修改前（原图）",
    "Y\t\tBefore | After split": "Y\t\t前后对比分屏", "J\t\tShow clipping": "J\t\t显示溢出警告",
    "F / Z\t\tFit / 100%   (double-click the image too)": "F / Z\t\t适合 / 100%（也可双击图片）",
    "Mouse wheel\tZoom   ·   drag to pan   ·   click the Navigator to jump": "鼠标滚轮\t缩放 · 拖动平移 · 点击导航器跳转",
    "Ctrl+Z / Ctrl+Y\tUndo / redo   (or click a History step)": "Ctrl+Z / Ctrl+Y\t撤销 / 重做（或点击历史记录中的一步）",
    "Ctrl+Shift+C / V\tCopy… / paste settings": "Ctrl+Shift+C / V\t拷贝… / 粘贴设置",
    "Ctrl+Shift+S\tSync settings to selected photos": "Ctrl+Shift+S\t把设置同步到所选照片",
    "Ctrl+R\t\tReset photo": "Ctrl+R\t\t重置照片",
    "0 – 5\t\tStar rating   ·   P / X / U  pick / reject / unflag": "0 – 5\t\t星级 · P / X / U 选取 / 排除 / 取消旗标",
    "Shift+F\t\tShow / hide the film frame in the preview": "Shift+F\t\t在预览中显示 / 隐藏胶片边框",
    "Ctrl+Shift+I\tImport presets & LUTs (.xmp, .lrtemplate, .cube)": "Ctrl+Shift+I\t导入预设与 LUT（.xmp、.lrtemplate、.cube）",
    "F7 / F8\t\tLeft / Develop panel": "F7 / F8\t\t左侧 / 修改面板",
    "Drag on the histogram to change Blacks / Shadows / Exposure / Highlights / Whites":
        "在直方图上拖动可调整 黑色色阶 / 阴影 / 曝光 / 高光 / 白色色阶",
    "Right-click filmstrip photos for ratings, looks, copy / paste, rotate, export…": "右键点击胶片栏中的照片：星级、风格、拷贝 / 粘贴、旋转、导出…",
    "Double-click a slider label to reset it": "双击滑块名称可重置",
})
