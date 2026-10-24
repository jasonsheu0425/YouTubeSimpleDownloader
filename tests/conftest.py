from __future__ import annotations

import os
from pathlib import Path
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QSettings, QStandardPaths
from PySide6.QtWidgets import QApplication

from scripts.check_test_isolation import TestIsolationError, verify_test_isolation


def pytest_sessionstart(session: pytest.Session) -> None:
    try:
        verify_test_isolation(Path(__file__).resolve().parents[1])
    except TestIsolationError as exc:
        raise pytest.UsageError(str(exc)) from exc


@pytest.fixture(scope="session", autouse=True)
def isolated_user_environment(tmp_path_factory: pytest.TempPathFactory):
    """Cover session fixtures and imported path constants, not just GUI tests."""
    from ytsimpledownloader import app, ffmpeg_resolver, paths

    root = tmp_path_factory.mktemp("ytsd-user")
    profile = root / "profile"
    app_data = root / "local" / paths.APP_NAME
    downloads = profile / "Downloads" / paths.APP_NAME
    temporary = root / "temp"
    for directory in (profile, app_data, downloads, temporary, root / "roaming", root / "config"):
        directory.mkdir(parents=True, exist_ok=True)
    patch = pytest.MonkeyPatch()
    old_test_mode = QStandardPaths.isTestModeEnabled()
    QStandardPaths.setTestModeEnabled(True)
    for name, value in {
        "USERPROFILE": profile,
        "HOME": profile,
        "LOCALAPPDATA": root / "local",
        "APPDATA": root / "roaming",
        "XDG_DATA_HOME": root / "local",
        "XDG_CONFIG_HOME": root / "config",
        "TEMP": temporary,
        "TMP": temporary,
    }.items():
        patch.setenv(name, str(value))
    patch.setenv("PATH", os.environ.get("PATH", ""))
    patch.setattr(tempfile, "tempdir", str(temporary))
    for name, value in {
        "APP_DATA_DIR": app_data,
        "PROJECT_DIR": app_data,
        "DEFAULT_DOWNLOAD_DIR": downloads,
        "FFMPEG_DIR": app_data / "ffmpeg",
    }.items():
        patch.setattr(paths, name, value)
    patch.setattr(ffmpeg_resolver, "FFMPEG_DIR", paths.FFMPEG_DIR)
    patch.setattr(app, "PROJECT_DIR", app_data)
    patch.setattr(app, "HISTORY_PATH", app_data / "history.json")
    patch.setattr(app, "DEFAULT_DOWNLOAD_DIR", downloads)
    try:
        yield root
    finally:
        QStandardPaths.setTestModeEnabled(old_test_mode)
        patch.undo()


@pytest.fixture
def isolated_settings_factory(tmp_path: Path):
    settings_path = tmp_path / "settings.ini"

    def create_settings(
        organization: str = "YouTubeSimpleDownloader",
        application: str = "YouTubeSimpleDownloader",
    ) -> QSettings:
        if (organization, application) != ("YouTubeSimpleDownloader", "YouTubeSimpleDownloader"):
            raise AssertionError("Unexpected settings identity in application test")
        # The organization/application overload ignores setDefaultFormat on Windows.
        settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
        settings.setFallbacksEnabled(False)
        assert settings.format() == QSettings.Format.IniFormat
        assert Path(settings.fileName()).resolve() == settings_path.resolve()
        return settings

    return create_settings


@pytest.fixture(autouse=True)
def isolated_settings(isolated_user_environment, isolated_settings_factory, monkeypatch, tmp_path):
    from ytsimpledownloader import app, paths

    app_data = tmp_path / "app-data"
    downloads = tmp_path / "downloads"
    app_data.mkdir()
    downloads.mkdir()
    monkeypatch.setattr(paths, "APP_DATA_DIR", app_data)
    monkeypatch.setattr(paths, "PROJECT_DIR", app_data)
    monkeypatch.setattr(paths, "DEFAULT_DOWNLOAD_DIR", downloads)
    monkeypatch.setattr(app, "PROJECT_DIR", app_data)
    monkeypatch.setattr(app, "HISTORY_PATH", app_data / "history.json")
    monkeypatch.setattr(app, "DEFAULT_DOWNLOAD_DIR", downloads)
    monkeypatch.setattr(app, "QSettings", isolated_settings_factory)
    settings = isolated_settings_factory()
    yield settings
    settings.sync()
    assert settings.status() == QSettings.Status.NoError


@pytest.fixture(scope="session")
def qapp(isolated_user_environment) -> QApplication:
    application = QApplication.instance() or QApplication([])
    yield application
    application.closeAllWindows()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    application.processEvents()
    application.quit()


@pytest.fixture(autouse=True)
def cleanup_qt_widgets(isolated_settings):
    yield
    application = QApplication.instance()
    if application is None:
        return
    for widget in application.topLevelWidgets():
        preview_timer = getattr(widget, "preview_timer", None)
        if preview_timer is not None:
            preview_timer.stop()
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    application.processEvents()
