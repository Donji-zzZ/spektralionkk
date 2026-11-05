"""Photo library and per-photo edits, persisted in %LOCALAPPDATA%\\sprktralionkk\\library.json."""

from __future__ import annotations

import json
import os
import tempfile

from .engine import SUPPORTED_EXTENSIONS
from .settings import DevelopSettings


def data_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "sprktralionkk")
    os.makedirs(d, exist_ok=True)
    return d


def expand_paths(paths) -> list[str]:
    out = []
    for p in paths:
        if os.path.isdir(p):
            for name in sorted(os.listdir(p), key=str.lower):
                full = os.path.join(p, name)
                if os.path.isfile(full) and os.path.splitext(name)[1].lower() in SUPPORTED_EXTENSIONS:
                    out.append(os.path.normpath(full))
        elif os.path.isfile(p) and os.path.splitext(p)[1].lower() in SUPPORTED_EXTENSIONS:
            out.append(os.path.normpath(p))
    seen, uniq = set(), []
    for p in out:
        k = p.lower()
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    return uniq


class Library:
    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(data_dir(), "library.json")
        self.photos: list[str] = []
        self.edits: dict[str, dict] = {}
        self.default: dict = {}
        self.prefs: dict = {}
        self.meta: dict[str, dict] = {}  # path -> {"rating": 1..5, "flag": "pick" | "reject"}
        self._load()

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        self.photos = [p for p in data.get("photos", []) if os.path.isfile(p)]
        self.edits = data.get("edits", {})
        self.default = data.get("default", {})
        self.prefs = data.get("prefs", {})
        self.meta = {p: m for p, m in data.get("meta", {}).items() if isinstance(m, dict)}

    def save(self):
        data = {"version": 1, "photos": self.photos, "edits": self.edits, "default": self.default,
                "prefs": self.prefs, "meta": self.meta}
        d = os.path.dirname(self.path)
        fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=1)
            os.replace(tmp, self.path)
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass

    # -- photos
    def add(self, paths) -> list[str]:
        new = [p for p in expand_paths(paths) if p not in self.photos]
        self.photos.extend(new)
        return new

    def remove(self, paths):
        rm = set(paths)
        self.photos = [p for p in self.photos if p not in rm]

    # -- settings
    def default_settings(self) -> DevelopSettings:
        return DevelopSettings.from_dict(self.default)

    def settings_for(self, path: str) -> DevelopSettings:
        if path in self.edits:
            return DevelopSettings.from_dict(self.edits[path])
        return self.default_settings()

    def set_settings(self, path: str, s: DevelopSettings):
        self.edits[path] = s.to_dict()

    def is_edited(self, path: str) -> bool:
        return path in self.edits

    # -- ratings and flags
    def rating(self, path: str) -> int:
        return int(self.meta.get(path, {}).get("rating", 0))

    def flag(self, path: str) -> str:
        return str(self.meta.get(path, {}).get("flag", ""))

    def set_meta(self, path: str, **values):
        m = self.meta.setdefault(path, {})
        for k, v in values.items():
            if v in (0, "", None):
                m.pop(k, None)
            else:
                m[k] = v
        if not m:
            self.meta.pop(path, None)
