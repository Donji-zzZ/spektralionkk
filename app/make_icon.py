"""Render the app icon: app/assets/spektralionkk.ico (Windows, multi-size), .png and .icns (macOS).

The macOS icon follows Apple's icon grid: the rounded square is 824 px on a 1024 px canvas, with a soft
shadow under it, so it sits in the Dock at the same size as other apps.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageFilter
from PySide6 import QtGui

from spektralionkk.ui.theme import draw_icon


def to_pil(img: QtGui.QImage) -> Image.Image:
    img = img.convertToFormat(QtGui.QImage.Format_RGBA8888)
    return Image.frombuffer("RGBA", (img.width(), img.height()), bytes(img.constBits()), "raw", "RGBA", 0, 1).copy()


def mac_icon() -> Image.Image:
    size = round(824 * 256 / 240)  # draw_icon's rounded square spans 240 of its 256 units
    body = to_pil(draw_icon(size))
    offset = round(100 - 8 * size / 256)
    canvas = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    alpha = Image.new("L", (1024, 1024), 0)
    alpha.paste(body.getchannel("A"), (offset, offset + 12))
    shadow.putalpha(alpha.filter(ImageFilter.GaussianBlur(14)).point(lambda a: a * 0.45))
    canvas.alpha_composite(shadow)
    canvas.alpha_composite(body, (offset, offset))
    return canvas


if __name__ == "__main__":
    app = QtGui.QGuiApplication([])
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
    os.makedirs(out_dir, exist_ok=True)
    pil = to_pil(draw_icon(256))
    pil.save(os.path.join(out_dir, "spektralionkk.ico"),
             sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    pil.save(os.path.join(out_dir, "spektralionkk.png"))
    mac_icon().save(os.path.join(out_dir, "spektralionkk.icns"))
    print("icons written to", out_dir)
