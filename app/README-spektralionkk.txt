spektralionkk 1.4 — spectral film & print simulation for Windows and macOS
============================================================================

Language
  English or 简体中文. The language you pick in the Windows installer is used by the app (on a Mac:
  the system language); change it any time with View ▸ Language (takes effect after a restart).

On a Mac
  Ctrl in this text is the ⌘ Command key; Show in Explorer is Show in Finder. Photos and folders
  can also be dropped on the Dock icon or opened with Finder's Open With ▸ spektralionkk.

Layout (Lightroom-style)
  Left   Navigator (FIT / FILL / 100% / 200%; click or drag to move around), Looks, History,
         Copy… / Paste
  Top    Open… / Folder… / Export…; export progress appears right next to Export…
  Centre the photo; toolbar: Before (\), Before | After split (Y), Clipping (J); filmstrip
  Right  Histogram + camera info, tools (Crop R, White-balance picker W), then Profile (film,
         paper, B&W contrast grade), Film Edge (film strip and date back), Basic (WB, exposure,
         contrast, highlights, shadows, whites, blacks, clarity, vibrance, saturation), Tone Curve,
         Color Mixer (HSL), Color Grading, Enlarger, Film & Grain, Effects (vignette, glare,
         diffusion filter, creative LUT), Detail, Lens; Sync… / Reset

Film and paper
  Film is what the photo is exposed and developed on. Paper is the photographic paper the
  negative is printed on, as in a darkroom: a negative is an inverted orange image and the paper
  turns it into the print, each paper with its own contrast and colour (Portra Endura soft and
  natural, Ultra Endura punchy, Ektacolor Edge bright minilab prints, Crystal Archive Fujifilm's
  lab paper, Vision 2383 / 2393 cinema print film). "Direct scan" skips the print — that is how
  slides are viewed. A note under the Paper menu describes the selected paper.

White balance
  Every photo starts with the camera's own (as-shot) white balance; films and Looks never change
  it. Change it in Basic ▸ WB (Auto, presets, Temp / Tint) or with the picker (W).

Workflow
  1. Open photos or a folder (Ctrl+O / Ctrl+Shift+O) or drag files in. RAW (NEF, CR2/CR3, ARW,
     RAF, ORF, RW2, DNG, …, including compressed RAW), JPEG, TIFF, PNG, EXR.
  2. Click a Look on the left, or pick a film and paper in Profile ("Digital (no film)" turns the
     film simulation off).
  3. Fine-tune in Basic and the other panels — or drag left/right on the histogram to change
     Blacks, Shadows, Exposure, Highlights or Whites directly.
  4. Crop (R): drag corners/edges or inside the box; choose an aspect (Free = unlocked).
  5. Export (Ctrl+E): JPEG / TIFF 16-bit / PNG in sRGB, Display P3, Adobe RGB, ProPhoto, Rec.2020,
     with or without the film frame and date stamp. The export runs in the background; a slim
     progress bar next to Export… (top left) shows it, ✕ stops it, "Show" opens the folder.

Speed
  Sliders update the picture in real time: colour, tone, exposure, white balance, film, paper,
  curves, HSL and LUTs are computed from lookup tables (a few milliseconds per frame, any CPU, no
  graphics card needed). When you let go, the full-quality render adds grain, halation, coupler
  diffusion and sharpening. Grain is simulated where it is visible — at 100% zoom and in exports
  (View menu to always show it). Rendering runs at below-normal priority and leaves two CPU cores
  free, so the PC stays responsive. The first launch on a PC compiles the processing kernels
  (~30 s, one time).
  Zooming in: a sharp full-resolution view appears at once; the grain, halation and clarity of
  the visible area are developed a moment later and replace it. The full-resolution photo is
  decoded in the background as soon as the preview is ready, so the first zoom does not wait.
  Exports: the film is developed at full resolution (grain, halation, couplers) in parallel bands;
  the paper / scanner part comes from a table baked once per look with spektrafilm's own maths
  (ΔE00 ≈ 0.03 from per-pixel), so a 42 MP RAW exports in about 40 s on a 12-core PC.

