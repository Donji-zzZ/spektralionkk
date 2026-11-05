"""macOS code paths, checked on any system: data folder, Finder, language file, font fallbacks, the macOS build
files, Finder open events, the Mac menus, and rendering threads on numba's workqueue layer (the one macOS uses,
where two threads must never run parallel kernels at the same time).

Run: .venv\\Scripts\\python.exe -I -X utf8 -W ignore app\\tests\\test_platform.py
"""
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(APP_DIR)
TMP = tempfile.mkdtemp(prefix="sprk_platform_")
os.environ["LOCALAPPDATA"] = os.path.join(TMP, "local")
os.environ["SPRK_LANG"] = "en"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, APP_DIR)
fails = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


def start_workqueue_selftest():
    """The packaged app's self-test (renders on two threads at once) with numba forced onto workqueue."""
    env = dict(os.environ, NUMBA_THREADING_LAYER="workqueue", LOCALAPPDATA=os.path.join(TMP, "wq"))
    env.pop("SPRK_LANG", None)
    return subprocess.Popen([sys.executable, "-X", "utf8", "-W", "ignore", os.path.join(APP_DIR, "launcher.py"),
                             "--selftest-quiet"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace")


def test_platform_util():
    from spektralionkk import platform_util as pu

    saved = pu.IS_MAC, pu.IS_WINDOWS, os.environ.pop("LOCALAPPDATA")
    try:
        pu.IS_MAC, pu.IS_WINDOWS = True, False
        check(pu.data_root() == os.path.join(os.path.expanduser("~/Library/Application Support"), "spektralionkk"),
              "macOS data folder: ~/Library/Application Support/spektralionkk")
        check(pu.file_manager() == "Finder", "menus say Finder")
        check(pu.reveal_command("/Users/me/a.jpg")[:2] == ["open", "-R"], "Show in Finder uses open -R")
    finally:
        pu.IS_MAC, pu.IS_WINDOWS = saved[0], saved[1]
        os.environ["LOCALAPPDATA"] = saved[2]
    check(pu.data_root() == os.path.join(os.environ["LOCALAPPDATA"], "spektralionkk"), "LOCALAPPDATA still wins")


def test_language_file():
    import ctypes

    from spektralionkk import i18n

    saved_winreg = sys.modules.get("winreg")
    saved_windll = getattr(ctypes, "windll", None)
    sys.modules["winreg"] = None  # import winreg fails, as on a Mac
    ctypes.windll = None
    try:
        check(i18n._stored_language() is None, "no language file at first")
        i18n.save_language("zh_CN")
        check(os.path.exists(i18n._language_file()), "View ▸ Language writes the language file")
        check(i18n._stored_language() == "zh_CN", "language file read back")
        os.environ.pop("SPRK_LANG")
        check(i18n.init() == "zh_CN", "the saved language is used at start-up")
        i18n.save_language("en")
        check(i18n.init() == "en", "switched back to English")
        check(i18n._system_language() in ("en", "zh_CN"), "system language from the Qt locale")
    finally:
        os.environ["SPRK_LANG"] = "en"
        if saved_winreg is not None:
            sys.modules["winreg"] = saved_winreg
        else:
            sys.modules.pop("winreg", None)
        if saved_windll is not None:
            ctypes.windll = saved_windll
        i18n.init("en")


def test_fonts():
    import numpy as np

    from spektralionkk import borders, engine
    from spektralionkk.settings import DevelopSettings

    def clear():
        for f in (borders._font_file, borders._font, borders._mono_font, borders._edge_font):
            f.cache_clear()

    saved = borders._font_dirs
    try:
        borders._font_dirs = lambda: [os.path.join(TMP, "no-such-fonts")]
        clear()
        p = borders._font_file("arialbd.ttf", "segoeuib.ttf")
        check(bool(p) and p.endswith("Inter-Bold.ttf"), "no system font: the bundled Inter")
        check(borders._font_file("arial.ttf", bold=False).endswith("Inter-Regular.ttf"), "regular weight too")
        fonts = os.path.join(TMP, "Fonts")
        os.makedirs(fonts)
        for name in ("Arial Bold.ttf", "DIN Condensed Bold.ttf", "Courier New Bold.ttf"):
            shutil.copy(os.path.join(APP_DIR, "spektralionkk", "data", "fonts", "Inter-Bold.ttf"),
                        os.path.join(fonts, name))
        borders._font_dirs = lambda: [fonts]
        clear()
        check(borders._font_file("bahnschrift.ttf") == os.path.join(fonts, "DIN Condensed Bold.ttf"),
              "Bahnschrift -> DIN Condensed Bold (macOS)")
        check(borders._font_file("arialbd.ttf") == os.path.join(fonts, "Arial Bold.ttf"), "Arial Bold (macOS)")
        check(borders._font_file("consolab.ttf") == os.path.join(fonts, "Courier New Bold.ttf"),
              "Consolas -> Courier New Bold (macOS)")
        img = np.full((400, 600, 3), 0.45, np.float32)
        s = DevelopSettings(film="kodak_tri_x_400", border="135", date_stamp=True, date_text="'26 11 05")
        out = engine.add_border(img, s, show_frame=True)
        rebate = out[: max(4, (out.shape[0] - 400) // 2)]
        check(out.shape[0] > 400 and out.shape[1] > 600 and float(rebate.std()) > 0.02,
              f"film strip with edge print drawn with the macOS fonts ({out.shape[1]}x{out.shape[0]})")
    finally:
        borders._font_dirs = saved
        clear()


def test_build_files():
    ent = plistlib.load(open(os.path.join(APP_DIR, "macos", "entitlements.plist"), "rb"))
    check(ent.get("com.apple.security.cs.allow-jit") is True
          and ent.get("com.apple.security.cs.allow-unsigned-executable-memory") is True,
          "entitlements allow the numba JIT under the hardened runtime")
    # run the macOS spec with PyInstaller's build functions stubbed out, and look at what it would build
    seen = {}

    def stub(name):
        def f(*a, **kw):
            seen[name] = (a, kw)
            return types.SimpleNamespace(binaries=[], datas=[], pure=[], scripts=[], name=name)
        return f

    hooks = types.ModuleType("PyInstaller.utils.hooks")
    hooks.collect_all = lambda pkg: ([], [], [])
    hooks.collect_submodules = lambda pkg: []
    saved = {k: sys.modules.get(k) for k in ("PyInstaller", "PyInstaller.utils", "PyInstaller.utils.hooks")}
    sys.modules.update({"PyInstaller": types.ModuleType("PyInstaller"),
                        "PyInstaller.utils": types.ModuleType("PyInstaller.utils"),
                        "PyInstaller.utils.hooks": hooks})
    try:
        spec = os.path.join(APP_DIR, "spektralionkk_mac.spec")
        ns = {"SPECPATH": APP_DIR, "__file__": spec}
        ns.update({k: stub(k) for k in ("Analysis", "PYZ", "EXE", "COLLECT", "BUNDLE")})
        exec(compile(open(spec, encoding="utf-8").read(), spec, "exec"), ns)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    _, bundle = seen["BUNDLE"]
    info = bundle["info_plist"]
    from spektralionkk import APP_VERSION

    check(bundle["name"] == "spektralionkk.app" and os.path.exists(bundle["icon"]), "app bundle with its .icns icon")
    check(info["LSMinimumSystemVersion"] == "14.0" and info["CFBundleShortVersionString"] == APP_VERSION,
          f"Info.plist: macOS 14+, version {APP_VERSION}")
    types_ = [t for d in info["CFBundleDocumentTypes"] for t in d["LSItemContentTypes"]]
    check("public.camera-raw-image" in types_ and "public.folder" in types_ and
          all(d["LSHandlerRank"] == "Alternate" for d in info["CFBundleDocumentTypes"]),
          "Open With for photos, RAW files and folders (never the default app)")
    check(seen["EXE"][1].get("target_arch") == "arm64" and os.path.exists(seen["EXE"][1]["entitlements_file"]),
          "arm64 executable signed with the entitlements")
    datas = [os.path.basename(d[0]) for d in seen["Analysis"][1]["datas"]]
    check({"LICENSE", "THIRD_PARTY_NOTICES.md", "SPEKTRAFILM_LICENSE.txt"} <= set(datas), "licences inside the app")
    plistlib.dumps(info)  # every value must be a valid property-list type
    # disk image layout
    ns = {"defines": {"app": "dist/spektralionkk.app", "background": "app/macos/dmg-background.png"}}
    settings = os.path.join(APP_DIR, "macos", "dmg_settings.py")
    exec(compile(open(settings, encoding="utf-8").read(), settings, "exec"), ns)
    check(ns["symlinks"] == {"Applications": "/Applications"} and
          set(ns["icon_locations"]) == {"spektralionkk.app", "Applications"}, "disk image: app + Applications link")
    from PIL import Image

    for name in ("dmg-background", "dmg-background-signed"):
        a = Image.open(os.path.join(APP_DIR, "macos", f"{name}.png"))
        b = Image.open(os.path.join(APP_DIR, "macos", f"{name}@2x.png"))
        check(a.size == (640, 400) and b.size == (1280, 800), f"{name}: 1x and Retina @2x")
    icns = Image.open(os.path.join(APP_DIR, "assets", "spektralionkk.icns"))
    check((512, 512, 2) in icns.info.get("sizes", []), "Mac icon up to 1024 px (512 pt @2x)")
    for script in ("build_macos.sh", "run_tests.sh"):
        raw = open(os.path.join(ROOT, "scripts", script), "rb").read()
        check(raw.startswith(b"#!/usr/bin/env bash\n") and b"\r\n" not in raw,
              f"{script}: bash script with Unix line endings")


def test_file_open(app):
    from PySide6 import QtCore, QtGui

    a, b, c = (os.path.join(TMP, n) for n in ("a.jpg", "b.ARW", "c.jpg"))

    class Window:
        def __init__(self):
            self.got = []
            self.raised = 0

        def add_paths(self, paths):
            self.got.append(list(paths))

        def raise_(self):
            self.raised += 1

        def activateWindow(self):
            pass

    for p in (a, b):
        QtCore.QCoreApplication.sendEvent(app, QtGui.QFileOpenEvent(p))
    check(app.pending == [a, b], "Finder files opened at launch wait for the window")
    w = Window()
    app.window = w
    app.flush_opened()
    check(w.got == [[a, b]] and app.pending == [], "...and are added together once it exists")
    QtCore.QCoreApplication.sendEvent(app, QtGui.QFileOpenEvent(QtCore.QUrl.fromLocalFile(c)))
    for _ in range(30):
        app.processEvents()
        QtCore.QThread.msleep(20)
    check(w.got[-1:] == [[c]] and w.raised == 2, "a photo dropped on the Dock icon later is added and shown")
    app.window = None


def test_mac_menus(app):
    from PySide6 import QtCore, QtGui, QtWidgets

    from spektralionkk import platform_util
    from spektralionkk.ui import main_window as mw
    from spektralionkk.ui import theme

    mw.IS_MAC = platform_util.IS_MAC = True
    theme.apply(app)
    win = mw.MainWindow()
    win.show()
    for _ in range(20):
        app.processEvents()
        QtCore.QThread.msleep(25)

    def walk(menu):
        for act in menu.actions():
            if act.menu():
                yield from walk(act.menu())
            elif not act.isSeparator():
                yield act

    acts = {a.text(): a for m in win.menuBar().actions() if m.menu() for a in walk(m.menu())}
    check(acts["Exit"].menuRole() == QtGui.QAction.QuitRole, "Exit becomes Quit in the application menu")
    check(acts["About spektralionkk"].menuRole() == QtGui.QAction.AboutRole, "About goes to the application menu")
    others = [t for t, a in acts.items() if t not in ("Exit", "About spektralionkk")
              and a.menuRole() != QtGui.QAction.NoRole]
    check(not others, f"every other entry stays in its menu ({len(acts)} entries)")
    check(acts["Redo"].shortcut().toString() == "Ctrl+Shift+Z", "Redo is ⌘⇧Z")
    check(acts["Exit"].shortcut() == QtGui.QKeySequence(QtGui.QKeySequence.Quit), "Quit uses the standard ⌘Q")
    shown = {}
    orig = QtWidgets.QMessageBox.information
    QtWidgets.QMessageBox.information = staticmethod(lambda parent, title, text, *a, **kw: shown.setdefault("t", text))
    try:
        win.show_shortcuts()
    finally:
        QtWidgets.QMessageBox.information = orig
    text = shown.get("t", "")
    check("⌘O" in text and "⌘⇧Z" in text and "Ctrl" not in text, "Keyboard Shortcuts lists ⌘ keys")
    check(win.top.export_status.show_btn.toolTip().endswith("in Finder"), "export status offers Show in Finder")
    tip = win.top.open_btn.toolTip()
    check("⌘O" in tip and "Ctrl" not in tip, f"tooltips name the ⌘ key ({tip!r})")
    return win


def main():
    proc = start_workqueue_selftest()
    test_platform_util()
    test_language_file()
    test_fonts()
    test_build_files()

    from PySide6 import QtCore

    from spektralionkk.app import make_application

    app = make_application([sys.argv[0]])
    test_file_open(app)
    win = test_mac_menus(app)

    out, _ = proc.communicate(timeout=1800)
    report_path = os.path.join(TMP, "wq", "spektralionkk", "selftest.txt")
    report = open(report_path, encoding="utf-8").read() if os.path.exists(report_path) else out
    ok = proc.returncode == 0 and "RESULT: PASS" in report
    if not ok:
        print(report[-3000:])
    check(ok, "self-test passes on numba's workqueue layer (live preview and refined render at once)")
    check("threading: workqueue (renders take turns)" in report, "the guard is on for workqueue")
    for _ in range(2400):  # let the render thread finish compiling before the hard exit
        if win._engine_ready:
            break
        app.processEvents()
        QtCore.QThread.msleep(50)
    print("\n" + ("ALL PASSED" if not fails else f"{len(fails)} FAILED"), flush=True)
    os._exit(1 if fails else 0)


if __name__ == "__main__":
    main()
