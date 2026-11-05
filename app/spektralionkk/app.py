"""Application entry point: splash screen first, heavy imports after."""

from __future__ import annotations

import sys

IS_MAC = sys.platform == "darwin"


def _be_a_good_neighbour():
    """Windows: rendering runs at below-normal priority (other programs stay smooth); the UI thread runs above
    the render threads so sliders and panning stay responsive while a render is in progress."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        k32 = ctypes.windll.kernel32
        BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
        THREAD_PRIORITY_HIGHEST = 2
        k32.SetPriorityClass(k32.GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS)
        k32.SetThreadPriority(k32.GetCurrentThread(), THREAD_PRIORITY_HIGHEST)
    except Exception:
        pass


def _opened_file(ev) -> str:
    """The path of a QFileOpenEvent (whatever class the binding hands over)."""
    from PySide6 import QtGui

    import os

    if not isinstance(ev, QtGui.QFileOpenEvent):
        import shiboken6

        ev = shiboken6.wrapInstance(shiboken6.getCppPointer(ev)[0], QtGui.QFileOpenEvent)
    path = ev.file() or ev.url().toLocalFile()
    return os.path.normpath(path) if path else ""


def make_application(argv):
    """The QApplication, which also takes photos opened from Finder: macOS sends them (Open With, double-click,
    dropped on the Dock icon) as QFileOpenEvent instead of command-line arguments."""
    from PySide6 import QtCore, QtWidgets

    class Application(QtWidgets.QApplication):
        def __init__(self, args):
            super().__init__(args)
            self.pending: list[str] = []  # opened before the window exists
            self.window = None
            self._flush_timer = QtCore.QTimer(self)
            self._flush_timer.setSingleShot(True)
            self._flush_timer.setInterval(150)  # several files arrive as several events: add them together
            self._flush_timer.timeout.connect(self.flush_opened)

        def event(self, ev):
            if ev.type() == QtCore.QEvent.FileOpen:
                try:
                    path = _opened_file(ev)
                except Exception:  # noqa: BLE001
                    path = ""
                if path and path not in self.pending:
                    self.pending.append(path)
                    self._flush_timer.start()
                return True
            return super().event(ev)

        def flush_opened(self):
            if self.window is None or not self.pending:
                return
            paths, self.pending = self.pending, []
            self.window.add_paths(paths)
            self.window.raise_()
            self.window.activateWindow()

    return Application(argv)


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    _be_a_good_neighbour()
    from PySide6 import QtCore, QtGui, QtWidgets

    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_ShareOpenGLContexts, False)
    app = make_application(argv)
    if IS_MAC:
        try:  # dark title bar, menus and dialogs to match the dark interface, whatever the system appearance
            app.styleHints().setColorScheme(QtCore.Qt.ColorScheme.Dark)
        except Exception:
            pass
    from . import APP_NAME, i18n
    from .i18n import tr
    from .ui import theme

    i18n.init()  # the installer's (or View ▸ Language) choice, else the system language

    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    theme.apply(app)
    app.setWindowIcon(theme.app_icon())

    families = ["Segoe UI", "Helvetica Neue", "Microsoft YaHei UI", "PingFang SC"]
    pm = QtGui.QPixmap(420, 240)
    pm.fill(QtGui.QColor(theme.PANEL))
    p = QtGui.QPainter(pm)
    p.drawImage(QtCore.QRect(24, 52, 136, 136), theme.draw_icon(256))
    p.setPen(QtGui.QColor(theme.TEXT))
    f = QtGui.QFont("Segoe UI", 20, QtGui.QFont.DemiBold)
    f.setFamilies(families)
    p.setFont(f)
    p.drawText(QtCore.QRect(176, 80, 240, 40), QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, APP_NAME)
    p.setPen(QtGui.QColor(theme.TEXT_DIM))
    sub = QtGui.QFont("Segoe UI", 12 if IS_MAC else 9)
    sub.setFamilies(families)
    p.setFont(sub)
    p.drawText(QtCore.QRect(176, 120, 240, 40), QtCore.Qt.AlignLeft | QtCore.Qt.TextWordWrap,
               tr("Spectral film & print simulation\npowered by spektrafilm"))
    p.end()
    splash = QtWidgets.QSplashScreen(pm)
    splash.show()
    splash.showMessage(tr("Loading film engine…"), QtCore.Qt.AlignBottom | QtCore.Qt.AlignHCenter,
                       QtGui.QColor(theme.TEXT_DIM))
    app.processEvents()

    from .ui.main_window import MainWindow

    # photos given on the command line (Windows "Open with", drag onto the .exe) or already sent by Finder
    paths = [a for a in argv[1:] if not a.startswith("-")] + app.pending
    app.pending = []
    win = MainWindow(initial_paths=paths or None)
    app.window = win
    win.show()
    splash.finish(win)
    QtCore.QTimer.singleShot(0, app.flush_opened)  # anything Finder sent while the window was being built
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
