"""The few things that differ between Windows and macOS: where the app keeps its data, and how to show a file in
the system file manager."""

from __future__ import annotations

import os
import sys

APP_DIR = "spektralionkk"
IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"


def data_root() -> str:
    """Per-user folder for the library, imported LUTs, caches and logs.
    Windows: %LOCALAPPDATA%\\spektralionkk; macOS: ~/Library/Application Support/spektralionkk;
    Linux: ~/.local/share/spektralionkk. A LOCALAPPDATA variable wins on every system (the tests use it to work
    in a throwaway folder)."""
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return os.path.join(base, APP_DIR)
    if IS_MAC:
        return os.path.join(os.path.expanduser("~/Library/Application Support"), APP_DIR)
    if IS_WINDOWS:
        return os.path.join(os.path.expanduser("~"), "AppData", "Local", APP_DIR)
    return os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), APP_DIR)


def file_manager() -> str:
    """'Explorer', 'Finder' or 'file manager' — used in menu texts such as 'Show in Finder'."""
    return "Finder" if IS_MAC else ("Explorer" if IS_WINDOWS else "file manager")


def reveal_command(path: str) -> list[str]:
    path = os.path.normpath(path)
    if IS_WINDOWS:
        return ["explorer.exe", "/select,", path]
    if IS_MAC:
        return ["open", "-R", path]
    return ["xdg-open", os.path.dirname(path) or "."]


def reveal(path: str) -> None:
    """Show the file selected in Explorer / Finder."""
    from PySide6 import QtCore

    cmd = reveal_command(path)
    QtCore.QProcess.startDetached(cmd[0], cmd[1:])


def native_keys(text: str) -> str:
    """Shortcut names as this system's keyboard shows them: Ctrl+Shift+O -> ⌘⇧O on a Mac."""
    if not IS_MAC or not text or "+" not in text:
        return text
    for a, b in (("Ctrl+Shift+", "⌘⇧"), ("Ctrl+Alt+", "⌘⌥"), ("Ctrl+", "⌘"), ("Shift+", "⇧"), ("Alt+", "⌥")):
        text = text.replace(a, b)
    return text


def native_keys_tree(root) -> None:
    """Rewrite the shortcut names in the tooltips of a finished widget tree (macOS only)."""
    if not IS_MAC or root is None:
        return
    from PySide6 import QtGui, QtWidgets

    for w in [root] + root.findChildren(QtWidgets.QWidget):
        tip = w.toolTip()
        if tip:
            w.setToolTip(native_keys(tip))
    for a in root.findChildren(QtGui.QAction):
        if a.toolTip():
            a.setToolTip(native_keys(a.toolTip()))