Presets and LUTs
  File ▸ Import Presets & LUTs… (or right-click the Looks list) reads Lightroom / Camera Raw
  presets (.xmp, .lrtemplate), .cube LUTs and spektralionkk presets (.sprkpreset). Imported
  presets appear under My Looks. Lightroom settings without an equivalent here (e.g. Texture,
  Dehaze, masks) are skipped and listed. Export any look or the current settings as a
  .sprkpreset to share it. Effects ▸ Creative LUT ▸ Import… adds a .cube LUT to one photo.

Filmstrip
  Right-click a photo (or several) for: star ratings (keys 0–5), pick / reject flags (P / X / U),
  Apply Look, Copy / Paste / Sync settings, Reset, Rotate, Export, Show in Explorer, Open in the
  default app, Copy file path, Remove from library, and Show ▸ (all / picks / hide rejects /
  rated). A small red dot marks edited photos.

Film Edge & date back
  Turn on the switch in the Film Edge header (right panel, under Profile). Film strip prints the
  film around the picture, to scale: 135 with perforations (white as a backlit scan, or black),
  the stock's own edge print, frame numbers and DX code; 120 with its rebate lettering. Film
  format picks the gate — half frame, 135, XPan, 645, 6×6, 6×7, 6×8, 6×9, 6×12, 6×17, 4×5 — and
  the picture is framed in it (6×6 is square; move it with the Crop tool). Other styles: filed
  carrier, slide mount, white border. Date back: an orange LED date in the picture on 135, in the
  film margin on 120, where Shooting data adds shutter, aperture and focal length.
  View ▸ Show Film Frame (Shift+F) hides it in the preview only; the Export dialog has its own
  "Include the film frame" checkbox (on by default).

Compressed RAW
  Lossless and lossy compressed RAW files from Sony, Canon (CR3 and C-RAW), Fujifilm, Nikon,
  Panasonic and DNG open normally. A few newest codecs (Nikon High Efficiency, JPEG XL DNG) are
  not supported by the RAW decoder yet; for those the app edits the camera's embedded full-size
  JPEG instead and says so.

Looks
  Camera-inspired looks (GR-, Leica- and Fujifilm-inspired) are approximations of those styles
  made with this app's film simulation and finishing tools. They are not the manufacturers'
  profiles, and spektralionkk is not affiliated with Ricoh, Leica or Fujifilm. The Leica-inspired
  ones aim at the dense "German" rendering: deep, rich colour, deep blacks, dark corners.
  On the Film Edge a camera-inspired look prints its own name (LEICA CLASSIC and so on, with
  LEICA in red) instead of the film it is built on; choosing another film brings that film's
  edge print back. Photos styled with an earlier version keep their colours until you click
  the look again.

Check a PC:  "spektralionkk self-test" in the Start Menu (or spektralionkk.exe --selftest).
Check a Mac: /Applications/spektralionkk.app/Contents/MacOS/spektralionkk --selftest  (Terminal)
Your edits:  %LOCALAPPDATA%\spektralionkk\library.json   (log: spektralionkk.log)
             Mac: ~/Library/Application Support/spektralionkk/library.json
LUTs:        the luts folder next to it (File ▸ Open Presets & LUTs Folder)

Credits & licences
  Film simulation engine and the colour film / paper profiles: spektrafilm by Andrea Volpato
    https://github.com/andreavolpato/spektrafilm — code GPL-3.0, profiles CC BY-SA 4.0
  Black-and-white film profiles (Kodak Tri-X 400, T-Max 100, Ilford HP5 Plus 400, Fujifilm Neopan
  Acros 100 II), Ilford Multigrade IV RC paper and the CineStill 800T alias: SpektraLab (GPL-3.0),
    built from the manufacturers' published datasheets — with thanks. Licence notice:
    spektralionkk\data\NOTICE-SpektraLab-profiles.md.
  Interface font: Inter by Rasmus Andersson, SIL Open Font License 1.1
    (spektralionkk\data\fonts\Inter-LICENSE-OFL.txt).
  Installer: Inno Setup; Simplified Chinese installer translation from the Inno Setup project.
  Film, camera, software and brand names (including Lightroom and Camera Raw) are trademarks of
  their owners and only identify the data, file formats or inspiration. spektralionkk is not
  affiliated with any of these projects or companies.
  spektralionkk is free software under the GNU GPL v3 (see LICENSE). If you distribute it,
  you must also offer its source code.
