from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from scripts.check_dependency_locks import DependencyLockError, verify_dependency_locks
from scripts.dependency_lock_policy import RequirementInputError, parse_requirement_inputs
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


def _write_policy_project(project_root: Path) -> None:
    requirements = project_root / "requirements"
    requirements.mkdir()
    input_contents = {
        "bootstrap.in": "pip==26.2.1\n",
        "base.in": (
            "setuptools==82.0.1\n"
            "PySide6==6.10.1\n"
            "yt-dlp==2026.8.19\n"
            "imageio-ffmpeg==0.6.0\n"
        ),
        "runtime.in": "-r base.in\n",
        "dev.in": "-r runtime.in\npytest==8.4.2\n",
        "build.in": "-r runtime.in\npyinstaller==6.15.0\ncyclonedx-bom==7.5.0\n",
    }
    for filename, content in input_contents.items():
        (requirements / filename).write_text(content, encoding="utf-8")

    package_versions = {
        "pip": "26.2.1",
        "setuptools": "82.0.1",
        "pyside6": "6.10.1",
        "yt-dlp": "2026.8.19",
        "imageio-ffmpeg": "0.6.0",
        "pytest": "8.4.2",
        "pyinstaller": "6.15.0",
        "cyclonedx-bom": "7.5.0",
    }
    environments = {
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
    for environment, packages in environments.items():
        entries = "".join(
            f"{name}=={package_versions[name]} --hash=sha256:{'a' * 64}\n"
            for name in sorted(packages)
        )
        (requirements / f"{environment}.lock").write_text(
            f"# Resolver: pip==26.2.1.\n\n{entries}", encoding="utf-8"
        )

    for filename, lock_name in {
        "requirements.txt": "runtime.lock",
        "requirements-dev.txt": "dev.lock",
        "requirements-build.txt": "build.lock",
    }.items():
        (project_root / filename).write_text(
            f"-r requirements/{lock_name}\n", encoding="utf-8"
        )
    (project_root / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools==82.0.1"]\n'
        'build-backend = "setuptools.build_meta"\n\n'
        '[project]\ndependencies = ["PySide6==6.10.1", '
        '"yt-dlp==2026.8.19", "imageio-ffmpeg==0.6.0"]\n',
        encoding="utf-8",
    )


def test_lock_checker_accepts_matching_direct_inputs(tmp_path: Path) -> None:
    _write_policy_project(tmp_path)

    assert verify_dependency_locks(tmp_path) == 4


def test_lock_checker_rejects_direct_input_version_mismatch(tmp_path: Path) -> None:
    _write_policy_project(tmp_path)
    build_lock = tmp_path / "requirements" / "build.lock"
    build_lock.write_text(
        build_lock.read_text(encoding="utf-8").replace("pyinstaller==6.15.0", "pyinstaller==6.14.0"),
        encoding="utf-8",
    )

    with pytest.raises(DependencyLockError, match="input requires pyinstaller==6.15.0"):
        verify_dependency_locks(tmp_path)


def test_lock_checker_rejects_resolver_mismatch(tmp_path: Path) -> None:
    _write_policy_project(tmp_path)
    lock_path = tmp_path / "requirements" / "dev.lock"
    lock_path.write_text(
        lock_path.read_text(encoding="utf-8").replace("pip==26.2.1", "pip==26.2.0"),
        encoding="utf-8",
    )

    with pytest.raises(DependencyLockError, match="resolver must be pip==26.2.1"):
        verify_dependency_locks(tmp_path)


def test_lock_checker_rejects_pyproject_runtime_pin_drift(tmp_path: Path) -> None:
    _write_policy_project(tmp_path)
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text(encoding="utf-8").replace("yt-dlp==2026.8.19", "yt-dlp==2026.8.18"),
        encoding="utf-8",
    )

    with pytest.raises(DependencyLockError, match="exactly match requirements/runtime.in"):
        verify_dependency_locks(tmp_path)


def test_requirement_input_parser_rejects_include_escape(tmp_path: Path) -> None:
    project = tmp_path / "project"
    requirements = project / "requirements"
    requirements.mkdir(parents=True)
    outside = tmp_path / "outside.in"
    outside.write_text("example==1.0\n", encoding="utf-8")
    input_file = requirements / "build.in"
    input_file.write_text(f"-r {outside}\n", encoding="utf-8")

    with pytest.raises(RequirementInputError, match="escapes the project"):
        parse_requirement_inputs(input_file, project)


def test_lock_checker_cli() -> None:
    result = subprocess.run(
        [sys.executable, str(LOCK_CHECK_SCRIPT), "--project-root", str(PROJECT_ROOT)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Verified 4 hash-locked dependency environments." in result.stdout
