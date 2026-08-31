from __future__ import annotations

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


def test_sanitize_pyinstaller_path_preserves_tools_and_removes_ambient_runtimes() -> None:
    path_value = ";".join(
        [
            r"C:\Windows\System32",
            r"E:\YouTubeSimpleDownloader\.venv\Scripts",
            r"C:\Users\jason\.cache\codex-runtimes\runtime\native\poppler\Library\bin",
            r"C:\Tools\Poppler\Library\bin",
        ]
    )

    assert sanitize_pyinstaller_path(path_value) == ";".join(
        [r"C:\Windows\System32", r"E:\YouTubeSimpleDownloader\.venv\Scripts"]
    )
