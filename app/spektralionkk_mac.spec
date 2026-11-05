# PyInstaller spec for the macOS app bundle (spektralionkk.app, Apple silicon, macOS 14+).
# Build on a Mac from the repository root (or just run scripts/build_macos.sh, which also makes the DMG):
#   .venv/bin/python -m PyInstaller app/spektralionkk_mac.spec --noconfirm --distpath dist --workpath build
# MACOS_SIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)" signs every file with that certificate and
# the hardened runtime (needed for notarisation); without it the bundle is signed ad hoc.
import os
import re

from PyInstaller.utils.hooks import collect_all, collect_submodules

HERE = os.path.abspath(SPECPATH)
ROOT = os.path.dirname(HERE)
with open(os.path.join(HERE, "spektralionkk", "__init__.py"), encoding="utf-8") as fh:
    VERSION = re.search(r'APP_VERSION = "(.+?)"', fh.read()).group(1)
IDENTITY = os.environ.get("MACOS_SIGN_IDENTITY") or None
ENTITLEMENTS = os.path.join(HERE, "macos", "entitlements.plist")

datas, binaries, hiddenimports = [], [], []
for pkg in ["spektrafilm", "colour", "skimage", "numba", "llvmlite", "pyfftw", "OpenImageIO", "rawpy",
            "exiv2", "lensfunpy", "opt_einsum", "imageio", "tifffile"]:
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception as exc:
        print(f"skip {pkg}: {exc}")
hiddenimports += collect_submodules("spektralionkk")

import spektrafilm  # noqa: E402  (its licence file goes into the bundle with the others)

notices = [os.path.join(ROOT, "LICENSE"), os.path.join(ROOT, "THIRD_PARTY_NOTICES.md"),
           os.path.join(HERE, "README-spektralionkk.txt"),
           os.path.join(os.path.dirname(spektrafilm.__file__), "data", "license", "SPEKTRAFILM_LICENSE.txt")]

a = Analysis(
    [os.path.join(HERE, "launcher.py")],
    pathex=[HERE],
    binaries=binaries,
    datas=datas + [(os.path.join(HERE, "assets", "spektralionkk.png"), "assets"),
                   (os.path.join(HERE, "spektralionkk", "data"), os.path.join("spektralionkk", "data"))]
          + [(p, ".") for p in notices if os.path.exists(p)],
    hiddenimports=hiddenimports,
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
# Qt frameworks the app never loads, pulled in only by plugins it does not use (virtual keyboard, PDF images).
# Frameworks go as a whole - binary and Info.plist - so the bundle stays valid for code signing.
_DROP = ("QtQuick", "QtQml", "QtPdf", "QtVirtualKeyboard", "QtShaderTools", "virtualkeyboard", "libqpdf")


def _keep(entry):
    path = entry[0].replace("\\", "/")
    return not any(k.lower() in path.lower() for k in _DROP)


a.binaries = [b for b in a.binaries if _keep(b)]
a.datas = [d for d in a.datas if _keep(d)
           and (not any(p in d[0].replace("\\", "/") for p in ("numba/tests/", "scipy/", "/tests/", "skimage/data/"))
                or d[0].replace("\\", "/").startswith("scipy/") and "/tests/" not in d[0].replace("\\", "/"))]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="spektralionkk", console=False, upx=False,
          target_arch="arm64", codesign_identity=IDENTITY, entitlements_file=ENTITLEMENTS)
coll = COLLECT(exe, a.binaries, a.datas, name="spektralionkk", upx=False)

# the formats engine.SUPPORTED_EXTENSIONS opens
_IMAGES = ["public.camera-raw-image", "com.adobe.raw-image", "com.sony.arw-raw-image", "com.canon.cr2-raw-image",
           "com.canon.cr3-raw-image", "com.nikon.raw-image", "com.nikon.nrw-raw-image", "com.fuji.raw-image",
           "com.panasonic.rw2-raw-image", "com.olympus.or-raw-image", "com.pentax.raw-image", "com.leica.rwl-raw-image",
           "public.jpeg", "public.png", "public.tiff", "public.heic", "public.heif", "org.webmproject.webp",
           "com.microsoft.bmp", "com.ilm.openexr-image"]
app = BUNDLE(
    coll,
    name="spektralionkk.app",
    icon=os.path.join(HERE, "assets", "spektralionkk.icns"),
    bundle_identifier="io.github.spektralionkk",
    version=VERSION,
    codesign_identity=IDENTITY,
    entitlements_file=ENTITLEMENTS,
    info_plist={
        "CFBundleName": "spektralionkk",
        "CFBundleDisplayName": "spektralionkk",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSMinimumSystemVersion": "14.0",
        "LSArchitecturePriority": ["arm64"],
        "LSApplicationCategoryType": "public.app-category.photography",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
        "NSAppSleepDisabled": True,  # no App Nap: an export keeps full speed while the window is in the background
        "NSHumanReadableCopyright": "Free software under the GNU GPL v3. Film engine: spektrafilm by Andrea Volpato.",
        # "Open With" and dropping photos or folders on the Dock icon; never the default app for a type
        "CFBundleDocumentTypes": [
            {"CFBundleTypeName": "Photo", "CFBundleTypeRole": "Viewer", "LSHandlerRank": "Alternate",
             "LSItemContentTypes": _IMAGES},
            {"CFBundleTypeName": "Folder", "CFBundleTypeRole": "Viewer", "LSHandlerRank": "Alternate",
             "LSItemContentTypes": ["public.folder"]},
        ],
        # shown when macOS asks for access to photos kept in these places
        "NSDesktopFolderUsageDescription": "spektralionkk opens the photos you add from your Desktop.",
        "NSDocumentsFolderUsageDescription": "spektralionkk opens the photos you add from your Documents folder.",
        "NSDownloadsFolderUsageDescription": "spektralionkk opens the photos you add from your Downloads folder.",
        "NSRemovableVolumesUsageDescription": "spektralionkk opens photos from memory cards and external drives.",
        "NSNetworkVolumesUsageDescription": "spektralionkk opens photos kept on network drives.",
    },
)
