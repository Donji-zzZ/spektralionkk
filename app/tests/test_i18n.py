"""Chinese interface: every visible text, tooltip, menu entry and list item is translated.

Run: .venv\\Scripts\\python.exe -I -X utf8 -W ignore app\\tests\\test_i18n.py
"""
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="sprk_i18n_")
os.environ["SPRK_LANG"] = "zh_CN"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(HERE, ".."))
from PySide6 import QtCore, QtGui, QtWidgets

from spektralionkk import i18n

OUT = os.path.join(HERE, "out")
SRC = os.path.join(OUT, "test_input.jpg")
fails = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


CJK = re.compile(r"[一-鿿]")
WORDS = re.compile(r"\b[a-z]{3,}\b")
OK_WORDS = {"mm", "px", "jpg", "xmp", "cube", "lrtemplate", "sprkpreset", "exr", "png", "tif", "tiff", "spektrafilm",
            "spektralionkk", "http", "https", "github", "com", "html", "srgb"}


def suspicious(t: str) -> bool:
    t = t.replace("&&", "&").strip()
    if not t or CJK.search(t):
        return False
    for k in (t, t.replace("&", "")):
        if k in i18n.ZH and i18n.ZH[k] != k:
            return True  # known string shown untranslated
    # any ordinary lowercase English word (film / paper / camera names are capitalised or codes)
    words = [w for w in re.findall(r"\b[a-z]{4,}\b", t) if w not in OK_WORDS]
    return len(words) >= 1


def texts_of(win):
    seen = []
    widgets = [win] + win.findChildren(QtWidgets.QWidget)
    actions = set()
    for w in widgets:
        if not w.isVisibleTo(win) and not isinstance(w, QtWidgets.QMenu):
            continue
        actions.update(w.actions())
        for t in (w.toolTip(),):
            seen.append(("tooltip", type(w).__name__, t))
        if isinstance(w, (QtWidgets.QLabel, QtWidgets.QAbstractButton)):
            seen.append(("text", type(w).__name__, w.text()))
        if isinstance(w, QtWidgets.QComboBox):
            seen.extend(("combo", "QComboBox", w.itemText(i)) for i in range(w.count()))
        if isinstance(w, QtWidgets.QLineEdit):
            seen.append(("placeholder", "QLineEdit", w.placeholderText()))
        if isinstance(w, QtWidgets.QListWidget):
            for i in range(w.count()):
                it = w.item(i)
                seen.append(("list", w.objectName(), it.text()))
                seen.append(("list-tip", w.objectName(), it.toolTip()))
    for a in actions:
        seen.append(("action", "QAction", a.text()))
        if a.menu():
            seen.append(("menu", "QMenu", a.menu().title()))
            for b in a.menu().actions():
                seen.append(("action", "QAction", b.text()))
    return seen


def main():
    app = QtWidgets.QApplication(sys.argv)
    from spektralionkk.ui import theme
    from spektralionkk.ui.main_window import MainWindow

    i18n.init()
    check(i18n.LANG == "zh_CN", "language from SPRK_LANG")
    theme.apply(app)
    win = MainWindow(initial_paths=[SRC] if os.path.exists(SRC) else None)
    win.show()
    for _ in range(40):
        app.processEvents()
        QtCore.QThread.msleep(50)
    for sec in win.right.sections.values():  # open every section so all rows are visible
        sec.set_collapsed(False)
    win.right.crop_sec.setVisible(True)
    app.processEvents()
    seen = texts_of(win)
    bad = sorted({(k, cls, t) for k, cls, t in seen if t and suspicious(t)}, key=lambda x: x[2])
    for k, cls, t in bad[:80]:
        print(f"   untranslated {k:11s} {cls:14s} {t[:110]!r}")
    check(not bad, f"no untranslated texts in the main window ({len(bad)} found, {len(seen)} checked)")
    zh = sum(1 for _, _, t in seen if t and CJK.search(t))
    check(zh > 150, f"{zh} texts shown in Chinese")
    # dialogs built on demand
    from spektralionkk.ui.export_dialog import ExportDialog
    from spektralionkk.ui.panels import GroupsDialog
    from spektralionkk.settings import SYNC_GROUPS

    for dlg in (ExportDialog(1, 2, 3, {}, win), GroupsDialog("Copy Settings", list(SYNC_GROUPS), [], "Copy", win)):
        seen = [(k, c, t) for k, c, t in texts_of(dlg)]
        bad = sorted({t for _, _, t in seen if t and suspicious(t)})
        for t in bad:
            print(f"   untranslated in {type(dlg).__name__}: {t[:110]!r}")
        check(not bad, f"{type(dlg).__name__} translated")
    # the filmstrip and Looks context menus are built when shown: build them and read their entries
    def entries(menu):
        out = []
        for act in menu.actions():
            out.append(act.text())
            if act.menu():
                out.extend(entries(act.menu()))
        return out

    menus = []
    if win.strip.list.count():
        win.strip.list.setCurrentRow(0)
        menus.append(entries(win.strip.build_menu(QtCore.QPoint(5, 5))))
    menus.append(entries(win.left.looks.build_menu(QtCore.QPoint(5, 5))))
    bad = sorted({t for m in menus for t in m if t and suspicious(t)})
    for t in bad:
        print(f"   untranslated menu entry: {t!r}")
    check(menus and not bad, f"context menus translated ({sum(map(len, menus))} entries)")
    win.grab().save(os.path.join(OUT, "i18n_zh.png"))
    for _ in range(2400):  # let the render thread finish compiling its kernels before the hard exit
        if win._engine_ready:
            break
        app.processEvents()
        QtCore.QThread.msleep(50)
    print("\n" + ("ALL PASSED" if not fails else f"{len(fails)} FAILED"), flush=True)
    os._exit(1 if fails else 0)  # render threads may still be busy: don't wait for them


if __name__ == "__main__":
    main()
