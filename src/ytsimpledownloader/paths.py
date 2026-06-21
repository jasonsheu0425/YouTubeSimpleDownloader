from __future__ import annotations

import os
from pathlib import Path


APP_NAME = "YouTubeSimpleDownloader"


def _app_data_root() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base)
        return Path.home() / "AppData" / "Local"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))


def _downloads_root() -> Path:
    downloads = Path.home() / "Downloads"
    if downloads.exists():
        return downloads
    return Path.home()


APP_DATA_DIR = _app_data_root() / APP_NAME
PROJECT_DIR = APP_DATA_DIR
DEFAULT_DOWNLOAD_DIR = _downloads_root() / APP_NAME
FFMPEG_DIR = APP_DATA_DIR / "ffmpeg"


def ensure_default_dirs() -> None:
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
