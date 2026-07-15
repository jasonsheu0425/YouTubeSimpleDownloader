from __future__ import annotations

from collections.abc import Callable
import hashlib
import logging
import os
from pathlib import Path
from shutil import copy2
import sys

import imageio_ffmpeg

from .paths import FFMPEG_DIR


LOGGER = logging.getLogger(__name__)
StatusCallback = Callable[[str], None]


def _bundled_ffmpeg_candidates() -> list[Path]:
    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        executable_root = Path(sys.executable).resolve().parent
        return [
            bundle_root / "ffmpeg" / "ffmpeg.exe",
            executable_root / "_internal" / "ffmpeg" / "ffmpeg.exe",
            executable_root / "ffmpeg" / "ffmpeg.exe",
        ]
    return [Path(__file__).resolve().parents[2] / "ffmpeg" / "ffmpeg.exe"]


def resolve_ffmpeg_source(status_callback: StatusCallback | None = None) -> tuple[Path, bool]:
    for candidate in _bundled_ffmpeg_candidates():
        if candidate.is_file():
            return candidate, False

    fallback = Path(imageio_ffmpeg.get_ffmpeg_exe())
    message = f"Bundled FFmpeg was not found; using imageio-ffmpeg fallback: {fallback}"
    LOGGER.warning(message)
    if status_callback:
        status_callback(message)
    return fallback, True


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_ffmpeg_exe(status_callback: StatusCallback | None = None) -> str:
    source, _is_fallback = resolve_ffmpeg_source(status_callback)
    target = FFMPEG_DIR / "ffmpeg.exe"
    needs_sync = (
        not target.exists()
        or target.stat().st_size != source.stat().st_size
        or _sha256(target) != _sha256(source)
    )
    if needs_sync:
        target.parent.mkdir(parents=True, exist_ok=True)
        copy2(source, target)

    ffmpeg_dir = str(target.parent)
    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    if ffmpeg_dir not in path_entries:
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
    return str(target)
