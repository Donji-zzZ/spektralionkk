"""Application entry point: splash screen first, heavy imports after."""

from __future__ import annotations

import sys


def _be_a_good_neighbour():
    """Rendering runs at below-normal priority (other programs stay smooth); the UI thread runs above
    the render threads so sliders and panning stay responsive while a render is in progress."""
    try:
        import ctypes

        k32 = ctypes.windll.kernel32
        BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
        THREAD_PRIORITY_HIGHEST = 2
        k32.SetPriorityClass(k32.GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS)
        k32.SetThreadPriority(k32.GetCurrentThread(), THREAD_PRIORITY_HIGHEST)
    except Exception:
        pass


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    _be_a_good_neighbour()
    from PySide6 import QtCore, QtGui, QtWidgets

    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_ShareOpenGLContexts, False)
    app = QtWidgets.QApplication(argv)
    from . import APP_NAME, i18n
    from .i18n import tr
    from .ui import theme

    i18n.init()  # the installer's (or View ▸ Language) choice, else the Windows display language

    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    theme.apply(app)
    app.setWindowIcon(theme.app_icon())

    pm = QtGui.QPixmap(420, 240)
    pm.fill(QtGui.QColor(theme.PANEL))
    p = QtGui.QPainter(pm)
    p.drawImage(QtCore.QRect(24, 52, 136, 136), theme.draw_icon(256))
    p.setPen(QtGui.QColor(theme.TEXT))
    f = QtGui.QFont("Segoe UI", 20, QtGui.QFont.DemiBold)
    p.setFont(f)
    p.drawText(QtCore.QRect(176, 80, 240, 40), QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, APP_NAME)
    p.setPen(QtGui.QColor(theme.TEXT_DIM))
    sub = QtGui.QFont("Segoe UI", 9)
    sub.setFamilies(["Segoe UI", "Microsoft YaHei UI"])
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

    paths = [a for a in argv[1:] if not a.startswith("--")]
    win = MainWindow(initial_paths=paths or None)
    win.show()
    splash.finish(win)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
