"""Verify repository dependency locks are complete and match their declared inputs."""

from __future__ import annotations

import argparse
import re
import tomllib
from pathlib import Path

try:
    from scripts.dependency_lock_policy import (
        LOCK_GENERATOR_PIP_VERSION,
        RequirementInputError,
        normalized_name,
        parse_requirement_inputs,
    )
except ModuleNotFoundError:
    from dependency_lock_policy import (
        LOCK_GENERATOR_PIP_VERSION,
        RequirementInputError,
        normalized_name,
        parse_requirement_inputs,
    )


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCK_NAMES = ("bootstrap", "runtime", "dev", "build")
LOCK_LINE_PATTERN = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)==(?P<version>[^\s]+) "
    r"--hash=sha256:(?P<hash>[0-9a-f]{64})$"
)
PROJECT_PIN_PATTERN = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)==(?P<version>[A-Za-z0-9][A-Za-z0-9.+!_-]*)$"
)
REQUIRED_PACKAGES = {
    "bootstrap": {"pip"},
    "runtime": {"setuptools", "pyside6", "yt-dlp", "imageio-ffmpeg"},
    "dev": {"setuptools", "pyside6", "yt-dlp", "imageio-ffmpeg", "pytest"},
    "build": {
        "setuptools",
        "pyside6",
        "yt-dlp",
        "imageio-ffmpeg",
        "pyinstaller",
        "cyclonedx-bom",
    },
}


class DependencyLockError(RuntimeError):
    """Raised when a lock is incomplete, mutable, or inconsistent with policy."""


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
    """Validate lock completeness, exact direct inputs, selectors, and resolver pins."""
    requirement_directory = project_root / "requirements"
    lock_entries: dict[str, dict[str, tuple[str, str]]] = {}
    for name in LOCK_NAMES:
        lock_path = requirement_directory / f"{name}.lock"
        entries = parse_lock(lock_path)
        lock_entries[name] = entries
        missing = REQUIRED_PACKAGES[name] - set(entries)
        if missing:
            raise DependencyLockError(
                f"requirements/{name}.lock is missing required packages: {', '.join(sorted(missing))}."
            )
        try:
            direct_pins = parse_requirement_inputs(
                requirement_directory / f"{name}.in", project_root
            )
        except (OSError, RequirementInputError) as exc:
            raise DependencyLockError(str(exc)) from exc
        for package, version in direct_pins.items():
            locked = entries.get(package)
            if locked is None:
                raise DependencyLockError(
                    f"requirements/{name}.lock is missing direct input {package}=={version}."
                )
            if locked[0] != version:
                raise DependencyLockError(
                    f"requirements/{name}.lock pins {package}=={locked[0]}, "
                    f"but its input requires {package}=={version}."
                )

    bootstrap_pip = lock_entries["bootstrap"].get("pip")
    if bootstrap_pip is None or bootstrap_pip[0] != LOCK_GENERATOR_PIP_VERSION:
        raise DependencyLockError(
            "bootstrap pip pin must match the lock generator resolver version "
            f"{LOCK_GENERATOR_PIP_VERSION}."
        )
    for name in LOCK_NAMES:
        lock_text = (requirement_directory / f"{name}.lock").read_text(encoding="utf-8")
        resolver_line = f"# Resolver: pip=={LOCK_GENERATOR_PIP_VERSION}."
        if resolver_line not in lock_text.splitlines():
            raise DependencyLockError(
                f"requirements/{name}.lock resolver must be pip=={LOCK_GENERATOR_PIP_VERSION}."
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

    pyproject = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))
    build_requires = pyproject.get("build-system", {}).get("requires", [])
    if len(build_requires) != 1 or build_requires[0] != "setuptools==82.0.1":
        raise DependencyLockError("pyproject.toml must pin the setuptools build backend exactly.")
    project_dependencies = pyproject.get("project", {}).get("dependencies", [])
    if not isinstance(project_dependencies, list):
        raise DependencyLockError("pyproject.toml project dependencies must be exact pins.")
    project_runtime_pins: dict[str, str] = {}
    for requirement in project_dependencies:
        match = PROJECT_PIN_PATTERN.fullmatch(requirement) if isinstance(requirement, str) else None
        if match is None:
            raise DependencyLockError("pyproject.toml project dependencies must be exact pins.")
        package = normalized_name(match.group("name"))
        version = match.group("version")
        if package in project_runtime_pins:
            raise DependencyLockError(f"pyproject.toml duplicates runtime dependency {package}.")
        project_runtime_pins[package] = version
    input_runtime_pins = parse_requirement_inputs(requirement_directory / "runtime.in", project_root)
    declared_application_pins = {
        package: version
        for package, version in input_runtime_pins.items()
        if package != "setuptools"
    }
    if project_runtime_pins != declared_application_pins:
        raise DependencyLockError(
            "pyproject.toml runtime dependency pins must exactly match requirements/runtime.in."
        )
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
