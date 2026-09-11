from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from scripts.check_dependency_locks import DependencyLockError, verify_dependency_locks
from scripts.generate_windows_lock import (
    LOCK_GENERATOR_PIP_VERSION,
    LockGenerationError,
    generate_lock,
    records_from_wheel_directory,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCK_CHECK_SCRIPT = PROJECT_ROOT / "scripts" / "check_dependency_locks.py"


def _write_wheel(wheel_directory: Path, name: str, version: str, payload: bytes = b"wheel") -> None:
    wheel_path = wheel_directory / f"{name}-{version}-py3-none-any.whl"
    dist_info = f"{name.replace('-', '_')}-{version}.dist-info"
    with zipfile.ZipFile(wheel_path, "w") as wheel:
        wheel.writestr(f"{dist_info}/METADATA", f"Name: {name}\nVersion: {version}\n")
        wheel.writestr(f"{dist_info}/RECORD", "")
        wheel.writestr("package.py", payload)


def test_repository_locks_follow_policy() -> None:
    assert verify_dependency_locks() == 4


def test_lock_generator_renders_sorted_hashed_wheels(tmp_path: Path) -> None:
    requirements_input = tmp_path / "runtime.in"
    requirements_input.write_text("example\n", encoding="utf-8")
    wheel_directory = tmp_path / "wheels"
    wheel_directory.mkdir()
    _write_wheel(wheel_directory, "zeta-package", "2.0")
    _write_wheel(wheel_directory, "alpha_package", "1.0")

    output_path = tmp_path / "runtime.lock"
    records = generate_lock(requirements_input, output_path, wheel_directory=wheel_directory)

    assert [record.normalized_name for record in records] == ["alpha-package", "zeta-package"]
    rendered = output_path.read_text(encoding="utf-8")
    assert f"# Resolver: pip=={LOCK_GENERATOR_PIP_VERSION}." in rendered
    assert "alpha-package==1.0 --hash=sha256:" in rendered
    assert "zeta-package==2.0 --hash=sha256:" in rendered


def test_lock_generator_rejects_conflicting_wheel_versions(tmp_path: Path) -> None:
    _write_wheel(tmp_path, "example", "1.0", b"first")
    _write_wheel(tmp_path, "Example", "2.0", b"second")

    with pytest.raises(LockGenerationError, match="Conflicting wheels"):
        records_from_wheel_directory(tmp_path)


def test_lock_policy_rejects_unhashed_package(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements"
    requirements.mkdir()
    for name in ("bootstrap", "runtime", "dev", "build"):
        (requirements / f"{name}.lock").write_text("example==1.0\n", encoding="utf-8")
    for filename, lock_name in {
        "requirements.txt": "runtime.lock",
        "requirements-dev.txt": "dev.lock",
        "requirements-build.txt": "build.lock",
    }.items():
        (tmp_path / filename).write_text(f"-r requirements/{lock_name}\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools==82.0.1"]\n', encoding="utf-8"
    )

    with pytest.raises(DependencyLockError, match="complete hashed pin"):
        verify_dependency_locks(tmp_path)


def test_lock_checker_cli() -> None:
    result = subprocess.run(
        [sys.executable, str(LOCK_CHECK_SCRIPT), "--project-root", str(PROJECT_ROOT)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Verified 4 hash-locked dependency environments." in result.stdout
