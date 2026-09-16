"""Runtime and writable-path helpers for source and packaged app launches."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def runtime_root() -> Path:
    """Directory containing bundled read-only assets such as the app icon."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def data_root() -> Path:
    """Directory for reports, settings, and the persistent Playwright profile."""
    if is_frozen():
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return base / "Patreon Updater"
    return Path(__file__).resolve().parent.parent
