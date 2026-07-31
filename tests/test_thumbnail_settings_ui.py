from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings

import ytsimpledownloader.app as app_module


@pytest.fixture
def isolated_settings(monkeypatch: pytest.MonkeyPatch, tmp_path) -> QSettings:
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.SystemScope, str(tmp_path))
    settings = QSettings("YouTubeSimpleDownloader", "YouTubeSimpleDownloader")
    settings.clear()
    settings.sync()
    monkeypatch.setattr(app_module, "ensure_default_dirs", lambda: None)
    monkeypatch.setattr(app_module, "HISTORY_PATH", tmp_path / "history.json")
    monkeypatch.setattr(app_module, "DEFAULT_DOWNLOAD_DIR", tmp_path)
    return settings


def test_thumbnail_setting_defaults_off_and_is_saved(qapp, isolated_settings) -> None:
    window = app_module.MainWindow()
    try:
        checkbox = window.embed_audio_thumbnail_checkbox
        assert checkbox.isChecked() is False
        assert checkbox.isEnabled() is True

        checkbox.setChecked(True)
        isolated_settings.sync()
        reloaded = QSettings("YouTubeSimpleDownloader", "YouTubeSimpleDownloader")
        assert str(reloaded.value("embed_audio_thumbnail", "false")).lower() == "true"
    finally:
        window.close()


def test_thumbnail_setting_is_loaded_and_only_enabled_for_mp3(qapp, isolated_settings) -> None:
    isolated_settings.setValue("embed_audio_thumbnail", "true")
    isolated_settings.sync()
    window = app_module.MainWindow()
    try:
        checkbox = window.embed_audio_thumbnail_checkbox
        assert checkbox.isChecked() is True

        window.audio_format_combo.setCurrentIndex(window.audio_format_combo.findData("m4a"))
        assert checkbox.isEnabled() is False

        window.audio_format_combo.setCurrentIndex(window.audio_format_combo.findData("mp3"))
        assert checkbox.isEnabled() is True

        window.mode_combo.setCurrentIndex(window.mode_combo.findData("mp4"))
        assert checkbox.isEnabled() is False

        window.mode_combo.setCurrentIndex(window.mode_combo.findData("both"))
        assert checkbox.isEnabled() is True
    finally:
        window.close()
