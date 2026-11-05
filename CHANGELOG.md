# Changelog

## 1.4.0

- **macOS version** for Macs with Apple silicon (macOS 14 or later): a disk image with drag-to-Applications,
  a Mac icon, the app menu (About, ⌘Q), ⌘ shortcuts, Show in Finder, Open With and dropping photos on the
  Dock icon, the system language on first start. Rendering threads take turns on numba's workqueue layer
  (the one macOS uses), which would otherwise stop the app when the live preview and a refined render ran at
  once. The macOS build runs on GitHub (`.github/workflows/build.yml`); signing and notarisation are used
  when an Apple Developer ID is configured.
- **Camera-inspired looks name themselves on the Film Edge** instead of the stock they are built on: the
  Leica-inspired ones print LEICA CLASSIC, LEICA CONTEMPORARY, LEICA ETERNAL or LEICA MONOCHROME (LEICA in
  red), the Fujifilm-inspired ones CHROME CLASSIC, NEG CLASSIC or ETERNA 250D in Fujifilm-style lettering, the
  GR-inspired ones POSITIVE FILM / NEGATIVE FILM (they used to read KODAK PORTRA 400, KODAK EKTAR 100,
  KODAK E100, EASTMAN 5207…). Choosing another film puts that film's name back. Long names no longer overlap
  on 120.
- **Faster zoom:** zooming in shows a sharp full-resolution view at once (from the real-time tables); grain,
  halation and clarity are developed for the visible area a moment later and replace it. Below 100 % the
  detail is developed at the screen's resolution instead of the photo's (a 25 % view of a 45 MP photo:
  about 3 s instead of 38 s), and the full-resolution photo is decoded in the background once the preview
  is ready. Finishing (tone, colour) is also quicker.
- **Leica-inspired looks retuned** for the dense "German" rendering: deeper, richer colour (darker blues,
  greens and reds, no yellow cast), deep blacks, stronger local contrast and darker corners.
- **Film Edge, redone:** a switch in the Film Edge header (right under Film / Paper) turns it on. Film strips
  are drawn to scale: 135 with white (backlit scan) or black perforations, each stock's own edge print,
  frame numbers and DX code; 120 with its rebate lettering. Formats: half frame, 135, XPan, 645, 6×6,
  6×7, 6×8, 6×9, 6×12, 6×17, 4×5; the picture is framed in the format's gate. Date back: in the picture
  on 135, in the film margin on 120 together with optional shooting data.
- **Faster exports:** a 42 MP RAW exports in about 40 s instead of about 110 s. The paper / scanner stage
  is baked once per look from spektrafilm's own maths (ΔE00 ≈ 0.03 from the per-pixel result), film grain
  draws one exact Poisson sample per layer instead of two loops, and bands are developed in parallel.
  Refined previews got faster too.
- **Export progress in the top bar** next to Export…: no window, no percentage; ✕ stops, "Show" opens the
  folder.
- **Chinese interface:** the language chosen in the installer is used by the app; View ▸ Language switches
  it (English / 简体中文).
- **Paper explained:** a tooltip and a note under the Paper menu describe what the paper does and each
  paper's character.

## 1.3.0

- Real-time sliders: the preview updates while you drag (lookup tables, a few ms per frame); one undo step
  per drag.
- Installer in English or Simplified Chinese.
- Filmstrip right-click menu: ratings, pick / reject flags and filters, apply a look to many photos, copy /
  paste / sync, reset, rotate, export, show in Explorer, open, copy path, remove.
- Inter interface font.
- Drag on the histogram to change Blacks, Shadows, Exposure, Highlights or Whites.
- Import Lightroom / Camera Raw presets (.xmp, .lrtemplate) and .cube LUTs; export .sprkpreset.
- Compressed RAW support checked on ten formats; embedded-JPEG fallback for codecs LibRaw cannot decode.
- Optional photo frame and date stamp in preview and export.
- CineStill 800T printed green on every paper: fixed by using Vision3 500T's neutral filtration.

## 1.0 – 1.2

- Lightroom-style editor around the spektrafilm engine: Navigator, Looks, History, Develop panel,
  filmstrip; camera-inspired and classic film looks; white balance, crop and straighten, before / after,
  full-resolution detail at 100 %; Windows installer.
