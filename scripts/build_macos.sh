#!/usr/bin/env bash
# Build spektralionkk for macOS (Apple silicon, macOS 14 or later):
#   dist/spektralionkk.app                                  the app
#   release/spektralionkk-<version>-macos-arm64.dmg         the disk image people download
#
# Needs a Mac with Apple silicon, Python 3.13 and a virtual environment with the requirements (see README.md):
#   python3.13 -m venv .venv
#   .venv/bin/pip install -r requirements.txt -r requirements-build.txt
#   scripts/build_macos.sh
#
# Optional signing, so the app opens with a plain double-click instead of the one-time "Open Anyway" step
# (needs an Apple Developer account; .github/workflows/build.yml reads these from repository secrets):
#   MACOS_SIGN_IDENTITY   "Developer ID Application: Your Name (TEAMID)" - a certificate in your keychain
#   and, to notarise:     APPLE_ID, APPLE_TEAM_ID and APPLE_APP_PASSWORD (an app-specific password),
#                         or NOTARY_PROFILE (a profile saved with `xcrun notarytool store-credentials`)
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-.venv/bin/python}"
if [ ! -x "$PY" ]; then
    echo "Python not found at $PY - create the virtual environment first (see README.md)." >&2
    exit 1
fi
if [ "$(uname -m)" != "arm64" ]; then
    echo "warning: this Mac is $(uname -m); spektralionkk is built for Apple silicon (arm64)." >&2
fi

VERSION=$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' app/spektralionkk/__init__.py)
SF=$("$PY" -c "import os, spektrafilm; print(os.path.dirname(spektrafilm.__file__))")
APP=dist/spektralionkk.app
DMG="release/spektralionkk-${VERSION}-macos-arm64.dmg"
ENTITLEMENTS=app/macos/entitlements.plist
IDENTITY="${MACOS_SIGN_IDENTITY:-}"
NOTARIZE=""
if [ -n "$IDENTITY" ]; then
    if [ -n "${NOTARY_PROFILE:-}" ] || { [ -n "${APPLE_ID:-}" ] && [ -n "${APPLE_TEAM_ID:-}" ] &&
                                         [ -n "${APPLE_APP_PASSWORD:-}" ]; }; then
        NOTARIZE=1
    fi
fi

notary() {  # xcrun notarytool <command> <args...> with the credentials from the environment
    local cmd="$1"
    shift
    if [ -n "${NOTARY_PROFILE:-}" ]; then
        xcrun notarytool "$cmd" "$@" --keychain-profile "$NOTARY_PROFILE"
    else
        xcrun notarytool "$cmd" "$@" --apple-id "$APPLE_ID" --team-id "$APPLE_TEAM_ID" --password "$APPLE_APP_PASSWORD"
    fi
}

notarize() {  # $1: a .zip or .dmg for Apple's notary service; waits for the verdict
    local out status id
    out=$(notary submit "$1" --wait --output-format json)
    echo "$out"
    status=$("$PY" -c "import json, sys; print(json.loads(sys.argv[1]).get('status', ''))" "$out")
    id=$("$PY" -c "import json, sys; print(json.loads(sys.argv[1]).get('id', ''))" "$out")
    if [ "$status" != "Accepted" ]; then
        if [ -n "$id" ]; then notary log "$id" || true; fi
        echo "Notarisation was not accepted ($status)." >&2
        exit 1
    fi
}

echo "== spektralionkk $VERSION for macOS"
# Stale numba caches from development runs must not be bundled: the app compiles its own on first start.
find app "$SF" \( -name '*.nbi' -o -name '*.nbc' \) -delete

echo "== Building the app with PyInstaller"
rm -rf "$APP" dist/spektralionkk
"$PY" -m PyInstaller app/spektralionkk_mac.spec --noconfirm --distpath dist --workpath build

echo "== Separating the two libintl libraries"
# exiv2 and lensfunpy each bundle a different libintl.8.dylib: GNU gettext, and glib's small proxy with the
# g_libintl_* functions. PyInstaller gives both the same install name, so lensfunpy's glib would load exiv2's copy
# and the app would not start. Give lensfunpy's copy a name of its own.
LENSFUN="$APP/Contents/Frameworks/lensfunpy"
GLIB_INTL=libintl-glib.8.dylib

sign_file() {  # install_name_tool breaks a file's signature, and Apple silicon runs only signed code
    if [ -n "$IDENTITY" ]; then
        codesign --force --timestamp --options runtime --sign "$IDENTITY" "$1"
    else
        codesign --force --sign - "$1"
    fi
}

