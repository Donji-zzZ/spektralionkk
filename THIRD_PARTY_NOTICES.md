# Third-party notices

spektralionkk is free software under the GNU General Public License v3 (see [LICENSE](LICENSE)).
It is built on, and ships with, the following work by others.

## spektrafilm — film simulation engine and colour film / paper profiles

- **Author:** Andrea Volpato
- **Source:** https://github.com/andreavolpato/spektrafilm (pinned commit in `requirements.txt`)
- **Licences:** engine code GPL-3.0; film and paper profiles and their direct derivatives (including the
  lookup tables this app computes from them at run time) **CC BY-SA 4.0**. The full profile licence,
  `SPEKTRAFILM_LICENSE.txt`, is shipped next to the app by `build.ps1`.

> spektrafilm by Andrea Volpato
> https://github.com/andreavolpato/spektrafilm
> Licensed CC BY-SA 4.0

The profiles are used unmodified. spektralionkk is an independent application that uses spektrafilm; it is
not affiliated with or endorsed by the spektrafilm project.

## Black-and-white film profiles, Ilford Multigrade paper, CineStill 800T alias

- **Files:** `app/spektralionkk/data/profiles/*.json`, `app/spektralionkk/data/paper_grades.json`
- **Source:** SpektraLab, https://github.com/JamesQiu2005/SpektraLab — built from the manufacturers'
  published data sheets. Thank you!
- **Licence:** GPL-3.0. Copied unmodified; the original notice describing how each file was made is
  `app/spektralionkk/data/NOTICE-SpektraLab-profiles.md`.
- `cinestill_800t.json` is an alias of spektrafilm's Kodak Vision3 500T profile (CC BY-SA 4.0, above):
  it only adds a name and usage keys; the spectral data is read from spektrafilm's file.

## Inter typeface

- **Author:** Rasmus Andersson — https://rsms.me/inter/
- **Licence:** SIL Open Font License 1.1 — `app/spektralionkk/data/fonts/Inter-LICENSE-OFL.txt`

## Inno Setup Simplified Chinese translation

- `installer/ChineseSimplified.isl`, unmodified, from the Inno Setup project (https://github.com/jrsoftware/issrc,
  `Files/Languages/ChineseSimplified.isl`), under the Inno Setup licence.

## Python packages bundled in the installer

Each keeps its own licence. Notably: Qt for Python / PySide6 (LGPL-3.0), LibRaw via rawpy (LGPL-2.1 or
CDDL-1.0), Exiv2 via python-exiv2 (GPL-2.0-or-later), FFTW via pyFFTW (GPL-2.0-or-later), lensfun via
lensfunpy (LGPL-3.0; lens database CC BY-SA 3.0), OpenImageIO (Apache-2.0); NumPy, SciPy, Numba / llvmlite,
scikit-image, colour-science, Pillow, opt_einsum, imageio and tifffile under BSD / MIT-style licences.

## Trademarks

Film, paper, camera, software and brand names (Kodak, Fujifilm, Ilford, CineStill, Ricoh, Leica, Sony,
Adobe Lightroom, Camera Raw and others) are trademarks of their owners. They are used only to identify the
data a profile was built from, file formats, or the inspiration of a look. The "camera-inspired" looks are
approximations made with this app's own tools, not the manufacturers' profiles. spektralionkk is not
affiliated with any of these companies or projects.
