# spektralionkk

**English** | [简体中文](README.zh-CN.md)

Spectral film and print simulation for Windows: a darkroom-style photo editor built on the
[spektrafilm](https://github.com/andreavolpato/spektrafilm) engine by Andrea Volpato.

English and 简体中文 interface. Free software under the [GNU GPL v3](LICENSE).

## Download

**[Download the spektralionkk 1.4.0 installer for Windows](https://github.com/Donji-zzZ/spektralionkk/releases/download/v1.4.0/spektralionkk-1.4.0-setup.exe)** (124 MB)

All versions are on the [Releases page](https://github.com/Donji-zzZ/spektralionkk/releases), which also
has source code archives.

The installer is not code-signed, so Windows SmartScreen may show a warning: choose **More info**, then
**Run anyway**.

Version 1.4.0 was built before the project was renamed, so once installed it still shows its old name,
sprktralionkk.

## What it adds to spektrafilm

- **A redesigned interface** in a Lightroom-style layout: navigator, looks, history, filmstrip,
  histogram and editing panels.
- **Faster filter previews.** Sliders update in real time from lookup tables, with no graphics card
  needed. Full-quality grain, halation and sharpening render when you let go.
- **Your own photos.** Open files or folders, or drag them in: RAW, JPEG, TIFF, PNG and EXR.
- **Automatic exposure compensation,** on by default, with selectable metering and a manual
  exposure slider.
- **RAW editing,** including compressed RAW from Sony, Canon (CR3 and C-RAW), Fujifilm, Nikon,
  Panasonic and DNG. A few of the newest codecs (Nikon High Efficiency, JPEG XL DNG) can't be decoded
  yet; for those the app edits the camera's embedded full-size JPEG and says so.
- **Compressed export.** Save edited RAW files as JPEG (quality 50–100), 16-bit TIFF or PNG in sRGB,
  Display P3, Adobe RGB, ProPhoto or Rec.2020. RAW files are exported to these formats, not rewritten
  as RAW.
- **Presets and LUTs.** Import Lightroom / Camera Raw presets (`.xmp`, `.lrtemplate`) and `.cube` LUTs.
- **Film edge and date back.** Film strips, frame numbers and date stamps for formats from half frame
  to 4×5.

See the [user guide](docs/USER_GUIDE.txt) for the full feature list and shortcuts.

## Run from source

Requires Windows and Python 3.13, the version spektrafilm supports.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m spektralionkk.app
```

The first launch on a PC compiles the processing kernels, which takes about 30 seconds.

## Credits and licences

- Code: GPL-3.0, see [LICENSE](LICENSE).
- Film simulation engine and colour film / paper profiles: spektrafilm by Andrea Volpato, code GPL-3.0,
  profiles CC BY-SA 4.0, see [SPEKTRAFILM_LICENSE.txt](SPEKTRAFILM_LICENSE.txt).
- Interface font: Inter by Rasmus Andersson, SIL Open Font License 1.1.
- Full credits for all bundled data, including the black-and-white profiles, are in the
  [user guide](docs/USER_GUIDE.txt) and [`spektralionkk/data/`](spektralionkk/data/).

Film, camera, software and brand names are trademarks of their owners and only identify data, file
formats or inspiration. spektralionkk is not affiliated with any of these projects or companies.
