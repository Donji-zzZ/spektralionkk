"""Draw the background of the macOS disk-image window (1x and @2x for Retina).

    dmg-background.png         drag-to-Applications hint plus the first-open steps (app not notarised)
    dmg-background-signed.png  drag-to-Applications hint only (notarised app: it opens with a double-click)

An 18 % grey card between two film-strip edges: the icon labels Finder draws (black in light mode, white in
dark mode) stay readable on it either way. Run on Windows or macOS (it needs a font with Chinese characters):
    python app/macos/make_dmg_background.py
"""
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "..", "spektralionkk", "data", "fonts")
W, H = 640, 400  # Finder window content, in points
GREY, BAND, WHITE, SOFT = (110, 110, 110), (24, 24, 26), (255, 255, 255), (236, 236, 236)
APP_X, APPS_X, ICON_Y = 170, 470, 150  # icon centres (see dmg_settings.py)

LINES = [("Drag spektralionkk to Applications", "latin-bold", 15, WHITE),
         ("把 spektralionkk 拖到“应用程序”文件夹", "cjk", 14, WHITE)]
FIRST_OPEN = [("Won't open? System Settings › Privacy & Security › Open Anyway", "latin", 12, SOFT),
              ("打不开？系统设置 › 隐私与安全性 › 仍要打开", "cjk", 12, SOFT)]


def font(kind: str, px: int):
    if kind.startswith("latin"):
        return ImageFont.truetype(os.path.join(FONTS, "Inter-SemiBold.ttf" if kind == "latin-bold"
                                               else "Inter-Medium.ttf"), px)
    for path in (r"C:\Windows\Fonts\msyh.ttc", "/System/Library/Fonts/PingFang.ttc",
                 "/System/Library/Fonts/Hiragino Sans GB.ttc", "/System/Library/Fonts/STHeiti Medium.ttc"):
        if os.path.exists(path):
            return ImageFont.truetype(path, px)
    raise SystemExit("no font with Chinese characters found")


def draw(scale: int, lines) -> Image.Image:
    s = scale
    img = Image.new("RGB", (W * s, H * s), GREY)
    d = ImageDraw.Draw(img)
    band = 28 * s
    for y0 in (0, H * s - band):  # film edges with sprocket holes
        d.rectangle([0, y0, W * s, y0 + band], fill=BAND)
        for x in range(10 * s, W * s, 30 * s):
            d.rounded_rectangle([x, y0 + 9 * s, x + 14 * s, y0 + 19 * s], radius=3 * s, fill=GREY)
    # arrow from the app to Applications
    cx, cy = (APP_X + APPS_X) // 2 * s, ICON_Y * s
    shaft, head, half = 34 * s, 22 * s, 5 * s
    d.rectangle([cx - shaft, cy - half, cx + shaft - head // 2, cy + half], fill=SOFT)
    d.polygon([(cx + shaft - head, cy - 16 * s), (cx + shaft + 6 * s, cy), (cx + shaft - head, cy + 16 * s)],
              fill=SOFT)
    y = 262 * s
    for i, (text, kind, px, colour) in enumerate(lines):
        f = font(kind, px * s)
        if i == 2:
            y += 12 * s  # a gap before the first-open steps
        w = d.textlength(text, font=f)
        d.text(((W * s - w) / 2, y), text, font=f, fill=colour)
        y += round(px * 1.55) * s
    return img


if __name__ == "__main__":
    for name, lines in (("dmg-background", LINES + FIRST_OPEN), ("dmg-background-signed", LINES)):
        draw(1, lines).save(os.path.join(HERE, f"{name}.png"), optimize=True)
        draw(2, lines).save(os.path.join(HERE, f"{name}@2x.png"), optimize=True)
    print("written to", HERE)
