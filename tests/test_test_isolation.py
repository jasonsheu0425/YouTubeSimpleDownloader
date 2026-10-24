from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest
from PySide6.QtCore import QSettings

from scripts.check_test_isolation import check_source, verify_test_isolation
from ytsimpledownloader import app, ffmpeg_resolver, paths


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "source",
    [
        "from PySide6.QtCore import QSettings\ns = QSettings('org', 'app')",
        "from PySide6.QtCore import QSettings as S\ns = S('org', 'app')",
        "from PySide6 import QtCore as core\ns = core.QSettings('org', 'app')",
        "import PySide6.QtCore as core\ns = core.QSettings('org', 'app')",
        "from PySide6.QtCore import QSettings\nS = QSettings\ns = S('org', 'app')",
        "import PySide6.QtCore as core\nS = core.QSettings\ns = S('org', 'app')",
        "from PySide6.QtCore import QSettings\nQSettings.setDefaultFormat(QSettings.IniFormat)\ns = QSettings('org', 'app')",
        "from PySide6.QtCore import QSettings\ns = QSettings(QSettings.UserScope, 'org', 'app')",
        "from PySide6.QtCore import QSettings\ns = QSettings('HKEY_CURRENT_USER/Software/Test', QSettings.NativeFormat)",
        "from PySide6.QtCore import QSettings\ns = QSettings()",
        "def isolated_settings():\n    pass",
        "import pytest\n@pytest.fixture(name='isolated_settings')\ndef replacement():\n    pass",
        "import winreg\nwinreg.OpenKey(None, 'test')",
        "from winreg import CreateKey as create_key",
        "from PySide6.QtCore import *",
    ],
)
def test_policy_rejects_native_settings_paths_without_executing_them(source: str) -> None:
    assert check_source(source)


def test_policy_allows_only_the_shared_explicit_ini_constructor() -> None:
    source = "settings = QSettings(str(settings_path), QSettings.Format.IniFormat)"
    assert check_source(source, shared_conftest=True) == []
    assert check_source(source)
    assert check_source(source.replace("IniFormat", "NativeFormat"), shared_conftest=True)


def test_repository_passes_precollection_isolation_policy() -> None:
    assert verify_test_isolation(PROJECT_ROOT) > 30


def test_release_tooling_job_installs_application_after_locked_dependencies() -> None:
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    job = workflow.split("\n  release-integrity-tooling:", 1)[1]
    dependencies = job.index("python -m pip install --require-hashes -r requirements-build.txt")
    application = job.index("python -m pip install --no-deps --no-build-isolation -e .")
    tests = job.index("python -m pytest tests/test_release_integrity.py tests/test_bundle_components.py")
    assert dependencies < application < tests


def test_precollection_guard_rejects_unsafe_module_before_its_code_runs(tmp_path: Path) -> None:
    project = tmp_path / "mini-project"
    tests = project / "tests"
    tests.mkdir(parents=True)
    fake_qt = project / "PySide6"
    fake_qt.mkdir()
    (fake_qt / "__init__.py").write_text("", encoding="utf-8")
    marker = project / "constructor-ran.txt"
    # A fake Qt module makes this failure-path test safe even if the guard regresses.
    (fake_qt / "QtCore.py").write_text(
        "from pathlib import Path\n"
        "def QSettings(*args):\n"
        f"    Path({str(marker)!r}).write_text('unsafe constructor ran')\n"
        "    raise AssertionError('Qt must never be reached')\n",
        encoding="utf-8",
    )
    (tests / "conftest.py").write_text(
        "from pathlib import Path\nimport pytest\n"
        "from scripts.check_test_isolation import TestIsolationError, verify_test_isolation\n"
        "def pytest_sessionstart(session):\n"
        "    try:\n        verify_test_isolation(Path(__file__).resolve().parents[1])\n"
        "    except TestIsolationError as exc:\n        raise pytest.UsageError(str(exc))\n",
        encoding="utf-8",
    )
    (tests / "test_unsafe.py").write_text(
        "from PySide6.QtCore import QSettings\n"
        "settings = QSettings('YouTubeSimpleDownloader', 'YouTubeSimpleDownloader')\n"
        "settings.clear()\ndef test_never_runs(): pass\n",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    environment["PYTHONPATH"] = os.pathsep.join((str(project), str(PROJECT_ROOT)))
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--confcutdir", str(tests), str(tests), "-q"],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 4
    assert "Unsafe test settings access" in result.stderr
    assert not marker.exists()


def test_settings_are_explicit_file_backed_and_can_be_reloaded(
    isolated_settings, isolated_settings_factory, tmp_path: Path,
) -> None:
    assert isolated_settings.format() == QSettings.Format.IniFormat
    assert Path(isolated_settings.fileName()).resolve() == (tmp_path / "settings.ini").resolve()
    assert not isolated_settings.fallbacksEnabled()
    isolated_settings.setValue("test-sentinel", "isolated")
    isolated_settings.sync()
    reloaded = isolated_settings_factory()
    assert reloaded.value("test-sentinel") == "isolated"
    assert reloaded.status() == QSettings.Status.NoError
    with pytest.raises(AssertionError, match="Unexpected settings identity"):
        isolated_settings_factory("another-organization", "another-application")


@pytest.mark.parametrize("iteration", [1, 2])
def test_every_case_gets_fresh_settings_without_opt_in(qapp, tmp_path: Path, iteration: int) -> None:
    window = app.MainWindow()
    try:
        assert window.settings.format() == QSettings.Format.IniFormat
        assert Path(window.settings.fileName()).resolve().is_relative_to(tmp_path.resolve())
        assert window.settings.value("previous-test") is None
        window.settings.setValue("previous-test", iteration)
        assert app.HISTORY_PATH.resolve().is_relative_to(tmp_path.resolve())
        assert app.DEFAULT_DOWNLOAD_DIR.resolve().is_relative_to(tmp_path.resolve())
    finally:
        window.close()


def test_session_paths_and_environment_are_owned_by_pytest(isolated_user_environment) -> None:
    root = isolated_user_environment.resolve()
    assert Path.home().resolve().is_relative_to(root)
    for name in ("LOCALAPPDATA", "APPDATA", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "TEMP", "TMP"):
        assert Path(os.environ[name]).resolve().is_relative_to(root)
    assert paths.FFMPEG_DIR.resolve().is_relative_to(root)
    assert ffmpeg_resolver.FFMPEG_DIR == paths.FFMPEG_DIR
