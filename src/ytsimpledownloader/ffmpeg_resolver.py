from __future__ import annotations

from collections.abc import Callable
import hashlib
import logging
import os
from pathlib import Path
import re
from shutil import copy2
import subprocess
import sys

import imageio_ffmpeg

from .paths import FFMPEG_DIR


LOGGER = logging.getLogger(__name__)
StatusCallback = Callable[[str], None]
MINIMUM_FFMPEG_VERSION = (8, 1, 2)
MINIMUM_FFMPEG_VERSION_TEXT = ".".join(str(part) for part in MINIMUM_FFMPEG_VERSION)
FFMPEG_VERSION_PATTERN = re.compile(r"ffmpeg version\s+(\d+)\.(\d+)(?:\.(\d+))?", re.IGNORECASE)


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


def _read_ffmpeg_version(ffmpeg_path: Path) -> tuple[tuple[int, int, int], str]:
    try:
        completed = subprocess.run(
            [str(ffmpeg_path), "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"Unable to run FFmpeg at {ffmpeg_path}: {exc}") from exc

    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    match = FFMPEG_VERSION_PATTERN.search(output)
    if completed.returncode != 0 or not match:
        detail = output.splitlines()[0] if output else f"exit code {completed.returncode}"
        raise RuntimeError(f"Unable to determine FFmpeg version at {ffmpeg_path}: {detail}")

    version = tuple(int(part or 0) for part in match.groups())
    return version, ".".join(str(part) for part in version)


def _validate_ffmpeg(
    ffmpeg_path: Path,
    source_label: str,
    status_callback: StatusCallback | None = None,
) -> None:
    try:
        version, version_text = _read_ffmpeg_version(ffmpeg_path)
    except RuntimeError as exc:
        message = f"Rejected {source_label} FFmpeg: {exc}"
        LOGGER.error(message)
        if status_callback:
            status_callback(message)
        raise RuntimeError(message) from exc

    if version < MINIMUM_FFMPEG_VERSION:
        message = (
            f"Rejected {source_label} FFmpeg at {ffmpeg_path}: version {version_text} is below the "
            f"required minimum {MINIMUM_FFMPEG_VERSION_TEXT}."
        )
        LOGGER.error(message)
        if status_callback:
            status_callback(message)
        raise RuntimeError(message)


def resolve_ffmpeg_source(status_callback: StatusCallback | None = None) -> tuple[Path, bool]:
    for candidate in _bundled_ffmpeg_candidates():
        if candidate.is_file():
            _validate_ffmpeg(candidate, "bundled/manual", status_callback)
            return candidate, False

    fallback = Path(imageio_ffmpeg.get_ffmpeg_exe())
    message = f"Bundled FFmpeg was not found; checking imageio-ffmpeg fallback: {fallback}"
    LOGGER.warning(message)
    if status_callback:
        status_callback(message)
    _validate_ffmpeg(fallback, "imageio-ffmpeg fallback", status_callback)
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
