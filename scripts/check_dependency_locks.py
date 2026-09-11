"""Verify repository dependency locks are complete and match their declared inputs."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCK_NAMES = ("bootstrap", "runtime", "dev", "build")
LOCK_LINE_PATTERN = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)==(?P<version>[^\s]+) "
    r"--hash=sha256:(?P<hash>[0-9a-f]{64})$"
)
REQUIRED_PACKAGES = {
    "bootstrap": {"pip"},
    "runtime": {"setuptools", "pyside6", "yt-dlp", "imageio-ffmpeg"},
    "dev": {"setuptools", "pyside6", "yt-dlp", "imageio-ffmpeg", "pytest"},
    "build": {"setuptools", "pyside6", "yt-dlp", "imageio-ffmpeg", "pyinstaller"},
}


class DependencyLockError(RuntimeError):
    """Raised when a lock is incomplete, mutable, or inconsistent with policy."""


def normalized_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_lock(path: Path) -> dict[str, tuple[str, str]]:
    """Parse exact one-hash-per-resolved-package lock entries."""
    entries: dict[str, tuple[str, str]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line or line.startswith("#"):
            continue
        match = LOCK_LINE_PATTERN.fullmatch(line)
        if match is None:
            raise DependencyLockError(f"{path}:{line_number} is not a complete hashed pin.")
        name = normalized_name(match.group("name"))
        if name in entries:
            raise DependencyLockError(f"{path}:{line_number} duplicates {name}.")
        entries[name] = (match.group("version"), match.group("hash"))
    if not entries:
        raise DependencyLockError(f"{path} contains no locked packages.")
    return entries


def verify_dependency_locks(project_root: Path = PROJECT_ROOT) -> int:
    """Validate generated locks and legacy selector files without resolving packages."""
    requirement_directory = project_root / "requirements"
    for name in LOCK_NAMES:
        entries = parse_lock(requirement_directory / f"{name}.lock")
        missing = REQUIRED_PACKAGES[name] - set(entries)
        if missing:
            raise DependencyLockError(
                f"requirements/{name}.lock is missing required packages: {', '.join(sorted(missing))}."
            )

    selectors = {
        "requirements.txt": "runtime.lock",
        "requirements-dev.txt": "dev.lock",
        "requirements-build.txt": "build.lock",
    }
    for filename, lock_name in selectors.items():
        content = (project_root / filename).read_text(encoding="utf-8").strip()
        if content != f"-r requirements/{lock_name}":
            raise DependencyLockError(f"{filename} must select requirements/{lock_name} only.")

    pyproject = (project_root / "pyproject.toml").read_text(encoding="utf-8")
    if 'requires = ["setuptools==82.0.1"]' not in pyproject:
        raise DependencyLockError("pyproject.toml must pin the setuptools build backend exactly.")
    return len(LOCK_NAMES)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify project dependency lock policy.")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    try:
        checked = verify_dependency_locks(args.project_root)
    except (DependencyLockError, OSError) as exc:
        parser.error(str(exc))
    print(f"Verified {checked} hash-locked dependency environments.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