mv "$LENSFUN/__dot__dylibs/libintl.8.dylib" "$LENSFUN/__dot__dylibs/$GLIB_INTL"
install_name_tool -id "@loader_path/$GLIB_INTL" "$LENSFUN/__dot__dylibs/$GLIB_INTL"
sign_file "$LENSFUN/__dot__dylibs/$GLIB_INTL"
for f in "$LENSFUN"/__dot__dylibs/*.dylib "$LENSFUN"/*.so; do
    old=$(otool -L "$f" | awk '/libintl\.8\.dylib/ {print $1}')
    if [ -n "$old" ]; then
        case "$f" in
            *.so) new="@loader_path/__dot__dylibs/$GLIB_INTL" ;;
            *) new="@loader_path/$GLIB_INTL" ;;
        esac
        echo "$(basename "$f"): $old -> $new"
        install_name_tool -change "$old" "$new" "$f"
        sign_file "$f"
    fi
done

echo "== Checking the signature"
# PyInstaller signs every file (ad hoc, or with MACOS_SIGN_IDENTITY and the hardened runtime). Apple silicon runs
# only signed code, and macOS calls an app with a broken seal "damaged", so make sure the seal is intact.
if ! codesign --verify --deep --strict "$APP" 2>/dev/null; then
    echo "re-signing the bundle"
    if [ -n "$IDENTITY" ]; then
        codesign --force --deep --timestamp --options runtime --entitlements "$ENTITLEMENTS" --sign "$IDENTITY" "$APP"
    else
        codesign --force --deep --sign - "$APP"
    fi
fi
codesign --verify --deep --strict --verbose=2 "$APP"

echo "== Self-test of the built app"
TESTDATA=$(mktemp -d)
if ! LOCALAPPDATA="$TESTDATA" "$APP/Contents/MacOS/spektralionkk" --selftest-quiet; then
    cat "$TESTDATA/spektralionkk/selftest.txt" "$TESTDATA/spektralionkk/spektralionkk.log" 2>/dev/null || true
    echo "The self-test failed." >&2
    exit 1
fi
cat "$TESTDATA/spektralionkk/selftest.txt"
echo
rm -rf "$TESTDATA"
codesign --verify --deep --strict "$APP"  # running it must not have changed the bundle

BACKGROUND=app/macos/dmg-background.png  # shows the one-time "Open Anyway" step
if [ -n "$NOTARIZE" ]; then
    echo "== Notarising the app"
    ditto -c -k --keepParent "$APP" build/spektralionkk-app.zip
    notarize build/spektralionkk-app.zip
    xcrun stapler staple "$APP"
    spctl --assess --type execute --verbose=2 "$APP"
    BACKGROUND=app/macos/dmg-background-signed.png
fi

echo "== Making the disk image"
mkdir -p release
rm -f "$DMG" "$DMG.sha256"
if ! "$PY" - "$APP" "$DMG" "$BACKGROUND" <<'PYEOF'
import sys

import dmgbuild

app, dmg, background = sys.argv[1:4]
dmgbuild.build_dmg(dmg, "spektralionkk", settings_file="app/macos/dmg_settings.py",
                   defines={"app": app, "background": background})
PYEOF
then
    echo "dmgbuild is missing or failed: making a plain disk image (the app and a link to Applications)"
    STAGE=$(mktemp -d)
    ditto "$APP" "$STAGE/spektralionkk.app"
    ln -s /Applications "$STAGE/Applications"
    hdiutil create -volname spektralionkk -srcfolder "$STAGE" -ov -format UDZO "$DMG"
    rm -rf "$STAGE"
fi

if [ -n "$IDENTITY" ]; then
    codesign --force --timestamp --sign "$IDENTITY" "$DMG"
fi
if [ -n "$NOTARIZE" ]; then
    echo "== Notarising the disk image"
    notarize "$DMG"
    xcrun stapler staple "$DMG"
    spctl --assess --type open --context context:primary-signature --verbose=2 "$DMG"
fi
hdiutil verify "$DMG"
(cd release && shasum -a 256 "$(basename "$DMG")" > "$(basename "$DMG").sha256")
echo "== Done"
ls -lh "$DMG"
if [ -z "$NOTARIZE" ]; then
    echo "Not notarised: on first open, macOS asks people to confirm once (the disk image window shows how)."
fi
