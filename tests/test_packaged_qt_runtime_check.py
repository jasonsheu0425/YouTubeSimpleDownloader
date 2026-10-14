from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_packaged_qt_runtime import (
    PackagedQtRuntimeError,
    find_unsafe_root_icu_files,
    verify_packaged_qt_runtime,
)
from scripts.sanitize_pyinstaller_path import sanitize_pyinstaller_path


CHECK_SCRIPT = Path(__file__).parents[1] / "scripts" / "check_packaged_qt_runtime.py"


def test_empty_internal_directory_is_accepted(tmp_path: Path) -> None:
    internal_dir = tmp_path / "_internal"
    internal_dir.mkdir()

    assert find_unsafe_root_icu_files(internal_dir) == []
    verify_packaged_qt_runtime(internal_dir)


@pytest.mark.parametrize("name", ["icuuc.dll", "icudt78.dll", "icuin78.dll"])
def test_root_level_icu_dll_is_rejected(tmp_path: Path, name: str) -> None:
    internal_dir = tmp_path / "_internal"
    internal_dir.mkdir()
    (internal_dir / name).write_bytes(b"ambient ICU")

    with pytest.raises(PackagedQtRuntimeError, match=name):
        verify_packaged_qt_runtime(internal_dir)


def test_nested_icu_dll_is_not_treated_as_root_contamination(tmp_path: Path) -> None:
    internal_dir = tmp_path / "_internal"
    nested_dir = internal_dir / "vendor"
    nested_dir.mkdir(parents=True)
    (nested_dir / "icuuc.dll").write_bytes(b"allowed nested ICU")

    verify_packaged_qt_runtime(internal_dir)


def test_cli_reports_ambient_icu_contamination(tmp_path: Path) -> None:
    internal_dir = tmp_path / "_internal"
    internal_dir.mkdir()
    (internal_dir / "icuuc.dll").write_bytes(b"ambient ICU")

    result = subprocess.run(
        [sys.executable, str(CHECK_SCRIPT), str(internal_dir)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Unsafe root-level ICU DLL(s)" in result.stderr
    assert "ambient build-environment contamination" in result.stderr


def test_sanitize_pyinstaller_path_uses_only_derived_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = tmp_path / "release-venv"
    scripts = environment / "Scripts"
    scripts.mkdir(parents=True)
    executable = scripts / "python.exe"
    executable.touch()
    base = tmp_path / "base-python"
    for suffix in ("", "Scripts", "DLLs"):
        (base / suffix).mkdir(parents=True, exist_ok=True)
    windows = tmp_path / "Windows"
    (windows / "System32").mkdir(parents=True)
    ambient = tmp_path / "HP" / "Poppler" / "codex-runtimes"
    ambient.mkdir(parents=True)
    monkeypatch.setenv("PATH", str(ambient))

    result = sanitize_pyinstaller_path(
        executable=executable, prefix=environment, base_prefix=base, system_root=windows
    )

    assert result.split(os.pathsep) == [
        str(scripts),
        str(base),
        str(base / "Scripts"),
        str(base / "DLLs"),
        str(windows / "System32"),
        str(windows),
    ]
    assert str(ambient) not in result


def test_sanitize_pyinstaller_path_rejects_unrelated_interpreter(tmp_path: Path) -> None:
    environment = tmp_path / "release-venv"
    (environment / "Scripts").mkdir(parents=True)
    executable = tmp_path / "ambient" / "python.exe"
    executable.parent.mkdir()
    executable.touch()
    base = tmp_path / "base-python"
    base.mkdir()
    windows = tmp_path / "Windows"
    (windows / "System32").mkdir(parents=True)

    with pytest.raises(ValueError, match="Build interpreter"):
        sanitize_pyinstaller_path(
            executable=executable, prefix=environment, base_prefix=base, system_root=windows
        )
