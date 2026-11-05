"""The app was called "sprktralionkk" up to 1.4.0. On the first start under the new name, copy the user's
library (edits, ratings, looks, preferences) and imported LUTs from the old data folder. The old folder is left
as it was; caches and logs are not copied."""

from __future__ import annotations

import os
import shutil

NEW_DIR = "spektralionkk"
OLD_DIR = "sprktralionkk"
SKIP = {"numba_cache", "selftest.txt"}


def migrate_old_data(base: str | None = None) -> bool:
    base = base or os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    new, old = os.path.join(base, NEW_DIR), os.path.join(base, OLD_DIR)
    marker = os.path.join(new, ".migrated")
    if (not os.path.isdir(old) or os.path.exists(marker)
            or os.path.exists(os.path.join(new, "library.json"))):
        return False
    os.makedirs(new, exist_ok=True)
    for name in os.listdir(old):
        if name in SKIP or name.endswith(".log"):
            continue
        src, dst = os.path.join(old, name), os.path.join(new, name.replace(OLD_DIR, NEW_DIR))
        if os.path.exists(dst):
            continue
        try:
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
        except OSError:
            pass
    try:
        with open(marker, "w", encoding="utf-8") as fh:
            fh.write(f"Copied from {old}\n")
    except OSError:
        pass
    return True
