# dmgbuild settings for the spektralionkk disk image (used by scripts/build_macos.sh from the repository root):
# the app on the left, a link to Applications on the right, an arrow and short instructions behind them.
# dmgbuild provides `defines` (the values build_macos.sh passes in).
import os.path

application = defines.get("app", "dist/spektralionkk.app")  # noqa: F821
appname = os.path.basename(application)

format = "UDZO"
files = [application]
symlinks = {"Applications": "/Applications"}
_icns = os.path.join(application, "Contents", "Resources", "spektralionkk.icns")
icon = _icns if os.path.exists(_icns) else None  # the mounted volume's icon
background = defines.get("background", "app/macos/dmg-background.png")  # noqa: F821  (+ its @2x for Retina)

show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
window_rect = ((200, 160), (640, 400))
default_view = "icon-view"
show_icon_preview = False
arrange_by = None
label_pos = "bottom"
text_size = 13
icon_size = 112
icon_locations = {appname: (170, 150), "Applications": (470, 150)}
