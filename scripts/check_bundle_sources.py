"""Reject native bundle inputs from outside the approved Windows build roots."""

from __future__ import annotations

import argparse
import ast
import ctypes
import hashlib
import sys
from pathlib import Path, PureWindowsPath


class BundleSourceError(RuntimeError):
    """A collected native file has an unapproved or inconsistent origin."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _within(path: Path, root: Path) -> bool:
    return path.is_relative_to(root)


def _windows_directory() -> Path:
    buffer = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetWindowsDirectoryW(buffer, len(buffer))
    if not 0 < length < len(buffer):
        raise BundleSourceError("Unable to identify the Windows runtime directory.")
    return Path(buffer.value).resolve()


def verify_collected_sources(
    project_root: Path,
    dist_dir: Path,
    toc_path: Path,
    *,
    python_base: Path | None = None,
    windows_root: Path | None = None,
) -> int:
    """Verify native origins and bytes before the application EXE is signed."""
    project_root, dist_dir = project_root.resolve(), dist_dir.resolve()
    python_base = (python_base or Path(sys.base_prefix)).resolve()
    windows_root = (windows_root or _windows_directory()).resolve()
    package_root = (project_root / ".release-venv/Lib/site-packages").resolve()
    generated_exe = (project_root / "build/YouTubeSimpleDownloader/YouTubeSimpleDownloader.exe").resolve()
    ffmpeg_exe = (project_root / "ffmpeg/ffmpeg.exe").resolve()
    try:
        toc = ast.literal_eval(toc_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError) as exc:
        raise BundleSourceError("The PyInstaller collection record is missing or malformed.") from exc
    if not isinstance(toc, tuple) or not toc or not isinstance(toc[0], list):
        raise BundleSourceError("Unexpected PyInstaller collection record format.")

    observed: set[str] = set()
    for entry in toc[0]:
        if not isinstance(entry, tuple) or len(entry) != 3:
            raise BundleSourceError("Malformed collection record entry.")
        destination, raw_source, kind = entry
        if kind not in {"BINARY", "EXTENSION", "EXECUTABLE"}:
            continue
        if not isinstance(destination, str) or not isinstance(raw_source, str):
            raise BundleSourceError("Malformed native collection path.")
        relative = PureWindowsPath(destination)
        if relative.is_absolute() or relative.drive or ".." in relative.parts:
            raise BundleSourceError("Native collection destination escapes the bundle.")
        source = Path(raw_source).resolve()
        if kind == "EXECUTABLE":
            approved = source == generated_exe and relative.as_posix() == "YouTubeSimpleDownloader.exe"
            target = dist_dir.joinpath(*relative.parts)
        else:
            approved = (
                _within(source, package_root)
                or source.parent == python_base
                or _within(source, python_base / "DLLs")
                or _within(source, windows_root / "System32")
                or _within(source, windows_root / "WinSxS")
                or source == ffmpeg_exe
            )
            target = (dist_dir / "_internal").joinpath(*relative.parts)
        if not approved:
            raise BundleSourceError(f"Unapproved native source for {destination}.")
        if not source.is_file() or not target.is_file() or _sha256(source) != _sha256(target):
            raise BundleSourceError(f"Collected native bytes differ for {destination}.")
        key = target.relative_to(dist_dir).as_posix().casefold()
        if key in observed:
            raise BundleSourceError(f"Duplicate native collection destination: {destination}.")
        observed.add(key)

    actual = {
        path.relative_to(dist_dir).as_posix().casefold()
        for path in dist_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in {".exe", ".dll", ".pyd"}
    }
    if not observed or observed != actual:
        raise BundleSourceError("Native bundle inventory differs from the verified collection record.")
    return len(observed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--dist-dir", type=Path, required=True)
    parser.add_argument("--toc", type=Path, required=True)
    args = parser.parse_args()
    try:
        count = verify_collected_sources(args.project_root, args.dist_dir, args.toc)
    except (OSError, BundleSourceError) as exc:
        parser.error(str(exc))
    print(f"Verified approved origins and bytes for {count} bundled native files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
