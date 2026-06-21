from __future__ import annotations

from pathlib import Path


PROJECT_DIR = Path("E:/YouTubeSimpleDownloader")
DEFAULT_DOWNLOAD_DIR = PROJECT_DIR / "downloads"


def ensure_default_dirs() -> None:
    DEFAULT_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
