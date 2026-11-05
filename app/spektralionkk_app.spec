# PyInstaller spec for the spektralionkk app (one-folder build).
# Build from the repository root (or just run build.ps1):
#   .venv\Scripts\python.exe -m PyInstaller app\spektralionkk_app.spec --noconfirm --distpath dist --workpath build
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

HERE = os.path.abspath(SPECPATH)
datas, binaries, hiddenimports = [], [], []
for pkg in ["spektrafilm", "colour", "skimage", "numba", "llvmlite", "pyfftw", "OpenImageIO", "rawpy",
            "exiv2", "lensfunpy", "opt_einsum", "imageio", "tifffile"]:
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception as exc:
        print(f"skip {pkg}: {exc}")
hiddenimports += collect_submodules("spektralionkk")

a = Analysis(
    [os.path.join(HERE, "launcher.py")],
    pathex=[HERE],
    binaries=binaries,
    datas=datas + [(os.path.join(HERE, "assets", "spektralionkk.png"), "assets"),
                   (os.path.join(HERE, "spektralionkk", "data"), os.path.join("spektralionkk", "data"))],
    hiddenimports=hiddenimports,
    # The old napari GUI and its stack are not used by this app.
    excludes=["napari", "napari_builtins", "napari_console", "napari_svg", "vispy", "magicgui", "superqt",
              "app_model", "npe2", "spektrafilm_gui", "spektrafilm_lut_creator", "PyQt5", "PyQt6", "PySide2",
              "tkinter", "IPython", "jupyter_client", "ipykernel", "qtconsole", "pytest", "numba.cuda",
              "numba.tests", "scipy.tests", "skimage.data", "matplotlib", "pandas", "sphinx", "babel",
              "docutils", "pygments", "jinja2", "dask", "pooch", "networkx",
              "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQuick", "PySide6.Qt3DCore",
              "PySide6.QtMultimedia", "PySide6.QtPdf", "PySide6.QtCharts", "PySide6.QtDataVisualization",
              "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtQml", "PySide6.QtNetwork"],
    # numba cache=True needs real source files (spektrafilm kernels and the app's real-time preview kernel)
    module_collection_mode={"spektrafilm": "py", "spektralionkk": "py"},
    noarchive=False,
)
# Drop big Qt / test payloads the app never loads (it draws with QPainter, no OpenGL).
_DROP = ("opengl32sw.dll", "Qt6Quick", "Qt6Qml", "Qt6Pdf", "Qt6OpenGL", "Qt6VirtualKeyboard", "Qt6Network",
         "QtQuick", "QtQml", "QtPdf", "QtOpenGL", "Qt6ShaderTools", "Qt6Svg")
a.binaries = [b for b in a.binaries if not any(k.lower() in b[0].lower() for k in _DROP)]
a.datas = [d for d in a.datas
           if not any(p in d[0].replace("\\", "/") for p in ("numba/tests/", "scipy/", "/tests/", "skimage/data/"))
           or d[0].replace("\\", "/").startswith("scipy/") and "/tests/" not in d[0].replace("\\", "/")]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="spektralionkk", console=False, upx=False,
          icon=os.path.join(HERE, "assets", "spektralionkk.ico"))
coll = COLLECT(exe, a.binaries, a.datas, name="spektralionkk", upx=False)
